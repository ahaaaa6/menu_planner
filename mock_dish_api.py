# menu_planner/mock_dish_api.py

import logging
import contextlib
import pandas as pd
from fastapi import FastAPI, HTTPException

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 全局变量，用于存储从CSV加载的菜品数据
DISHES_DB = {}

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 模拟API服务启动中...")
    logger.info("   正在从CSV加载模拟数据...")
    try:
        # 1. 【最终编码】使用 gbk 读取文件
        df = pd.read_csv("menu_planner/menu.csv", encoding="gbk")
        
        # 2. 【清理数据】清理 restaurant_id 列中可能存在的多余空格
        df['restaurant_id'] = df['restaurant_id'].str.strip()
        
        # 3. 【正确加载】按餐厅ID分组，并将数据加载到 DISHES_DB
        for restaurant_id, group in df.groupby("restaurant_id"):
            DISHES_DB[restaurant_id] = group.to_dict('records')
            logger.info(f"   ✅ 已加载餐厅 '{restaurant_id}' 的 {len(group)} 道菜。")
        
        logger.info("🎉 模拟API服务已准备就绪!")

    except FileNotFoundError:
        logger.error("   🚨 错误：找不到 'menu_planner/menu.csv' 文件。")
    except Exception as e:
        logger.error(f"   🚨 加载数据时发生未知错误: {e}", exc_info=True)

    yield
    
    logger.info("🛑 模拟API服务正在关闭...")
    DISHES_DB.clear()


app = FastAPI(
    title="模拟菜品API",
    description="一个用于为智能配餐AI助手提供模拟菜品数据的API。",
    version="1.2.0", # Final Fix Version
    lifespan=lifespan
)

@app.get("/dishes/{restaurant_id}")
async def get_dishes_by_restaurant(restaurant_id: str):

    if restaurant_id in DISHES_DB:
        return DISHES_DB[restaurant_id]
    else:
        raise HTTPException(status_code=404, detail=f"Restaurant '{restaurant_id}' not found.")

@app.get("/")
def read_root():
    return {"status": "ok", "message": "模拟菜品API正在运行。"}