import asyncio
import random
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from typing import List, Dict, Any, Tuple

from deap import base, creator, tools, algorithms

from ..core.config import AppConfig
from ..schemas.menu import Dish, MenuRequest, MenuResponse, SimplifiedDish

# DEAP 初始化
creator.create("FitnessMax", base.Fitness, weights=(1.0,))
creator.create("Individual", list, fitness=creator.FitnessMax)

def _get_dish_attributes(dishes: List[Dish]) -> Dict[str, Any]:
    """预计算菜品属性，用于遗传算法。"""
    return {
        "prices": [dish.price for dish in dishes],
        "ids": [dish.dish_id for dish in dishes],
    }

def _calculate_menu_difference(menu1: List[int], menu2: List[int], dishes: List[Dish]) -> float:
    """计算两个菜单之间的差异度"""
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
        dish_difference * 0.4 +
        cooking_difference * 0.2 +
        flavor_difference * 0.2 +
        ingredient_difference * 0.15 +
        price_difference * 0.05
    )
    
    return total_difference

class DiversityHallOfFame:
    """
    自定义名人堂类，内置差异性考虑
    确保存储的解决方案不仅质量高，而且彼此之间差异明显
    """
    def __init__(self, maxsize: int, dishes: List[Dish], min_difference_threshold: float = 0.3):
        self.maxsize = maxsize
        self.dishes = dishes
        self.min_difference_threshold = min_difference_threshold
        self.items = []
    
    def insert(self, item):
        """插入新的个体，考虑适应度和差异性"""
        # 如果名人堂未满，检查是否与现有解决方案有足够差异
        if len(self.items) < self.maxsize:
            if self._is_sufficiently_different(item):
                self.items.append(item)
                self.items.sort(key=lambda x: x.fitness.values[0], reverse=True)
                return True
            elif len(self.items) == 0:  # 第一个解决方案总是被接受
                self.items.append(item)
                return True
        else:
            # 名人堂已满，检查新解决方案是否值得替换现有解决方案
            worst_fitness = min(ind.fitness.values[0] for ind in self.items)
            
            # 如果新解决方案的适应度比最差的好，且与其他解决方案有足够差异
            if (item.fitness.values[0] > worst_fitness and 
                self._is_sufficiently_different(item)):
                
                # 移除适应度最低的解决方案
                worst_idx = min(range(len(self.items)), 
                              key=lambda i: self.items[i].fitness.values[0])
                self.items.pop(worst_idx)
                self.items.append(item)
                self.items.sort(key=lambda x: x.fitness.values[0], reverse=True)
                return True
        
        return False
    
    def _is_sufficiently_different(self, new_item) -> bool:
        """检查新解决方案是否与现有解决方案有足够差异"""
        if not self.items:
            return True
        
        for existing_item in self.items:
            difference = _calculate_menu_difference(new_item, existing_item, self.dishes)
            if difference < self.min_difference_threshold:
                return False
        
        return True
    
    def __len__(self):
        return len(self.items)
    
    def __iter__(self):
        return iter(self.items)
    
    def __getitem__(self, index):
        return self.items[index]

def _repair_individual(individual: List[int], dishes: List[Dish], budget: float) -> List[int]:
    """修复个体，确保不超预算且预算利用率不低于80%，同时保持多样性"""
    selected_indices = [i for i, bit in enumerate(individual) if bit == 1]
    
    if not selected_indices:
        return individual
    
    total_price = sum(dishes[i].price for i in selected_indices)
    min_budget_required = budget * 0.8
    
    # 如果超预算，优先移除价格最高的菜品
    while total_price > budget and selected_indices:
        selected_indices.sort(key=lambda i: dishes[i].price, reverse=True)
        remove_idx = selected_indices[0]
        individual[remove_idx] = 0
        selected_indices.remove(remove_idx)
        total_price -= dishes[remove_idx].price
    
    # 如果预算利用率低于80%，智能添加菜品
    if total_price < min_budget_required:
        available_indices = [i for i in range(len(dishes)) if individual[i] == 0]
        remaining_budget = budget - total_price
        
        # 多种添加策略，增加随机性
        if random.random() < 0.5:
            available_indices.sort(key=lambda i: dishes[i].price, reverse=True)
        else:
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
                
                if total_price >= min_budget_required:
                    if random.random() < 0.3:
                        continue
                    else:
                        break
    
    selected_indices_after_repair = [i for i, bit in enumerate(individual) if bit == 1]
    if len(selected_indices_after_repair) % 2 != 0:
        current_total_price = sum(dishes[i].price for i in selected_indices_after_repair)
        remaining_budget = budget - current_total_price
        
        # 同样，优先尝试添加最便宜的菜品
        available_to_add = [
            i for i in range(len(dishes)) 
            if individual[i] == 0 and dishes[i].price <= remaining_budget
        ]
        if available_to_add:
            available_to_add.sort(key=lambda i: dishes[i].price)
            individual[available_to_add[0]] = 1
        else:
            # 否则，移除已选中的最便宜的菜品
            if selected_indices_after_repair:
                selected_indices_after_repair.sort(key=lambda i: dishes[i].price)
                remove_idx = selected_indices_after_repair[0]
                individual[remove_idx] = 0
                
    return individual

def _create_valid_individual(dishes: List[Dish], request: MenuRequest, config: AppConfig) -> List[int]:
    """创建符合预算约束的个体，平衡预算利用率、多样性，并确保菜品数量为偶数"""
    individual = [0] * len(dishes)
    available_budget = request.total_budget
    min_budget_required = request.total_budget * 0.8
    
    selected_count = 0
    ideal_count = request.diner_count + config.ga.dish_count_add_on
    max_count = int(ideal_count * 1.5)
    current_total = 0
    
    # 使用多种策略来创建个体，增加多样性
    strategy = random.choice(['high_price_first', 'balanced', 'random_fill'])
    
    if strategy == 'high_price_first':
        dish_indices = list(range(len(dishes)))
        dish_indices.sort(key=lambda i: dishes[i].price, reverse=True)
    elif strategy == 'balanced':
        dish_indices = list(range(len(dishes)))
        dish_indices.sort(key=lambda i: (
            dishes[i].price * 0.6 + 
            len(dishes[i].cooking_methods) * 10 + 
            len(dishes[i].flavor_tags) * 5 + 
            (50 if dishes[i].is_signature else 0)
        ), reverse=True)
    else:
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
            
            if current_total >= request.total_budget * 0.95:
                break
    
    # 第二阶段：确保达到最低预算要求
    if current_total < min_budget_required:
        remaining_dishes = [i for i in range(len(dishes)) if individual[i] == 0]
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
    
    # 在生成个体后，检查并确保菜品数量为偶数
    selected_count = sum(individual)
    if selected_count % 2 != 0:
        current_total_price = sum(dishes[i].price for i, bit in enumerate(individual) if bit == 1)
        remaining_budget = request.total_budget - current_total_price

        # 策略：如果为奇数，优先尝试添加一个价格最低的菜品
        available_to_add = [
            i for i, bit in enumerate(individual) 
            if bit == 0 and dishes[i].price <= remaining_budget
        ]
        if available_to_add:
            # 按价格升序排序，选择最便宜的菜品添加
            available_to_add.sort(key=lambda i: dishes[i].price)
            individual[available_to_add[0]] = 1
        else:
            # 如果预算不足以添加任何菜品，则移除一个已选中的、最便宜的菜品
            selected_indices = [i for i, bit in enumerate(individual) if bit == 1]
            if selected_indices:
                selected_indices.sort(key=lambda i: dishes[i].price)
                remove_idx = selected_indices[0]
                individual[remove_idx] = 0

    return individual

def _evaluate_menu(individual: List[int], dishes: List[Dish], request: MenuRequest, config: AppConfig) -> Tuple[float]:
    """评估函数，用于计算一个菜单的适应度分数"""
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
    
    # 软性约束评分
    
    # 1. 价格得分：菜单总价越接近预算的100%，得分越高
    if request.total_budget == 0:
        price_score = 1.0 if total_price == 0 else 0.0
    else:
        price_score = budget_utilization

    # 2. 菜品数量得分
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

    # 5. 高价值菜品得分
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

def _run_ga_blocking(dishes: List[Dish], request: MenuRequest, config: AppConfig) -> DiversityHallOfFame:
    """
    在阻塞模式下运行遗传算法，使用自定义的差异性名人堂
    """
    dish_attributes = _get_dish_attributes(dishes)
    num_dishes = len(dishes)

    toolbox = base.Toolbox()
    
    def create_individual():
        return creator.Individual(_create_valid_individual(dishes, request, config))
    
    toolbox.register("individual", create_individual)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    def evaluate_and_repair(individual):
        repaired = _repair_individual(individual[:], dishes, request.total_budget)
        individual[:] = repaired
        return _evaluate_menu(individual, dishes, request, config)
    
    toolbox.register("evaluate", evaluate_and_repair)
    toolbox.register("mate", tools.cxTwoPoint)
    toolbox.register("mutate", tools.mutFlipBit, indpb=config.ga.mutation_rate)
    toolbox.register("select", tools.selTournament, tournsize=3)

    def crossover_and_repair(ind1, ind2):
        tools.cxTwoPoint(ind1, ind2)
        ind1[:] = _repair_individual(ind1[:], dishes, request.total_budget)
        ind2[:] = _repair_individual(ind2[:], dishes, request.total_budget)
        return ind1, ind2
    
    def mutate_and_repair(individual):
        tools.mutFlipBit(individual, indpb=config.ga.mutation_rate)
        individual[:] = _repair_individual(individual[:], dishes, request.total_budget)
        return individual,
    
    toolbox.register("mate", crossover_and_repair)
    toolbox.register("mutate", mutate_and_repair)

    population = toolbox.population(n=config.ga.population_size)
    
    # 使用自定义的差异性名人堂，只保留2个最优且差异明显的解
    hall_of_fame = DiversityHallOfFame(maxsize=2, dishes=dishes, min_difference_threshold=0.5)

    print(f"开始为 {request.diner_count} 人就餐执行遗传算法...")

    stats = tools.Statistics(lambda ind: ind.fitness.values[0])
    stats.register("avg", lambda x: round(sum(x) / len(x), 2))
    stats.register("max", lambda x: round(max(x), 2))

    # 自定义进化过程，在每一代中更新差异性名人堂
    for generation in range(config.ga.generations):
        # 选择下一代
        offspring = toolbox.select(population, len(population))
        offspring = list(map(toolbox.clone, offspring))
        
        # 交叉
        for child1, child2 in zip(offspring[::2], offspring[1::2]):
            if random.random() < config.ga.crossover_rate:
                toolbox.mate(child1, child2)
                del child1.fitness.values
                del child2.fitness.values
        
        # 变异
        for mutant in offspring:
            if random.random() < config.ga.mutation_rate:
                toolbox.mutate(mutant)
                del mutant.fitness.values
        
        # 评估未评估的个体
        invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
        fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
        for ind, fit in zip(invalid_ind, fitnesses):
            ind.fitness.values = fit
        
        # 更新差异性名人堂
        for ind in offspring:
            if ind.fitness.values[0] > 0:  # 只考虑有效的解决方案
                hall_of_fame.insert(ind)
        
        population[:] = offspring
        
        # 记录统计信息
        if generation % 10 == 0:
            record = stats.compile(population)
            print(f"第 {generation} 代: 平均适应度 {record['avg']}, 最大适应度 {record['max']}, 名人堂大小 {len(hall_of_fame)}")

    print(f"遗传算法执行完毕。差异性名人堂中有 {len(hall_of_fame)} 个最优解。")
    
    # 显示最终结果的差异度
    if len(hall_of_fame) == 2:
        difference = _calculate_menu_difference(hall_of_fame[0], hall_of_fame[1], dishes)
        print(f"两个解决方案的差异度: {difference:.2%}")
    
    return hall_of_fame

async def plan_menu_async(
    process_pool: ProcessPoolExecutor,
    dishes: List[Dish],
    request: MenuRequest,
    config: AppConfig,
) -> List[MenuResponse]:
    """
    异步接口，用于规划菜单。
    现在直接返回差异性名人堂中的解决方案，无需事后筛选。
    """
    loop = asyncio.get_event_loop()
    
    hall_of_fame = await loop.run_in_executor(
        process_pool,
        _run_ga_blocking,
        dishes,
        request,
        config
    )

    if not hall_of_fame:
        print("警告：没有找到符合要求的菜单方案")
        return []

    menu_responses: List[MenuResponse] = []

    # 直接使用差异性名人堂中的解决方案
    for individual in hall_of_fame:
        selected_dishes = [dishes[i] for i, selected in enumerate(individual) if selected]

        if not selected_dishes:
            continue

        # 适应度分数，精确到小数点后2位
        score = round(individual.fitness.values[0], 2)
        total_price = sum(dish.price for dish in selected_dishes)
        budget_utilization = round(total_price / request.total_budget * 100, 1) if request.total_budget > 0 else 0

        simplified_dishes = [
            SimplifiedDish(
                dish_id=dish.dish_id,
                dish_name=dish.dish_name,
                final_price=dish.final_price,  # <--- 修正
                contribution_to_dish_count=dish.contribution_to_dish_count
            )
            for dish in selected_dishes
        ]

        response = MenuResponse(
            菜单评分=score,
            总价=total_price,
            菜品总数=len(selected_dishes),
            菜品清单=simplified_dishes,
        )
        menu_responses.append(response)

    print(f"返回 {len(menu_responses)} 个预算利用率≥80%且差异明显的菜单方案")
    for i, response in enumerate(menu_responses):
        budget_util = round(response.总价 / request.total_budget * 100, 1) if request.total_budget > 0 else 0
        print(f"菜单 {i+1}: 预算利用率 {budget_util}%, 评分 {response.菜单评分}")

    return menu_responses