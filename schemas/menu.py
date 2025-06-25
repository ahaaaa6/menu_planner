# menu_planner/schemas/menu.py

from pydantic import BaseModel, Field
from typing import List, Optional, Union, Literal

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
    main_ingredient: List[str]

    final_price: Optional[float] = None
    contribution_to_dish_count: Optional[int] = None
    
    class Config:
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
    ignore_cache: bool = Field(False, description="用于判断是否调取缓存")

    model_config = {
        "json_schema_extra": {
            "example": {
                "restaurant_id": "MZDP",
                "user_id": "user007",
                "diner_count": 6,
                "total_budget": 600,
                "dietary_restrictions": [],
                "ignore_cache": True
            }
        }
    }

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

# --- 新增: 用于异步流程的新模型 ---

class PlanTaskSubmitResponse(BaseModel):
    """
    提交排菜任务后，立即返回的响应。
    """
    task_id: str = Field(..., description="唯一的任务ID")
    status: Literal["PENDING"] = Field("PENDING", description="任务状态")
    result_url: str = Field(..., description="用于查询最终结果的URL")

class PlanResultProcessing(BaseModel):
    """
    当任务还在处理中时，结果查询接口返回的响应。
    """
    task_id: str
    status: Literal["PROCESSING"]

class PlanResultSuccess(BaseModel):
    """
    当任务成功完成时，结果查询接口返回的响应。
    """
    task_id: str
    status: Literal["SUCCESS"]
    result: List[MenuResponse]

class PlanResultError(BaseModel):
    """
    当任务处理失败时，结果查询接口返回的响应。
    """
    task_id: str
    status: Literal["FAILED"]
    error: str

# 使用联合类型，让FastAPI能够根据内容自动选择正确的模型
PlanResultResponse = Union[PlanResultSuccess, PlanResultProcessing, PlanResultError]

class MenuPlanCachedResponse(BaseModel):
    """
    当方案缓存命中时，直接返回的包含多个菜单方案的响应体。
    """
    plans: List[MenuResponse] = Field(..., description="缓存中存储的推荐菜单方案列表")
