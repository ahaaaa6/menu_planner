# menu_planner/main.py
import logging
import json
import uuid
import time
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
from .core.cache import redis_manager, RedisConnectionError
from .core.config import settings

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 应用状态存储
app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("🚀 应用启动中...")
    
    # 初始化 Redis 连接
    try:
        redis_manager.initialize()
        logger.info("✅ Redis 连接池初始化成功")
        
        # 测试 Redis 连接
        ping_result = await redis_manager.ping()
        if ping_result:
            logger.info("✅ Redis 连接测试成功")
        else:
            logger.warning("⚠️ Redis 连接测试失败，但应用将继续运行")
            
        # 打印配置信息
        logger.info(f"📡 Redis 配置: {settings.redis.host}:{settings.redis.port}/{settings.redis.db}")
        
    except Exception as e:
        logger.error(f"❌ Redis 初始化失败: {e}")
        # 根据你的需求决定是否要阻止应用启动
        # raise  # 取消注释这行会在 Redis 连接失败时阻止应用启动
    
    # 初始化进程池
    try:
        app_state["PROCESS_POOL"] = ProcessPoolExecutor(max_workers=settings.process_pool_max_workers)
        logger.info(f"✅ 进程池已创建，最大工作进程数: {settings.process_pool_max_workers}")
    except Exception as e:
        logger.error(f"❌ 进程池初始化失败: {e}")
        raise
    
    logger.info("🎉 应用已准备就绪!")
    
    yield
    
    # 关闭时
    logger.info("🛑 应用关闭中...")
    try:
        if "PROCESS_POOL" in app_state:
            app_state["PROCESS_POOL"].shutdown(wait=True)
            logger.info("✅ 进程池已关闭")
    except Exception as e:
        logger.warning(f"⚠️ 关闭进程池时出现警告: {e}")
    
    try:
        await redis_manager.close()
        logger.info("✅ Redis 连接池已关闭")
    except Exception as e:
        logger.warning(f"⚠️ 关闭 Redis 连接时出现警告: {e}")

# API 描述文档
api_description = """
根据预算、人数、忌口等条件自动化配餐的API服务。

---

## 🚀 API 测试指南

本API采用**异步任务**模式，测试流程分为两步：

1.  **提交配餐任务**:
    - 使用 `POST /api/v1/plan-menu` 端点提交您的配餐需求。
    - 系统验证请求后，会返回一个 `task_id`，代表您的任务已进入后台队列。

2.  **查询配餐结果**:
    - 使用 `GET /api/v1/plan-menu/results/{task_id}` 端点，并将在上一步中获取的 `task_id` 作为路径参数。
    - 反复轮询此端点，直到 `status` 变为 `SUCCESS` 或 `FAILED`。

---

### ⚡️ 关于双层缓存机制

为了提升性能，本API内置了**两层缓存系统**，分别针对不同的场景进行优化。

### 第一层：菜品库缓存 (服务器端自动缓存)
为了缩短**每一个新任务**的准备时间。
-   系统会在收到配餐请求时从数据源（Mock API或真实数据库）获取该餐厅完整的菜品列表，并将其**缓存在Redis**中。这个缓存有一个预设的生命周期（TTL），十个小时。
-   在缓存有效期内，该餐厅所有新的配餐任务都无需再通过请求去获取菜品数据，而是直接从缓存中读取。

### 第二层：配餐方案缓存 (用户端可控缓存)
这是为了避免对**完全相同的请求**进行重复的CPU密集型计算。这个缓存通过 `ignore_cache` 参数来控制。
-   **`ignore_cache: false` (默认)**:
    - 当您提交任务时，系统会根据您请求的**所有参数**（如人数、预算、口味、忌口等）生成一个唯一的标识。
    - 系统会用此标识**优先在缓存中查找**是否已有完全匹配的、计算好的菜单方案。
    - **如果命中缓存**，API将**立即返回完整的菜单方案**，状态为 `SUCCESS`，整个过程几乎没有延迟，也不会创建新的后台任务。
    - **如果未命中缓存**，系统才会创建新任务，并返回 `task_id` 供您后续查询。

-   **`ignore_cache: true`**:
    - 当您提交任务时，系统会**强制忽略所有缓存**，总是创建一个新的后台任务来实时计算全新的菜单方案。您总会收到一个 `task_id`。

> **测试建议**: 在进行性能基准测试或需要确保获得全新结果时，建议将 `ignore_cache` 设置为 `true`。
"""

app = FastAPI(
    title="AI配餐模型 API",
    description=api_description,
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
    后台任务执行函数，带Redis重试逻辑
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
            result=[res.model_dump() for res in menu_results]
        ).model_dump_json()

        # 同时，更新方案缓存
        plan_cache_key = create_plan_cache_key(request)
        cache_data = {
            "plans": [res.model_dump() for res in menu_results]
        }

        # 使用重试逻辑保存结果
        task_saved = await redis_manager.set(
            task_result_key, 
            result_data, 
            ex=3600
        )
        
        cache_saved = await redis_manager.set(
            plan_cache_key, 
            json.dumps(cache_data), 
            ex=settings.redis.plan_cache_ttl_seconds
        )

        if task_saved:
            logger.info(f"Task {task_id}: 成功完成并保存任务结果。")
        else:
            logger.warning(f"Task {task_id}: 任务完成但无法保存到Redis。")
            
        if cache_saved:
            logger.info(f"Task {task_id}: 方案缓存已更新。")
        else:
            logger.warning(f"Task {task_id}: 无法更新方案缓存。")

    except Exception as e:
        logger.error(f"Task {task_id}: 配餐任务执行失败: {e}", exc_info=True)
        error_data = PlanResultError(
            task_id=task_id,
            status="FAILED",
            error=str(e)
        ).model_dump_json()
        
        # 尝试保存错误信息
        error_saved = await redis_manager.set(
            task_result_key, 
            error_data, 
            ex=3600
        )
        
        if not error_saved:
            logger.error(f"Task {task_id}: 无法保存错误信息到Redis。")

# --- 主要API端点 ---
@app.post("/api/v1/plan-menu", response_model=Union[PlanTaskSubmitResponse, MenuResponse], tags=["Menu Planning (Async)"])
async def submit_menu_plan(
    request: MenuRequest = Body(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    fastapi_request: FastAPIRequest = None
):
    """
    提交配餐任务（异步模式）
    """
    logger.info(f"收到配餐请求: 餐厅={request.restaurant_id}, 人数={request.diner_count}, 预算={request.total_budget}")
    
    # 1. 检查缓存（如果用户未要求忽略缓存）
    cached_plan_json = None
    if not request.ignore_cache:
        plan_cache_key = create_plan_cache_key(request)
        try:
            cached_plan_json = await redis_manager.get(plan_cache_key)
            if cached_plan_json:
                logger.info(f"方案缓存命中，立即返回结果。")
                cached_data = json.loads(cached_plan_json)
                return MenuResponse(plans=cached_data["plans"])
        except Exception as e:
            logger.warning(f"读取缓存失败: {e}")
    
    # 2. 创建新任务
    task_id = str(uuid.uuid4())
    if cached_plan_json and request.ignore_cache:
        logger.info(f"用户请求忽略缓存。创建新任务: {task_id}")
    else:
        logger.info(f"方案缓存未命中。创建新任务: {task_id}")

    # 3. 标记任务正在处理中
    task_result_key = f"task_result:{task_id}"
    processing_data = PlanResultProcessing(task_id=task_id, status="PROCESSING").model_dump_json()
    
    try:
        await redis_manager.set(task_result_key, processing_data, ex=3600)
    except Exception as e:
        logger.error(f"无法保存任务状态到Redis: {e}")
        raise HTTPException(status_code=503, detail="服务暂时不可用，请稍后重试。")

    # 4. 将耗时任务添加到后台
    background_tasks.add_task(run_planning_task, request, task_id)
    
    # 5. 立即返回任务ID
    result_url = fastapi_request.url_for('get_menu_plan_result', task_id=task_id)
    return PlanTaskSubmitResponse(task_id=task_id, status="PENDING", result_url=str(result_url))


@app.get("/api/v1/plan-menu/results/{task_id}", response_model=PlanResultResponse, tags=["Menu Planning (Async)"])
async def get_menu_plan_result(task_id: str = Path(..., description="提交任务时获取的Task ID")):
    """
    根据任务ID查询配餐结果，带重试逻辑
    """
    task_result_key = f"task_result:{task_id}"
    
    try:
        result_json = await redis_manager.get(task_result_key)
        
        if not result_json:
            raise HTTPException(status_code=404, detail="任务ID不存在或已过期。")
        
        result_data = json.loads(result_json)
        return result_data
        
    except RedisConnectionError:
        raise HTTPException(
            status_code=503, 
            detail="Redis服务暂时不可用，请稍后重试。"
        )
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500, 
            detail="任务结果数据损坏。"
        )
    
# 添加健康检查端点
@app.get("/health", tags=["Health Check"])
async def health_check():
    """
    健康检查端点，包含Redis连接状态
    """
    redis_status = await redis_manager.get_connection_status()
    redis_ping = await redis_manager.ping()
    
    return {
        "status": "ok" if redis_ping else "degraded",
        "message": "欢迎使用AI配餐模型 API v1.0",
        "redis": {
            "connected": redis_ping,
            "status": redis_status
        },
        "timestamp": time.time()
    }


# 添加Redis状态端点
@app.get("/api/v1/redis/status", tags=["Health Check"])
async def redis_status():
    """
    详细的Redis状态信息
    """
    status = await redis_manager.get_connection_status()
    ping_result = await redis_manager.ping()
    
    return {
        "connection_status": status,
        "ping_successful": ping_result,
        "timestamp": time.time()
    }


@app.get("/", tags=["Health Check"])
def read_root():
    return {"status": "ok", "message": "欢迎使用AI配餐模型 API v1.0"}