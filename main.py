# menu_planner/main.py
import logging
import json
import uuid
import psutil
import hashlib
from contextlib import asynccontextmanager
from concurrent.futures import ProcessPoolExecutor
from typing import List, Union
from fastapi import FastAPI, HTTPException, Body, BackgroundTasks, Path, Request as FastAPIRequest
from .schemas.menu import (
    MenuRequest, MenuResponse, PlanTaskSubmitResponse, PlanResultResponse, 
    PlanResultSuccess, 
    PlanResultProcessing, PlanResultError
)
from .services.menu_fetcher import get_dishes_for_restaurant, preprocess_menu
from .services.genetic_planner import plan_menu_async
from .core.cache import redis_manager
from .core.config import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 服务启动中...")
    redis_manager.initialize()
    app_state["PROCESS_POOL"] = ProcessPoolExecutor(max_workers=settings.process_pool_max_workers)
    logger.info("✅ Redis连接池与进程池已创建。")
    logger.info("🎉 服务已准备就绪!")
    yield
    logger.info("🛑 shutting down...")
    app_state["PROCESS_POOL"].shutdown(wait=True)
    redis_manager.close()
    logger.info("🛑 进程池与Redis连接池已关闭。")

api_description = """
一个利用遗传算法进行自动化配餐的API服务。

---

## 🚀 API 测试指南

本API采用**异步任务**模式，测试流程分为两步：

1.  **提交配餐任务**:
    - 使用 `POST /api/v1/plan-menu` 端点提交您的配餐需求。
    - 如果该请求可以被处理，系统会返回一个 `task_id`。

2.  **查询配餐结果**:
    - 使用 `GET /api/v1/plan-menu/results/{task_id}` 端点，并将在上一步中获取的 `task_id` 作为路径参数。
    - 反复轮询此端点，直到 `status` 变为 `SUCCESS` 或 `FAILED`。

---

### ⚡️ 关于缓存机制 (`ignore_cache` 参数)

为了提升性能，本API内置了缓存系统。`ignore_cache` 参数（默认为 `false`）控制着它的行为：

-   **`ignore_cache: false` (默认行为 / Default behavior)**:
    - 当您提交任务时，系统会**优先在缓存中查找**符合您请求（人数、预算、忌口等）的方案。
    - 如果**找到缓存**，您将**立即收到一个包含完整菜单方案的成功响应**，而不会创建新的后台任务。
    - 如果**未找到缓存**，系统才会创建新任务，并返回 `task_id` 供您查询。

-   **`ignore_cache: true`**:
    - 当您提交任务时，系统会**强制忽略所有缓存**，总是创建一个新的后台任务来实时计算全新的菜单方案。您总会收到一个 `task_id`。

> **测试建议**: 在进行功能或算法测试时，建议将 `ignore_cache` 设置为 `true` 以确保每次都触发新的计算。
"""
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

app = FastAPI(
    title="AI配餐模型 API",
    description=api_description, # <-- 修改这里，使用新变量
    version="1.0.0",
    lifespan=lifespan
)

# --- 辅助函数，用于创建缓存键 ---
def create_plan_cache_key(request: MenuRequest) -> str:
    """为方案请求创建一个确定性的缓存键"""
    # 将限制排序，确保 ['A', 'B'] 和 ['B', 'A'] 的哈希值相同
    sorted_restrictions = sorted(request.dietary_restrictions)
    key_string = (
        f"{request.restaurant_id}:{request.diner_count}:"
        f"{request.total_budget}:{','.join(sorted_restrictions)}"
    )
    return f"plan_cache:{hashlib.md5(key_string.encode()).hexdigest()}"

# --- 后台任务执行函数 ---
async def run_planning_task(request: MenuRequest, task_id: str):
    """
    这个函数在后台运行，执行完整的配餐逻辑并将结果存入Redis。
    """
    task_result_key = f"task_result:{task_id}"
    try:
        # 1. 获取和预处理菜品
        all_dishes = await get_dishes_for_restaurant(request.restaurant_id)
        if not all_dishes:
            raise ValueError(f"找不到餐厅 '{request.restaurant_id}' 的菜单。")

        available_dishes, error_msg = preprocess_menu(all_dishes, request)
        if error_msg:
            raise ValueError(error_msg)
        
        logger.info(f"Task {task_id}: 筛选后可用菜品数量: {len(available_dishes)}")

        # 2. 调用遗传算法
        menu_results = await plan_menu_async(
            process_pool=app_state["PROCESS_POOL"],
            dishes=available_dishes, 
            request=request,
            config=settings
        )
        
        if not menu_results:
            raise ValueError("抱歉，未能找到合适的菜单方案，请您修改预算或放宽部分规则后再次尝试！")

        # 3. 成功，存储结果
        result_data = PlanResultSuccess(
            task_id=task_id,
            status="SUCCESS",
            result=[res.model_dump() for res in menu_results] # 转换为可序列化字典
        ).model_dump_json()

        # 同时，更新方案缓存
        plan_cache_key = create_plan_cache_key(request)
        cache_data = {
            "plans": [res.model_dump() for res in menu_results]
        }
        async with redis_manager.get_connection() as redis:
            await redis.set(task_result_key, result_data, ex=3600) # 任务结果缓存1小时
            await redis.set(plan_cache_key, json.dumps(cache_data), ex=settings.redis.plan_cache_ttl_seconds)

        logger.info(f"Task {task_id}: 成功完成并缓存结果。")

    except Exception as e:
        logger.error(f"Task {task_id}: 配餐任务执行失败: {e}", exc_info=True)
        error_data = PlanResultError(
            task_id=task_id,
            status="FAILED",
            error=str(e)
        ).model_dump_json()
        async with redis_manager.get_connection() as redis:
            await redis.set(task_result_key, error_data, ex=3600)


@app.post(
    "/api/v1/plan-menu",
    # 响应模型现在可以是两种类型之一
    response_model=Union[PlanTaskSubmitResponse, PlanResultSuccess],
    tags=["Menu Planning (Async)"]
)
async def submit_menu_plan_task(
    request: MenuRequest,
    background_tasks: BackgroundTasks,
    fastapi_request: FastAPIRequest
):
    """
    - 提交一个配餐任务。
    - 如果缓存命中，立即返回成功结果。
    - 如果缓存未命中，返回任务ID供客户端轮询。
    """
    logger.info(f"收到新的异步配餐请求: 餐厅'{request.restaurant_id}', {request.diner_count}人, 预算 {request.total_budget}元")
    
    plan_cache_key = create_plan_cache_key(request)
    async with redis_manager.get_connection() as redis:
        cached_plan_json = await redis.get(plan_cache_key)
    
    #  缓存命中时的逻辑完全改变
    if cached_plan_json and not request.ignore_cache:
        cached_data = json.loads(cached_plan_json)
        logger.info("方案缓存命中。直接返回缓存的方案。")
        
        
        # 不再创建伪任务，而是直接构建并返回成功响应
        return PlanResultSuccess(
            task_id=f"cached-{uuid.uuid4()}", # 仍然生成一个唯一的ID用于追踪
            status="SUCCESS",
            result=cached_data["plans"]
        )

    # 如果缓存不适用(不存在或被忽略)，则尝试创建新任务 
    # 在创建任务前会检查当前系统内存使用率。

     # 获取当前系统的虚拟内存使用情况
    memory_status = psutil.virtual_memory()
    memory_percent = memory_status.percent

    # 检查内存使用率是否超过了配置的阈值
    if memory_percent >= settings.dynamic_queue_mem_threshold_percent:
        logger.warning(
            f"内存使用率过高 ({memory_percent:.2f}%)，已达到阈值 "
            f"({settings.dynamic_queue_mem_threshold_percent}%)。暂时拒绝新的任务请求。"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"服务当前负载过高 (内存使用率: {memory_percent:.2f}%)，请稍后重试。"
                "Service is under high load, please try again later."
            )
        )
    # --- 检查结束 ---

    task_id = str(uuid.uuid4())
    if cached_plan_json and request.ignore_cache:
        logger.info(f"用户请求忽略缓存。创建新任务: {task_id}")
    else:
        logger.info(f"方案缓存未命中。创建新任务: {task_id}")

    task_result_key = f"task_result:{task_id}"
    processing_data = PlanResultProcessing(task_id=task_id, status="PROCESSING").model_dump_json()
    async with redis_manager.get_connection() as redis:
        await redis.set(task_result_key, processing_data, ex=3600)

    background_tasks.add_task(run_planning_task, request, task_id)
    
    result_url = fastapi_request.url_for('get_menu_plan_result', task_id=task_id)
    # 只有在创建新任务时，才返回这个 PENDING 状态的响应
    return PlanTaskSubmitResponse(task_id=task_id, status="PENDING", result_url=str(result_url))


    # 2. 如果缓存不适用，创建新任务
    task_id = str(uuid.uuid4())
    logger.info(f"方案缓存未命中或被忽略。创建新任务: {task_id}")
    
    # 标记任务正在处理中
    task_result_key = f"task_result:{task_id}"
    processing_data = PlanResultProcessing(task_id=task_id, status="PROCESSING").model_dump_json()
    async with redis_manager.get_connection() as redis:
        await redis.set(task_result_key, processing_data, ex=3600) # 先占位，防止客户端过早查询

    # 3. 将耗时任务添加到后台
    background_tasks.add_task(run_planning_task, request, task_id)
    
    # 4. 立即返回任务ID
    result_url = fastapi_request.url_for('get_menu_plan_result', task_id=task_id)
    return PlanTaskSubmitResponse(task_id=task_id, status="PENDING", result_url=str(result_url))


@app.get("/api/v1/plan-menu/results/{task_id}", response_model=PlanResultResponse, tags=["Menu Planning (Async)"])
async def get_menu_plan_result(task_id: str = Path(..., description="提交任务时获取的Task ID")):
    """
    **v1 (异步)**: 根据任务ID查询配餐结果。
    """
    task_result_key = f"task_result:{task_id}"
    async with redis_manager.get_connection() as redis:
        result_json = await redis.get(task_result_key)
        
    if not result_json:
        raise HTTPException(status_code=404, detail="任务ID不存在或已过期。")
    
    result_data = json.loads(result_json)
    return result_data


@app.get("/", tags=["Health Check"])
def read_root():
    return {"status": "ok", "message": "欢迎使用AI配餐模型 API v1.0"}