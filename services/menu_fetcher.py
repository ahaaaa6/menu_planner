import json
import logging
from typing import List, Tuple, Any
from pydantic import ValidationError

from menu_planner.schemas.menu import Dish, MenuRequest
from menu_planner.core.config import settings
from menu_planner.core.cache import redis_manager
from menu_planner.services.api_client import fetch_dishes_from_external_api

logger = logging.getLogger(__name__)

# 辅助解析函数 
def parse_bool_from_api(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().upper() in ['TRUE', '1', '是', 'YES']


def parse_list_from_api(value: Any) -> List[str]:
    # 如果输入值本身就是None或者转换成字符串后为空，直接返回空列表
    if not value:
        return []
    # 确保只处理字符串类型
    s_value = str(value)
    items = [item.strip() for item in s_value.split(',') if item.strip()]
    return items

# get_dishes_for_restaurant 函数 
async def get_dishes_for_restaurant(restaurant_id: str) -> List[Dish]:
    cache_key = f"dishes:{restaurant_id}"
    
    try:
        async with redis_manager.get_connection() as redis:
            cached_dishes_json = await redis.get(cache_key)
        
        if cached_dishes_json:
            logger.info(f"CACHE HIT: 命中缓存 for restaurant '{restaurant_id}'")
            dishes_data = json.loads(cached_dishes_json)
        else:
            logger.info(f"CACHE MISS: 未命中缓存 for restaurant '{restaurant_id}', 将调用API。")
            dishes_data = await fetch_dishes_from_external_api(restaurant_id)
            
            if dishes_data:
                async with redis_manager.get_connection() as redis:
                    await redis.set(cache_key, json.dumps(dishes_data), ex=settings.redis.menu_cache_ttl_seconds)
    except Exception as e:
        logger.error(f"获取或设置缓存时出错: {e}, 将尝试直接调用API。")
        dishes_data = await fetch_dishes_from_external_api(restaurant_id)

    if not dishes_data:
        return []

    validated_dishes: List[Dish] = []
    for i, dish_data in enumerate(dishes_data, 1):
        try:
            parsed_data = {
                **dish_data,
                'is_signature': parse_bool_from_api(dish_data.get('is_signature')),
                'is_halal': parse_bool_from_api(dish_data.get('is_halal')),
                'is_vegetarian': parse_bool_from_api(dish_data.get('meat_veg_tag')),
                'cooking_methods': parse_list_from_api(dish_data.get('cooking_methods')),
                'flavor_tags': parse_list_from_api(dish_data.get('flavor_tags')),
                'main_ingredient': parse_list_from_api(dish_data.get('main_ingredient')),
            }
            validated_dishes.append(Dish.model_validate(parsed_data))
        except ValidationError as e:
            logger.warning(f"⚠️ [API数据校验失败] 第 {i} 条菜品数据无效. 原始数据: {dish_data}. 错误: {e}")
            continue
            
    if validated_dishes:
        logger.info(f"✅ 成功加载并验证通过 {len(validated_dishes)} 道菜品 for restaurant '{restaurant_id}'")
    else:
        logger.warning(f"🚨 所有从API获取的菜品都未能通过数据校验 for restaurant '{restaurant_id}'")
        
    return validated_dishes

# --- 核心修正：重构 preprocess_menu 函数 ---
def preprocess_menu(all_dishes: List[Dish], request: MenuRequest) -> Tuple[List[Dish], str]:
    """对已加载的菜品列表进行业务逻辑过滤和处理。"""
    if not all_dishes:
        return [], "餐厅菜单为空或所有菜品均未通过数据校验。"
    
    filtered_dishes = []
    for dish in all_dishes:
        # --- 新增核心修正：过滤掉无效价格的菜品 ---
        # 确保进入算法的每一道菜都有一个有效的、正数的价格。
        if not dish.price or dish.price <= 0:
            continue

        # 排除主食和甜品，但保留汤品用于后续处理
        if dish.dish_category in ["主食", "甜品"]:
            continue
        if "VEGETARIAN" in request.dietary_restrictions and not dish.is_vegetarian:
            continue
        if "HALAL" in request.dietary_restrictions and not dish.is_halal:
            continue
        if "NO_SPICY" in request.dietary_restrictions and any(f in dish.flavor_tags for f in ["辣", "麻"]):
            continue
        filtered_dishes.append(dish)

    if not filtered_dishes:
        return [], "抱歉，根据您的忌口信息，没有可选择的菜品。"

    # 在过滤后的列表上，为所有菜品设置运行时属性
    for dish in filtered_dishes:
        dish.final_price = dish.price
        dish.contribution_to_dish_count = 1

    # 预算合理性检查
    min_price = min((d.price for d in filtered_dishes if d.price > 0), default=0)
    if not min_price:
         return [], "所有可用菜品价格均为0，无法进行预算规划。"
    per_person_budget = request.total_budget / request.diner_count
    if per_person_budget < min_price:
        return [], f"您的 {request.total_budget}元 预算对于 {request.diner_count}人 来说过低，人均预算不足以购买最便宜的菜品（{min_price}元）。"
        
    return filtered_dishes, ""