# 文件: menu_planner/schemas/menu.py

from pydantic import BaseModel, Field
from typing import List, Optional

class Dish(BaseModel):
    """
    定义单个菜品的数据结构。
    这个模型应该与API返回的JSON对象中的字段相匹配。
    """
    restaurant_id: str
    dish_id: str
    dish_name: str
    dish_category: str
    is_signature: bool
    unit: str
    price: float
    cooking_methods: List[str]
    flavor_tags: List[str]
    is_vegetarian: bool 
    is_halal: bool
    # --- 核心修正：采纳你的建议，直接使用 'main_ingredient' 作为字段名 ---
    main_ingredient: List[str]

    # 这些字段在运行时由我们的业务逻辑动态添加，并非来自原始数据源
    final_price: Optional[float] = None
    contribution_to_dish_count: Optional[int] = None
    
    class Config:
        # 这个配置允许Pydantic在某些情况下更灵活地处理数据，保留它是个好习惯。
        populate_by_name = True


class MenuRequest(BaseModel):
    """
    定义了客户端发起排菜请求时的JSON结构。
    FastAPI会用它来校验入参。
    """
    restaurant_id: str = Field(..., description="餐厅ID")
    diner_count: int = Field(..., gt=0, description="就餐人数")
    total_budget: float = Field(..., gt=0, description="总预算")
    dietary_restrictions: List[str] = Field([], description="饮食限制, 如: ['VEGETARIAN', 'HALAL', 'NO_SPICY']")


class SimplifiedDish(BaseModel):
    """
    定义了在最终响应中，单个菜品的简化输出格式。
    """
    编号: str = Field(..., alias='dish_id')
    菜品名称: str = Field(..., alias='dish_name')
    单价: float = Field(..., alias='final_price')
    数量: int = Field(..., alias='contribution_to_dish_count')

    class Config:
        populate_by_name = True
        

class MenuResponse(BaseModel):
    """
    定义了最终返回给客户端的整个菜单方案的完整格式。
    """
    菜单评分: float
    总价: float
    菜品总数: int
    菜品列表: List[SimplifiedDish]