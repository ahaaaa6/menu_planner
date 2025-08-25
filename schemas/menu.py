# menu_planner/schemas/menu.py 

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Union, Literal, Dict

class DinerBreakdown(BaseModel):
    """就餐人员分类"""
    male_adults: int = Field(0, ge=0, description="成人男性数量")
    female_adults: int = Field(0, ge=0, description="成人女性数量")
    children: int = Field(0, ge=0, description="儿童数量")

class Preferences(BaseModel):
    """主食材、口味、烹饪方式偏好"""
    main_ingredient: Dict[str, List[str]] = Field({}, description="主食材偏好, e.g., {'likes': ['牛肉'], 'dislikes': ['猪肉']}")
    flavor: Dict[str, List[str]] = Field({}, description="口味偏好, e.g., {'likes': ['辣', '麻'], 'dislikes': ['苦']}")
    cooking_method: Dict[str, List[str]] = Field({}, description="烹饪方式偏好, e.g., {'likes': ['炒'], 'dislikes': ['炸']}")


class DishInRequest(BaseModel):
    """定义请求中单个菜品的数据结构，不包含餐厅ID"""
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
    applicable_people: str = Field("全部", description="适用人群 (单选), 可选值: '男性友好', '女性友好', '儿童友好', '全部'")


class MenuRequest(BaseModel):
    """
    定义了客户端发起排菜请求时的JSON结构。
    FastAPI会用它来校验入参。
    """
    diner_count: int = Field(..., gt=0, description="总就餐人数")
    total_budget: float = Field(..., gt=0, description="总预算")
    dishes: List[DishInRequest] = Field(..., description="用于配餐的所有可用菜品列表")
    ignore_cache: bool = Field(False, description="是否忽略方案缓存，强制重新计算")
    diner_breakdown: Optional[DinerBreakdown] = Field(None, description="就餐人员详细分类 (可选)")
    preferences: Optional[Preferences] = Field(None, description="各类偏好 (可选)")

    @validator('diner_breakdown', always=True)
    def total_diners_must_match_breakdown(cls, v, values):
        if v and 'diner_count' in values:
            diner_count = values['diner_count']
            total = v.male_adults + v.female_adults + v.children
            if diner_count != total:
                raise ValueError(f"总就餐人数 ({diner_count}) 与详细分类的总和 ({total}) 不匹配")
        return v
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "diner_count": 4,
                "diner_breakdown": {"male_adults": 2, "female_adults": 2, "children": 0},
                "total_budget": 300,
                "preferences": {
                    "main_ingredient": {"likes": ["牛肉", "蔬菜"], "dislikes": ["猪肉"]},
                    "flavor": {"likes": ["辣", "麻"], "dislikes": []},
                    "cooking_method": {"likes": ["炒", "烧"], "dislikes": ["炸"]}
                },
                "ignore_cache": True,
                "dishes": [
                     {
                        "dish_id": "D001", "dish_name": "夫妻肺片", "dish_category": "凉菜", "is_signature": True,
                        "unit": "份", "price": 32, "cooking_methods": ["拌"], "flavor_tags": ["辣", "麻"],
                        "is_vegetarian": False, "is_halal": True, "main_ingredient": ["牛肉"],
                        "applicable_people": "男性友好"
                    },
                    {
                        "dish_id": "D003", "dish_name": "凉拌木耳", "dish_category": "凉菜", "is_signature": False,
                        "unit": "份", "price": 26, "cooking_methods": ["拌"], "flavor_tags": ["酸", "辣"],
                        "is_vegetarian": True, "is_halal": True, "main_ingredient": ["蔬菜"],
                        "applicable_people": "全部"
                    },
                    {
                        "dish_id": "D045", "dish_name": "宫保鸡丁", "dish_category": "热菜", "is_signature": False,
                        "unit": "份", "price": 42, "cooking_methods": ["炒"], "flavor_tags": ["辣", "甜", "酸"],
                        "is_vegetarian": False, "is_halal": True, "main_ingredient": ["禽肉"],
                        "applicable_people": "全部"
                    },
                    {
                        "dish_id": "D046", "dish_name": "麻婆豆腐", "dish_category": "热菜", "is_signature": True,
                        "unit": "份", "price": 28, "cooking_methods": ["烧"], "flavor_tags": ["辣", "鲜"],
                        "is_vegetarian": True, "is_halal": True, "main_ingredient": ["牛肉"],
                        "applicable_people": "男性友好"
                    },
                    {
                        "dish_id": "D053", "dish_name": "水煮鱼", "dish_category": "热菜", "is_signature": False,
                        "unit": "份", "price": 78, "cooking_methods": ["煮"], "flavor_tags": ["辣", "麻"],
                        "is_vegetarian": False, "is_halal": True, "main_ingredient": ["水产"],
                        "applicable_people": "女性友好"
                    },
                    {
                        "dish_id": "D052", "dish_name": "干煸四季豆", "dish_category": "热菜", "is_signature": False,
                        "unit": "份", "price": 32, "cooking_methods": ["煸"], "flavor_tags": ["辣", "鲜"],
                        "is_vegetarian": True, "is_halal": True, "main_ingredient": ["蔬菜"],
                        "applicable_people": "全部"
                    },
                    {
                        "dish_id": "D065", "dish_name": "荷塘月色", "dish_category": "热菜", "is_signature": False,
                        "unit": "份", "price": 32, "cooking_methods": ["炒"], "flavor_tags": ["清淡", "鲜"],
                        "is_vegetarian": True, "is_halal": True, "main_ingredient": ["蔬菜"],
                        "applicable_people": "女性友好"
                    },
                    {
                        "dish_id": "D153", "dish_name": "番茄鸡蛋汤", "dish_category": "汤品", "is_signature": False,
                        "unit": "份", "price": 18, "cooking_methods": ["煮"], "flavor_tags": ["鲜"],
                        "is_vegetarian": True, "is_halal": True, "main_ingredient": ["蛋类"],
                        "applicable_people": "儿童友好"
                    },
                    {
                        "dish_id": "D118", "dish_name": "鸡丝凉面", "dish_category": "主食", "is_signature": False,
                        "unit": "份", "price": 28, "cooking_methods": ["拌"], "flavor_tags": ["辣", "酸"],
                        "is_vegetarian": False, "is_halal": True, "main_ingredient": ["禽肉"],
                        "applicable_people": "全部"
                    },
                    {
                        "dish_id": "D127", "dish_name": "红糖糍粑", "dish_category": "主食", "is_signature": False,
                        "unit": "份", "price": 22, "cooking_methods": ["炸"], "flavor_tags": ["甜"],
                        "is_vegetarian": True, "is_halal": True, "main_ingredient": ["其他"],
                        "applicable_people": "儿童友好"
                    }
                ]
            }
        }
    }


class Dish(DishInRequest):
    """
    定义内部使用的完整菜品数据结构
    """
    restaurant_id: str = "N/A"
    final_price: Optional[float] = None
    contribution_to_dish_count: Optional[int] = None


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
    菜品清单: List[SimplifiedDish]

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

PlanResultResponse = Union[PlanResultSuccess, PlanResultProcessing, PlanResultError]

class MenuPlanCachedResponse(BaseModel):
    """
    当方案缓存命中时，直接返回的包含多个菜单方案的响应体。
    """
    plans: List[MenuResponse] = Field(..., description="缓存中存储的推荐菜单方案列表")