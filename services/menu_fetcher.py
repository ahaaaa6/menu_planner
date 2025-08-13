# menu_planner/services/menu_fetcher.py (修正版)

import logging
from typing import List, Tuple

# 确保导入了 Dish 和 DishInRequest 两个模型
from ..schemas.menu import Dish, DishInRequest, MenuRequest

logger = logging.getLogger(__name__)

# 函数签名接收 DishInRequest 列表
def preprocess_menu(all_dishes_in_request: List[DishInRequest], request: MenuRequest) -> Tuple[List[Dish], str]:
    """对已加载的菜品列表进行业务逻辑过滤和处理。"""
    if not all_dishes_in_request:
        return [], "菜品列表为空，无法进行配餐。"

    # 在转换时，为 restaurant_id 赋一个默认值，因为它在后续逻辑中不被使用
    all_dishes: List[Dish] = [
        Dish(restaurant_id="N/A", **dish.model_dump()) for dish in all_dishes_in_request
    ]

    filtered_dishes = []
    for dish in all_dishes:
        # 确保进入算法的每一道菜都有一个有效的、正数的价格。
        if not dish.price or dish.price <= 0:
            continue

        # 排除主食和酒水
        if dish.dish_category in ["主食", "酒水"]:
            logger.info(f"过滤掉菜品 '{dish.dish_name}'，因为其类别是 '{dish.dish_category}'。")
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