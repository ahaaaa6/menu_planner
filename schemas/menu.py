# menu_planner/schemas/menu.py (已更新預設請求範例)

from pydantic import BaseModel, Field
from typing import List, Optional, Union, Literal

class Dish(BaseModel):
    """
    定義單個菜品的資料結構。
    這個模型應該與API返回的JSON對象中的欄位元相匹配。
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

class DishInRequest(BaseModel):
    """定義請求中單個菜品的資料結構，不包含餐廳ID"""
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

class MenuRequest(BaseModel):
    """
    定義了用戶端發起排菜請求時的JSON結構。
    FastAPI會用它來校驗入參。
    """
    diner_count: int = Field(..., gt=0, description="就餐人數")
    total_budget: float = Field(..., gt=0, description="總預算")
    dishes: List[DishInRequest] = Field(..., description="用於配餐的所有可用菜品列表")
    ignore_cache: bool = Field(False, description="是否忽略方案緩存，強制重新計算")

    model_config = {
        "json_schema_extra": {
            # 【核心修改】用 menu.csv 中的菜品更新了整個範例
            "example": {
                "diner_count": 4,
                "total_budget": 200,
                "ignore_cache": True,
                "dishes": [
                    {
                        "dish_id": "D001", "dish_name": "夫妻肺片", "dish_category": "凉菜", "is_signature": True,
                        "unit": "份", "price": 32, "cooking_methods": ["拌"], "flavor_tags": ["辣", "麻"],
                        "is_vegetarian": False, "is_halal": True, "main_ingredient": ["牛肉"]
                    },
                    {
                        "dish_id": "D003", "dish_name": "凉拌木耳", "dish_category": "凉菜", "is_signature": False,
                        "unit": "份", "price": 26, "cooking_methods": ["拌"], "flavor_tags": ["酸", "辣"],
                        "is_vegetarian": True, "is_halal": True, "main_ingredient": ["蔬菜"]
                    },
                    {
                        "dish_id": "D045", "dish_name": "宫保鸡丁", "dish_category": "热菜", "is_signature": False,
                        "unit": "份", "price": 42, "cooking_methods": ["炒"], "flavor_tags": ["辣", "甜", "酸"],
                        "is_vegetarian": False, "is_halal": True, "main_ingredient": ["禽肉"]
                    },
                    {
                        "dish_id": "D046", "dish_name": "麻婆豆腐", "dish_category": "热菜", "is_signature": True,
                        "unit": "份", "price": 28, "cooking_methods": ["烧"], "flavor_tags": ["辣", "鲜"],
                        "is_vegetarian": True, "is_halal": True, "main_ingredient": ["牛肉"]
                    },
                    {
                        "dish_id": "D053", "dish_name": "水煮鱼", "dish_category": "热菜", "is_signature": False,
                        "unit": "份", "price": 78, "cooking_methods": ["煮"], "flavor_tags": ["辣", "麻"],
                        "is_vegetarian": False, "is_halal": True, "main_ingredient": ["水产"]
                    },
                    {
                        "dish_id": "D052", "dish_name": "干煸四季豆", "dish_category": "热菜", "is_signature": False,
                        "unit": "份", "price": 32, "cooking_methods": ["煸"], "flavor_tags": ["辣", "鲜"],
                        "is_vegetarian": True, "is_halal": True, "main_ingredient": ["蔬菜"]
                    },
                    {
                        "dish_id": "D065", "dish_name": "荷塘月色", "dish_category": "热菜", "is_signature": False,
                        "unit": "份", "price": 32, "cooking_methods": ["炒"], "flavor_tags": ["清淡", "鲜"],
                        "is_vegetarian": True, "is_halal": True, "main_ingredient": ["蔬菜"]
                    },
                    {
                        "dish_id": "D153", "dish_name": "番茄鸡蛋汤", "dish_category": "汤品", "is_signature": False,
                        "unit": "份", "price": 18, "cooking_methods": ["煮"], "flavor_tags": ["鲜"],
                        "is_vegetarian": True, "is_halal": True, "main_ingredient": ["蛋类"]
                    },
                    {
                        "dish_id": "D118", "dish_name": "鸡丝凉面", "dish_category": "主食", "is_signature": False,
                        "unit": "份", "price": 28, "cooking_methods": ["拌"], "flavor_tags": ["辣", "酸"],
                        "is_vegetarian": False, "is_halal": True, "main_ingredient": ["禽肉"]
                    },
                    {
                        "dish_id": "D127", "dish_name": "红糖糍粑", "dish_category": "主食", "is_signature": False,
                        "unit": "份", "price": 22, "cooking_methods": ["炸"], "flavor_tags": ["甜"],
                        "is_vegetarian": True, "is_halal": True, "main_ingredient": ["其他"]
                    }
                ]
            }
        }
    }


class SimplifiedDish(BaseModel):
    """
    定義了在最終響應中，單個菜品的簡化輸出格式。
    """
    編號: str = Field(..., alias='dish_id')
    菜品名稱: str = Field(..., alias='dish_name')
    單價: float = Field(..., alias='final_price')
    數量: int = Field(..., alias='contribution_to_dish_count')

    class Config:
        populate_by_name = True


class MenuResponse(BaseModel):
    """
    定義了最終返回給用戶端的整個菜單方案的完整格式。
    """
    菜單評分: float
    總價: float
    菜品總數: int
    菜品清單: List[SimplifiedDish]


class PlanTaskSubmitResponse(BaseModel):
    """
    提交排菜任務後，立即返回的響應。
    """
    task_id: str = Field(..., description="唯一的任務ID")
    status: Literal["PENDING"] = Field("PENDING", description="任務狀態")
    result_url: str = Field(..., description="用於查詢最終結果的URL")

class PlanResultProcessing(BaseModel):
    """
    當任務還在處理中時，結果查詢介面返回的響應。
    """
    task_id: str
    status: Literal["PROCESSING"]

class PlanResultSuccess(BaseModel):
    """
    當任務成功完成時，結果查詢介面返回的響應。
    """
    task_id: str
    status: Literal["SUCCESS"]
    result: List[MenuResponse]

class PlanResultError(BaseModel):
    """
    當任務處理失敗時，結果查詢介面返回的響應。
    """
    task_id: str
    status: Literal["FAILED"]
    error: str

# 使用聯合類型，讓FastAPI能夠根據內容自動選擇正確的模型
PlanResultResponse = Union[PlanResultSuccess, PlanResultProcessing, PlanResultError]

class MenuPlanCachedResponse(BaseModel):
    """
    當方案緩存命中時，直接返回的包含多個菜單方案的響應體。
    """
    plans: List[MenuResponse] = Field(..., description="緩存中儲存的推薦菜單方案列表")