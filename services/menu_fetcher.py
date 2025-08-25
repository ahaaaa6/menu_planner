# menu_planner/services/menu_fetcher.py

import logging
from typing import List, Tuple, Set
from ..schemas.menu import Dish, DishInRequest, MenuRequest

logger = logging.getLogger(__name__)

def preprocess_menu(all_dishes_in_request: List[DishInRequest], request: MenuRequest) -> Tuple[List[Dish], str]:
    """对已加载的菜品列表进行业务逻辑过滤和处理。"""
    if not all_dishes_in_request:
        return [], "菜品列表为空，无法进行配餐。"

    all_dishes: List[Dish] = [Dish(**dish.model_dump()) for dish in all_dishes_in_request]

    disliked_ingredients: Set[str] = set()
    disliked_flavors: Set[str] = set()
    disliked_methods: Set[str] = set()

    # 仅当用户提供了偏好信息时，才提取忌口项
    if request.preferences:
        disliked_ingredients = set(request.preferences.main_ingredient.get('dislikes', []))
        disliked_flavors = set(request.preferences.flavor.get('dislikes', []))
        disliked_methods = set(request.preferences.cooking_method.get('dislikes', []))

    filtered_dishes = []
    for dish in all_dishes:
        # 确保进入算法的每一道菜都有一个有效的、正数的价格。
        if not dish.price or dish.price <= 0:
            continue

        # 排除主食和酒水
        if dish.dish_category in ["主食", "酒水"]:
            continue
        
        # 检查忌口主食材
        if disliked_ingredients and not disliked_ingredients.isdisjoint(dish.main_ingredient):
            logger.debug(f"过滤菜品 '{dish.dish_name}' (忌口主食材: {set(dish.main_ingredient).intersection(disliked_ingredients)})")
            continue
            
        # 检查忌口口味
        if disliked_flavors and not disliked_flavors.isdisjoint(dish.flavor_tags):
            logger.debug(f"过滤菜品 '{dish.dish_name}' (忌口口味: {set(dish.flavor_tags).intersection(disliked_flavors)})")
            continue

        # 检查忌口烹饪方式
        if disliked_methods and not disliked_methods.isdisjoint(dish.cooking_methods):
            logger.debug(f"过滤菜品 '{dish.dish_name}' (忌口烹饪方式: {set(dish.cooking_methods).intersection(disliked_methods)})")
            continue

        filtered_dishes.append(dish)

    if not filtered_dishes:
        return [], "抱歉，根据您的忌口或菜品类别过滤后，没有可选择的菜品。"

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