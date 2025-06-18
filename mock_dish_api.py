# mock_dish_api.py
import uvicorn
import pandas as pd
from fastapi import FastAPI, HTTPException
from typing import List
from contextlib import asynccontextmanager

# --- 核心修正: 使用 Lifespan 代替 on_event ---
# 这是FastAPI推荐的、更现代化的应用生命周期管理方式

DISHES_DB = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 服务启动时执行 ---
    print("🚀 模拟API服务启动中...")
    print("   正在从CSV加载模拟数据...")
    try:
        # 当从 menu_planner 目录的父目录运行时, 路径需要包含子目录
        df = pd.read_csv("menu_planner/menu.csv")
        
        DISHES_DB['MZDP'] = df.to_dict('records')
        DISHES_DB['KFC'] = df.head(10).to_dict('records')
        
        print(f"   ✅ 模拟数据加载完成: {len(DISHES_DB['MZDP'])} 道菜 for MZDP, {len(DISHES_DB['KFC'])} 道菜 for KFC.")
    except FileNotFoundError:
        print("   🚨 错误：找不到 'menu_planner/menu.csv' 文件。请确保你在项目根目录下运行此脚本。")
    
    print("🎉 模拟API服务已准备就绪!")
    yield
    # --- 服务关闭时执行 ---
    print("🛑 模拟API服务正在关闭...")


# 将lifespan注册到FastAPI应用
app = FastAPI(lifespan=lifespan)


@app.get("/api/v1/dishes/{restaurant_id}", response_model=List[dict])
def get_dishes(restaurant_id: str):
    """根据餐厅ID返回菜品列表"""
    print(f"   [请求日志] 收到对餐厅 '{restaurant_id}' 的菜品请求。")
    if restaurant_id in DISHES_DB:
        return DISHES_DB[restaurant_id]
    else:
        raise HTTPException(status_code=404, detail=f"Restaurant '{restaurant_id}' not found.")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)