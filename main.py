# menu_planner/main.py
import logging
from contextlib import asynccontextmanager
from concurrent.futures import ProcessPoolExecutor
from typing import List

from fastapi import FastAPI, HTTPException, Body

from menu_planner.schemas.menu import MenuRequest, MenuResponse
from menu_planner.services.menu_fetcher import get_dishes_for_restaurant, preprocess_menu
from menu_planner.services.genetic_planner import plan_menu_async
from menu_planner.core.cache import redis_manager
from menu_planner.core.config import settings  # 修复：正确导入配置

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 应用状态管理 ---
app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 服务启动时执行 ---
    logger.info("🚀 服务启动中...")
    
    # 1. 初始化Redis连接池
    redis_manager.initialize()
    
    # 2. 初始化进程池
    process_pool = ProcessPoolExecutor(max_workers=settings.process_pool_max_workers)  # 修复：使用配置中的值
    app_state["PROCESS_POOL"] = process_pool
    logger.info("✅ 进程池已创建。")
    
    logger.info("🎉 服务已准备就绪!")
    yield
    # --- 服务关闭时执行 ---
    logger.info("🛑 shutting down...")
    app_state["PROCESS_POOL"].shutdown(wait=True)
    redis_manager.close()
    logger.info("🛑 进程池与Redis连接池已关闭。")

# --- FastAPI 应用实例 ---
app = FastAPI(
    title="智能排菜AI助手 API",
    description="一个利用遗传算法进行自动化中餐菜单规划的API服务。",
    version="2.0.0", # 版本升级
    lifespan=lifespan
)

@app.post("/api/v1/plan-menu", response_model=List[MenuResponse], tags=["Menu Planning"])
async def create_menu_plan(request: MenuRequest = Body(...)):
    """
    接收排菜请求，并异步返回最多3个高质量的菜单方案。
    - **restaurant_id**: (必填) 餐厅的唯一标识符。
    - **diner_count**: (必填) 就餐人数。
    - **total_budget**: (必填) 总预算。
    - **dietary_restrictions**: (选填) 忌口列表。
    """
    logger.info(f"收到新的排菜请求: 餐厅'{request.restaurant_id}', {request.diner_count}人, 预算 {request.total_budget}元")
    
    # 1. 按需获取菜品数据（缓存优先）
    all_dishes = await get_dishes_for_restaurant(request.restaurant_id)
    if not all_dishes:
        raise HTTPException(
            status_code=404, 
            detail=f"找不到餐厅 '{request.restaurant_id}' 的菜单，或者该餐厅菜单为空。"
        )

    # 2. 预处理和过滤菜单
    available_dishes, error_msg = preprocess_menu(all_dishes, request)
    if error_msg:
        logger.warning(f"请求被拒绝: {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
        
    logger.info(f"筛选后可用菜品数量: {len(available_dishes)}")

    # 3. 调用异步排菜服务
    # 修复：使用正确的参数名称和顺序
    menu_results = await plan_menu_async(
        process_pool=app_state["PROCESS_POOL"],  # 修复：正确的参数名
        dishes=available_dishes, 
        request=request,
        config=settings  # 修复：传递配置对象
    )
    
    if not menu_results:
        logger.warning("算法未能为该请求找到任何合适的菜单方案。")
        raise HTTPException(status_code=404, detail="抱歉，未能找到合适的菜单方案，请您修改预算或放宽部分规则后再次尝试！")
        
    logger.info(f"成功为请求生成 {len(menu_results)} 个方案。")
    return menu_results

@app.get("/", tags=["Health Check"])
def read_root():
    return {"status": "ok", "message": "欢迎使用智能排菜AI助手 API v2.0"}