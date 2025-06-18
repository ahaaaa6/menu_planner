import asyncio
import random
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from typing import List, Dict, Any, Tuple

from deap import base, creator, tools, algorithms

from ..core.config import AppConfig
# 修复：导入 SimplifiedDish
from ..schemas.menu import Dish, MenuRequest, MenuResponse, SimplifiedDish

# DEAP 初始化 (无需修改)
# 创建一个最大化适应度的 FitnessMax 类
creator.create("FitnessMax", base.Fitness, weights=(1.0,))
# 创建一个 list 类型的 Individual 类，并关联 FitnessMax
creator.create("Individual", list, fitness=creator.FitnessMax)

def _get_dish_attributes(dishes: List[Dish]) -> Dict[str, Any]:
    """预计算菜品属性，用于遗传算法。"""
    return {
        "prices": [dish.price for dish in dishes],
        "ids": [dish.dish_id for dish in dishes],  # 修复：使用 dish_id 而不是 id
    }

def _repair_individual(individual: List[int], dishes: List[Dish], budget: float) -> List[int]:
    """修复个体，确保不超预算且预算利用率不低于80%，同时保持多样性"""
    selected_indices = [i for i, bit in enumerate(individual) if bit == 1]
    
    if not selected_indices:
        return individual
    
    # 计算当前总价
    total_price = sum(dishes[i].price for i in selected_indices)
    min_budget_required = budget * 0.8  # 最低预算利用率80%
    
    # 如果超预算，优先移除价格最高的菜品（保留多样性）
    while total_price > budget and selected_indices:
        # 按价格排序，移除最贵的菜品
        selected_indices.sort(key=lambda i: dishes[i].price, reverse=True)
        remove_idx = selected_indices[0]
        individual[remove_idx] = 0
        selected_indices.remove(remove_idx)
        total_price -= dishes[remove_idx].price
    
    # 如果预算利用率低于80%，智能添加菜品
    if total_price < min_budget_required:
        available_indices = [i for i in range(len(dishes)) if individual[i] == 0]
        remaining_budget = budget - total_price
        needed_amount = min_budget_required - total_price
        
        # 多种添加策略，增加随机性
        if random.random() < 0.5:
            # 策略1：优先添加能最大化预算利用率的菜品
            available_indices.sort(key=lambda i: dishes[i].price, reverse=True)
        else:
            # 策略2：平衡价格和多样性
            def diversity_score(dish_idx):
                dish = dishes[dish_idx]
                return (dish.price * 0.4 + 
                       len(dish.cooking_methods) * 8 + 
                       len(dish.flavor_tags) * 6 + 
                       len(dish.main_ingredient) * 4 +
                       (20 if dish.is_signature else 0))
            
            available_indices.sort(key=diversity_score, reverse=True)
        
        for dish_idx in available_indices:
            if (total_price + dishes[dish_idx].price <= budget and
                dishes[dish_idx].price <= remaining_budget):
                individual[dish_idx] = 1
                total_price += dishes[dish_idx].price
                remaining_budget -= dishes[dish_idx].price
                
                # 如果达到了最低预算要求，随机决定是否继续添加
                if total_price >= min_budget_required:
                    if random.random() < 0.3:  # 30%概率继续添加以提高预算利用率
                        continue
                    else:
                        break
    
    return individual

def _create_valid_individual(dishes: List[Dish], request: MenuRequest, config: AppConfig) -> List[int]:
    """创建符合预算约束的个体，平衡预算利用率和多样性"""
    individual = [0] * len(dishes)
    available_budget = request.total_budget
    min_budget_required = request.total_budget * 0.8  # 最低预算利用率80%
    
    selected_count = 0
    ideal_count = request.diner_count + config.ga.dish_count_add_on
    max_count = int(ideal_count * 1.5)  # 不超过理想数量的1.5倍
    current_total = 0
    
    # 使用多种策略来创建个体，增加多样性
    strategy = random.choice(['high_price_first', 'balanced', 'random_fill'])
    
    if strategy == 'high_price_first':
        # 策略1：优先选择高价菜品
        dish_indices = list(range(len(dishes)))
        dish_indices.sort(key=lambda i: dishes[i].price, reverse=True)
    elif strategy == 'balanced':
        # 策略2：价格和多样性平衡
        dish_indices = list(range(len(dishes)))
        # 根据价格和多样性指标排序
        dish_indices.sort(key=lambda i: (
            dishes[i].price * 0.6 + 
            len(dishes[i].cooking_methods) * 10 + 
            len(dishes[i].flavor_tags) * 5 + 
            (50 if dishes[i].is_signature else 0)
        ), reverse=True)
    else:
        # 策略3：完全随机
        dish_indices = list(range(len(dishes)))
        random.shuffle(dish_indices)
    
    # 第一阶段：按策略选择菜品
    for dish_idx in dish_indices:
        if (dishes[dish_idx].price <= available_budget and 
            selected_count < max_count):
            individual[dish_idx] = 1
            available_budget -= dishes[dish_idx].price
            current_total += dishes[dish_idx].price
            selected_count += 1
            
            # 如果已达到预算上限的95%，停止添加
            if current_total >= request.total_budget * 0.95:
                break
    
    # 第二阶段：确保达到最低预算要求
    if current_total < min_budget_required:
        remaining_dishes = [i for i in range(len(dishes)) if individual[i] == 0]
        # 按价格排序，优先添加能快速达到预算要求的菜品
        remaining_dishes.sort(key=lambda i: dishes[i].price, reverse=True)
        
        for dish_idx in remaining_dishes:
            if (dishes[dish_idx].price <= available_budget and 
                selected_count < max_count and
                current_total + dishes[dish_idx].price <= request.total_budget):
                individual[dish_idx] = 1
                available_budget -= dishes[dish_idx].price
                current_total += dishes[dish_idx].price
                selected_count += 1
                
                if current_total >= min_budget_required:
                    break
    
    return individual

def _evaluate_menu(individual: List[int], dishes: List[Dish], request: MenuRequest, config: AppConfig) -> Tuple[float]:
    """
    评估函数，用于计算一个菜单（individual）的适应度分数。
    这是遗传算法的核心。
    """
    selected_dishes = [dishes[i] for i, bit in enumerate(individual) if bit == 1]

    if not selected_dishes:
        return (0,)

    total_price = sum(d.price for d in selected_dishes)

    # 硬性约束：如果总价超过预算，适应度为0
    if total_price > request.total_budget:
        return (0,)
    
    # 硬性约束：预算利用率不能低于80%
    budget_utilization = total_price / request.total_budget if request.total_budget > 0 else 0
    if budget_utilization < 0.8:
        return (0,)

    num_people = request.diner_count
    
    # --- 软性约束评分 ---

    # 1. 价格得分：菜单总价越接近预算的100%，得分越高
    if request.total_budget == 0:
        price_score = 1.0 if total_price == 0 else 0.0
    else:
        # 预算利用率越接近100%，得分越高
        price_score = budget_utilization

    # 2. 菜品数量得分：菜品数越接近"人数+N"，得分越高
    ideal_dish_count = num_people + config.ga.dish_count_add_on
    if ideal_dish_count == 0:
        dish_count_score = 1.0 if not selected_dishes else 0.0
    else:
        dish_count_score = 1.0 - (abs(len(selected_dishes) - ideal_dish_count) / ideal_dish_count)

    # 3. 多样性得分
    all_cooking_methods = [method for d in selected_dishes for method in d.cooking_methods]
    all_flavors = [flavor for d in selected_dishes for flavor in d.flavor_tags]
    all_main_ingredients = [ing for d in selected_dishes for ing in d.main_ingredient]

    cooking_style_variety = len(set(all_cooking_methods))
    flavor_variety = len(set(all_flavors))
    main_ingredient_variety = len(set(all_main_ingredients))
    
    if len(selected_dishes) > 0:
        variety_score = (cooking_style_variety + flavor_variety + main_ingredient_variety) / (len(selected_dishes) * 3)
    else:
        variety_score = 0
        
    # 4. 荤素搭配得分
    num_meat = sum(1 for d in selected_dishes if not d.is_vegetarian)
    num_veg = len(selected_dishes) - num_meat
    if len(selected_dishes) > 0:
        balance_score = 1.0 - abs(num_meat - num_veg) / len(selected_dishes)
    else:
        balance_score = 0

    # 5. 高价值菜品得分 - 使用招牌菜作为高价值菜品的指标
    high_value_count = sum(1 for d in selected_dishes if d.is_signature)
    if len(selected_dishes) > 0:
        high_value_score = high_value_count / len(selected_dishes)
    else:
        high_value_score = 0.0

    # 最终加权总分
    final_score = (
        price_score * config.ga.weight_price +
        dish_count_score * config.ga.weight_dish_count +
        variety_score * config.ga.weight_variety +
        balance_score * config.ga.weight_balance +
        high_value_score * config.ga.weight_high_value
    ) * 100

    return (max(0, final_score),)

def _calculate_menu_difference(menu1: List[int], menu2: List[int], dishes: List[Dish]) -> float:
    """
    计算两个菜单之间的差异度
    差异度基于：
    1. 不同菜品的数量
    2. 不同烹饪方法的数量
    3. 不同口味标签的数量
    4. 不同主要食材的数量
    5. 价格差异
    """
    selected_dishes_1 = [dishes[i] for i, bit in enumerate(menu1) if bit == 1]
    selected_dishes_2 = [dishes[i] for i, bit in enumerate(menu2) if bit == 1]
    
    if not selected_dishes_1 or not selected_dishes_2:
        return 0.0
    
    # 1. 菜品差异 - 不同菜品的比例
    dishes_1 = set(d.dish_id for d in selected_dishes_1)
    dishes_2 = set(d.dish_id for d in selected_dishes_2)
    dish_difference = len(dishes_1.symmetric_difference(dishes_2)) / len(dishes_1.union(dishes_2))
    
    # 2. 烹饪方法差异
    cooking_methods_1 = set(method for d in selected_dishes_1 for method in d.cooking_methods)
    cooking_methods_2 = set(method for d in selected_dishes_2 for method in d.cooking_methods)
    cooking_difference = len(cooking_methods_1.symmetric_difference(cooking_methods_2)) / max(len(cooking_methods_1.union(cooking_methods_2)), 1)
    
    # 3. 口味标签差异
    flavors_1 = set(flavor for d in selected_dishes_1 for flavor in d.flavor_tags)
    flavors_2 = set(flavor for d in selected_dishes_2 for flavor in d.flavor_tags)
    flavor_difference = len(flavors_1.symmetric_difference(flavors_2)) / max(len(flavors_1.union(flavors_2)), 1)
    
    # 4. 主要食材差异
    ingredients_1 = set(ing for d in selected_dishes_1 for ing in d.main_ingredient)
    ingredients_2 = set(ing for d in selected_dishes_2 for ing in d.main_ingredient)
    ingredient_difference = len(ingredients_1.symmetric_difference(ingredients_2)) / max(len(ingredients_1.union(ingredients_2)), 1)
    
    # 5. 价格差异（标准化）
    price_1 = sum(d.price for d in selected_dishes_1)
    price_2 = sum(d.price for d in selected_dishes_2)
    price_difference = abs(price_1 - price_2) / max(price_1 + price_2, 1)
    
    # 综合差异度（加权平均）
    total_difference = (
        dish_difference * 0.4 +          # 菜品差异权重最高
        cooking_difference * 0.2 +       # 烹饪方法差异
        flavor_difference * 0.2 +        # 口味差异
        ingredient_difference * 0.15 +   # 食材差异
        price_difference * 0.05          # 价格差异权重最低
    )
    
    return total_difference

def _select_two_diverse_menus(hall_of_fame: tools.HallOfFame, dishes: List[Dish]) -> List[tools.HallOfFame]:
    """
    从名人堂中选择两个差异最大的菜单
    """
    if len(hall_of_fame) <= 1:
        return list(hall_of_fame)
    
    if len(hall_of_fame) == 2:
        return list(hall_of_fame)
    
    max_difference = 0
    best_pair = (hall_of_fame[0], hall_of_fame[1])
    
    # 遍历所有可能的菜单对，找到差异最大的一对
    for i in range(len(hall_of_fame)):
        for j in range(i + 1, len(hall_of_fame)):
            difference = _calculate_menu_difference(hall_of_fame[i], hall_of_fame[j], dishes)
            if difference > max_difference:
                max_difference = difference
                best_pair = (hall_of_fame[i], hall_of_fame[j])
    
    return list(best_pair)

def _run_ga_blocking(dishes: List[Dish], request: MenuRequest, config: AppConfig) -> tools.HallOfFame:
    """
    在阻塞模式下运行遗传算法。
    此函数设计为在单独的进程中运行。
    """
    dish_attributes = _get_dish_attributes(dishes)
    num_dishes = len(dishes)

    toolbox = base.Toolbox()
    
    # 修改：使用自定义个体生成函数，而不是随机生成
    def create_individual():
        return creator.Individual(_create_valid_individual(dishes, request, config))
    
    toolbox.register("individual", create_individual)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    # 修改：添加修复的评估函数
    def evaluate_and_repair(individual):
        # 先修复个体
        repaired = _repair_individual(individual[:], dishes, request.total_budget)
        individual[:] = repaired  # 更新原个体
        return _evaluate_menu(individual, dishes, request, config)
    
    # 注册遗传算子
    toolbox.register("evaluate", evaluate_and_repair)
    toolbox.register("mate", tools.cxTwoPoint)
    toolbox.register("mutate", tools.mutFlipBit, indpb=config.ga.mutation_rate)
    toolbox.register("select", tools.selTournament, tournsize=3)

    # 修改：自定义交叉算子，交叉后进行修复
    def crossover_and_repair(ind1, ind2):
        tools.cxTwoPoint(ind1, ind2)
        ind1[:] = _repair_individual(ind1[:], dishes, request.total_budget)
        ind2[:] = _repair_individual(ind2[:], dishes, request.total_budget)
        return ind1, ind2
    
    # 修改：自定义变异算子，变异后进行修复
    def mutate_and_repair(individual):
        tools.mutFlipBit(individual, indpb=config.ga.mutation_rate)
        individual[:] = _repair_individual(individual[:], dishes, request.total_budget)
        return individual,
    
    # 重新注册修复后的算子
    toolbox.register("mate", crossover_and_repair)
    toolbox.register("mutate", mutate_and_repair)

    # 其余代码保持不变
    population = toolbox.population(n=config.ga.population_size)
    hall_of_fame = tools.HallOfFame(config.ga.hall_of_fame_size)

    print(f"开始为餐厅 {request.restaurant_id} 执行遗传算法...")

    stats = tools.Statistics(lambda ind: ind.fitness.values[0])  # 注意这里也要修改
    stats.register("avg", lambda x: round(sum(x) / len(x), 2))
    stats.register("max", lambda x: round(max(x), 2))

    algorithms.eaSimple(
        population,
        toolbox,
        cxpb=config.ga.crossover_rate,
        mutpb=config.ga.mutation_rate,
        ngen=config.ga.generations,
        stats=stats,
        halloffame=hall_of_fame,
        verbose=True
    )

    print(f"遗传算法执行完毕。名人堂中有 {len(hall_of_fame)} 个最优解。")
    return hall_of_fame

async def plan_menu_async(
    process_pool: ProcessPoolExecutor,  # 修复：参数名称
    dishes: List[Dish],
    request: MenuRequest,
    config: AppConfig,  # 修复：添加配置参数
) -> List[MenuResponse]:
    """
    异步接口，用于规划菜单。
    它将计算密集型的遗传算法任务提交到进程池中执行。
    修改：仅返回两个差异最大的菜单，菜单评分精确到小数点后2位，
    预算利用率必须不低于80%。
    """
    loop = asyncio.get_event_loop()
    
    hall_of_fame = await loop.run_in_executor(
        process_pool,
        _run_ga_blocking,
        dishes,
        request,
        config
    )

    # 修改：过滤掉预算利用率低于80%的菜单
    if not hall_of_fame:
        return []
    
    # 过滤符合预算利用率要求的菜单
    valid_menus = []
    for individual in hall_of_fame:
        selected_dishes = [dishes[i] for i, selected in enumerate(individual) if selected]
        if selected_dishes:
            total_price = sum(dish.price for dish in selected_dishes)
            budget_utilization = total_price / request.total_budget if request.total_budget > 0 else 0
            if budget_utilization >= 0.8:  # 预算利用率不低于80%
                valid_menus.append(individual)
    
    if not valid_menus:
        print("警告：没有找到预算利用率不低于80%的菜单方案")
        return []
    
    # 从符合要求的菜单中选择两个差异最大的菜单
    if len(valid_menus) <= 2:
        selected_menus = valid_menus
    else:
        # 如果有足够多的候选菜单，选择差异最大的两个
        # 创建临时名人堂用于选择
        temp_hall_of_fame = tools.HallOfFame(len(valid_menus))
        for menu in valid_menus:
            temp_hall_of_fame.insert(menu)
        selected_menus = _select_two_diverse_menus(temp_hall_of_fame, dishes)
        
        # 如果选出的两个菜单差异度太低，尝试其他组合
        if len(selected_menus) == 2:
            current_difference = _calculate_menu_difference(selected_menus[0], selected_menus[1], dishes)
            if current_difference < 0.3:  # 如果差异度低于30%，尝试找更好的组合
                print(f"当前菜单差异度较低 ({current_difference:.2%})，尝试寻找更好的组合...")
                
                # 尝试从更多候选中找到差异更大的组合
                best_difference = current_difference
                best_pair = selected_menus
                
                # 检查前10个候选菜单的所有组合
                check_count = min(10, len(valid_menus))
                for i in range(check_count):
                    for j in range(i + 1, check_count):
                        diff = _calculate_menu_difference(valid_menus[i], valid_menus[j], dishes)
                        if diff > best_difference:
                            best_difference = diff
                            best_pair = [valid_menus[i], valid_menus[j]]
                
                selected_menus = best_pair
                print(f"找到更好的组合，差异度: {best_difference:.2%}")
    
    menu_responses: List[MenuResponse] = []

    # 遍历选中的菜单
    for individual in selected_menus:
        # 从 0/1 列表中重建菜品列表
        selected_dishes = [dishes[i] for i, selected in enumerate(individual) if selected]

        if not selected_dishes:
            continue

        # 适应度分数 - 修改：精确到小数点后2位
        score = round(individual.fitness.values[0], 2)
        # 计算总价和预算利用率
        total_price = sum(dish.price for dish in selected_dishes)
        budget_utilization = round(total_price / request.total_budget * 100, 1) if request.total_budget > 0 else 0

        # 修复：正确转换为 SimplifiedDish 列表
        simplified_dishes = [
            SimplifiedDish(
                dish_id=dish.dish_id,
                dish_name=dish.dish_name,
                final_price=dish.price,
                contribution_to_dish_count=1
            )
            for dish in selected_dishes
        ]

        # 修复：使用转换后的 SimplifiedDish 列表
        response = MenuResponse(
            菜单评分=score,
            总价=total_price,
            菜品总数=len(selected_dishes),
            菜品列表=simplified_dishes,
        )
        menu_responses.append(response)

    print(f"已选择 {len(menu_responses)} 个差异最大且预算利用率≥80%的菜单方案")
    for i, response in enumerate(menu_responses):
        budget_util = round(response.总价 / request.total_budget * 100, 1) if request.total_budget > 0 else 0
        print(f"菜单 {i+1}: 预算利用率 {budget_util}%, 评分 {response.菜单评分}")
    
   # 如果返回两个菜单，计算并显示差异度
    if len(menu_responses) == 2:
        # 从菜单响应中获取菜品ID集合 - 尝试不同的字段名
        try:
            # 尝试 dish_id 字段
            menu1_dish_ids = set(getattr(d, 'dish_id', None) for d in menu_responses[0].菜品列表)
            menu2_dish_ids = set(getattr(d, 'dish_id', None) for d in menu_responses[1].菜品列表)
        except:
            # 如果失败，尝试其他可能的字段名
            try:
                menu1_dish_ids = set(d.id for d in menu_responses[0].菜品列表)
                menu2_dish_ids = set(d.id for d in menu_responses[1].菜品列表)
            except:
                # 如果还是失败，打印对象属性和内容
                first_dish = menu_responses[0].菜品列表[0]
                print(f"SimplifiedDish 对象属性: {[attr for attr in dir(first_dish) if not attr.startswith('_')]}")
                print(f"SimplifiedDish 对象内容: {first_dish}")
                if hasattr(first_dish, '__dict__'):
                    print(f"SimplifiedDish __dict__: {first_dish.__dict__}")
                print("无法计算菜单差异度")
                return menu_responses
        
        # 移除 None 值
        menu1_dish_ids.discard(None)
        menu2_dish_ids.discard(None)
        
        if menu1_dish_ids and menu2_dish_ids:
            # 重建二进制表示用于差异度计算
            menu1_dishes = [1 if dish.dish_id in menu1_dish_ids else 0 for dish in dishes]
            menu2_dishes = [1 if dish.dish_id in menu2_dish_ids else 0 for dish in dishes]
            
            final_difference = _calculate_menu_difference(menu1_dishes, menu2_dishes, dishes)
            print(f"最终菜单差异度: {final_difference:.2%}")
        else:
            print("无法获取菜品ID，跳过差异度计算")
    
    return menu_responses