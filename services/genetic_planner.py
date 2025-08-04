import asyncio
import random
import logging
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from typing import List, Dict, Any, Tuple

from deap import base, creator, tools, algorithms

from ..core.config import AppConfig
from ..schemas.menu import Dish, MenuRequest, MenuResponse, SimplifiedDish

# --- 日志和自定义异常 ---
logger = logging.getLogger(__name__)

class MenuPlanningError(Exception):
    """用于排菜算法特定错误的自定义异常类，方便传递友好的错误信息。"""
    pass

# --- DEAP 初始化 ---
# 检查 creator 是否已定义，防止在热重载等场景下重复定义引发错误
if not hasattr(creator, "FitnessMax"):
    creator.create("FitnessMax", base.Fitness, weights=(1.0,))
if not hasattr(creator, "Individual"):
    creator.create("Individual", list, fitness=creator.FitnessMax)


# --- 核心辅助函数 ---

def _calculate_menu_difference(menu1: List[int], menu2: List[int], dishes: List[Dish]) -> float:
    """计算两个菜单之间的差异度 (保留您的原始加权逻辑)"""
    selected_dishes_1 = [dishes[i] for i, bit in enumerate(menu1) if bit == 1]
    selected_dishes_2 = [dishes[i] for i, bit in enumerate(menu2) if bit == 1]
    
    # 【防御性措施】如果任一菜单为空，直接返回0差异度
    if not selected_dishes_1 or not selected_dishes_2:
        return 0.0
    
    dishes_1 = set(d.dish_id for d in selected_dishes_1)
    dishes_2 = set(d.dish_id for d in selected_dishes_2)
    # 【防御性措施】确保并集不为0，防止除零错误
    dish_union_len = len(dishes_1.union(dishes_2))
    dish_difference = len(dishes_1.symmetric_difference(dishes_2)) / dish_union_len if dish_union_len > 0 else 0
    
    cooking_methods_1 = set(method for d in selected_dishes_1 for method in d.cooking_methods)
    cooking_methods_2 = set(method for d in selected_dishes_2 for method in d.cooking_methods)
    cooking_union_len = len(cooking_methods_1.union(cooking_methods_2))
    cooking_difference = len(cooking_methods_1.symmetric_difference(cooking_methods_2)) / cooking_union_len if cooking_union_len > 0 else 0
    
    flavors_1 = set(flavor for d in selected_dishes_1 for flavor in d.flavor_tags)
    flavors_2 = set(flavor for d in selected_dishes_2 for flavor in d.flavor_tags)
    flavor_union_len = len(flavors_1.union(flavors_2))
    flavor_difference = len(flavors_1.symmetric_difference(flavors_2)) / flavor_union_len if flavor_union_len > 0 else 0
    
    ingredients_1 = set(ing for d in selected_dishes_1 for ing in d.main_ingredient)
    ingredients_2 = set(ing for d in selected_dishes_2 for ing in d.main_ingredient)
    ingredient_union_len = len(ingredients_1.union(ingredients_2))
    ingredient_difference = len(ingredients_1.symmetric_difference(ingredients_2)) / ingredient_union_len if ingredient_union_len > 0 else 0
    
    price_1 = sum(d.price for d in selected_dishes_1)
    price_2 = sum(d.price for d in selected_dishes_2)
    price_sum = price_1 + price_2
    price_difference = abs(price_1 - price_2) / price_sum if price_sum > 0 else 0
    
    # 加权平均逻辑
    total_difference = (
        dish_difference * 0.4 +
        cooking_difference * 0.2 +
        flavor_difference * 0.2 +
        ingredient_difference * 0.15 +
        price_difference * 0.05
    )
    
    return total_difference

class DiversityHallOfFame:
    """自定义名人堂类 (增强 insert 方法的健壮性)"""
    def __init__(self, maxsize: int, dishes: List[Dish], min_difference_threshold: float = 0.3):
        self.maxsize = maxsize
        self.dishes = dishes
        self.min_difference_threshold = min_difference_threshold
        self.items = []
    
    def insert(self, item):
        """插入新的个体，考虑适应度和差异性"""
        # 【防御性措施】确保个体有有效的适应度值
        if not hasattr(item, 'fitness') or not item.fitness.valid:
            return

        is_different_enough = self._is_sufficiently_different(item)
        
        if not is_different_enough:
            return

        if len(self.items) < self.maxsize:
            self.items.append(item)
            self.items.sort(key=lambda x: x.fitness.values[0], reverse=True)
        else:
            # 找到名人堂中适应度最差的个体
            worst_item = min(self.items, key=lambda x: x.fitness.values[0])
            # 如果新个体的适应度更高，则替换掉最差的
            if item.fitness.values[0] > worst_item.fitness.values[0]:
                self.items.remove(worst_item)
                self.items.append(item)
                self.items.sort(key=lambda x: x.fitness.values[0], reverse=True)
    
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


def _get_dish_attributes(dishes: List[Dish]) -> Dict[str, Any]:
    """预计算菜品属性，用于遗传算法。"""
    return {
        "prices": [dish.price for dish in dishes],
        "ids": [dish.dish_id for dish in dishes],
    }

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
    
    return individual

def _create_valid_individual(dishes: List[Dish], request: MenuRequest, config: AppConfig) -> List[int]:
    """创建符合预算约束的个体，平衡预算利用率和多样性"""
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

# --- 遗传算法执行主函数 (增加防御和日志) ---

def _run_ga_blocking(dishes: List[Dish], request: MenuRequest, config: AppConfig) -> DiversityHallOfFame:
    """在阻塞模式下运行遗传算法 """
    # 【防御性检查】检查可用菜品数量是否满足最低要求
    min_dishes_required = config.ga.min_dishes_for_ga # 假设配置中有这个值
    if len(dishes) < min_dishes_required:
        raise MenuPlanningError(f"可用菜品数量不足。算法至少需要 {min_dishes_required} 道菜，但目前只有 {len(dishes)} 道可用。")

    toolbox = base.Toolbox()
    
    toolbox.register("individual", _create_valid_individual, dishes=dishes, request=request, config=config)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual, n=config.ga.population_size)

    toolbox.register("evaluate", _evaluate_menu, dishes=dishes, request=request, config=config)
    toolbox.register("mate", tools.cxTwoPoint)
    toolbox.register("mutate", tools.mutFlipBit, indpb=config.ga.mutation_rate)
    toolbox.register("select", tools.selTournament, tournsize=3)

    def crossover_and_repair(ind1, ind2):
        tools.cxTwoPoint(ind1, ind2)
        ind1[:] = _repair_individual(ind1[:], dishes, request.total_budget)
        ind2[:] = _repair_individual(ind2[:], dishes, request.total_budget)
        del ind1.fitness.values
        del ind2.fitness.values
        return ind1, ind2
    
    def mutate_and_repair(individual):
        tools.mutFlipBit(individual, indpb=config.ga.mutation_rate)
        individual[:] = _repair_individual(individual[:], dishes, request.total_budget)
        del individual.fitness.values
        return individual,
    
    toolbox.register("mate", crossover_and_repair)
    toolbox.register("mutate", mutate_and_repair)

    population = toolbox.population()
    hall_of_fame = DiversityHallOfFame(maxsize=2, dishes=dishes, min_difference_threshold=0.5)

    stats = tools.Statistics(lambda ind: ind.fitness.values[0])
    stats.register("avg", np.mean)
    stats.register("max", np.max)

    logger.info(f"开始为 {request.diner_count} 人就餐执行遗传算法 (共 {config.ga.generations} 代)...")

    # 自定义进化循环
    for generation in range(config.ga.generations):
        offspring = toolbox.select(population, len(population))
        offspring = list(map(toolbox.clone, offspring))
        
        for child1, child2 in zip(offspring[::2], offspring[1::2]):
            if random.random() < config.ga.crossover_rate:
                toolbox.mate(child1, child2)
        
        for mutant in offspring:
            if random.random() < config.ga.mutation_rate:
                toolbox.mutate(mutant)
        
        invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
        fitnesses = map(toolbox.evaluate, invalid_ind)
        for ind, fit in zip(invalid_ind, fitnesses):
            ind.fitness.values = fit
        
        for ind in offspring:
            hall_of_fame.insert(ind)
        
        population[:] = offspring
        
        if (generation + 1) % 10 == 0:
            record = stats.compile(population)
            logger.info(f"第 {generation + 1} 代: 平均适应度 {record['avg']:.2f}, 最大适应度 {record['max']:.2f}, 名人堂大小 {len(hall_of_fame)}")

    # 【防御性检查】检查名人堂是否有结果
    if not hall_of_fame:
        raise MenuPlanningError("算法执行完毕，但未能找到任何满足条件的菜单方案。请尝试放宽预算或增加菜品选择。")

    logger.info(f"遗传算法执行完毕。在名人堂中找到 {len(hall_of_fame)} 个最优解。")
    if len(hall_of_fame) == 2:
        difference = _calculate_menu_difference(hall_of_fame[0], hall_of_fame[1], dishes)
        logger.info(f"两个最优解的差异度: {difference:.2%}")
    
    return hall_of_fame

# --- 异步接口 (增加错误捕获和日志) ---
async def plan_menu_async(
    process_pool: ProcessPoolExecutor,
    dishes: List[Dish],
    request: MenuRequest,
    config: AppConfig,
) -> List[MenuResponse]:
    """异步接口，用于在背景进程中执行计算密集型的遗传算法。"""
    loop = asyncio.get_running_loop()
    
    try:
        hall_of_fame = await loop.run_in_executor(
            process_pool,
            _run_ga_blocking,
            dishes,
            request,
            config
        )

        menu_responses: List[MenuResponse] = []
        for individual in hall_of_fame:
            selected_dishes = [dishes[i] for i, selected in enumerate(individual) if selected]
            if not selected_dishes:
                continue

            score = round(individual.fitness.values[0], 2)
            total_price = round(sum(dish.price for dish in selected_dishes), 2)

            simplified_dishes = [
                SimplifiedDish(
                    dish_id=dish.dish_id,
                    dish_name=dish.dish_name,
                    final_price=dish.price,
                    contribution_to_dish_count=1
                ) for dish in selected_dishes
            ]
            response = MenuResponse(
                菜单评分=score,
                总价=total_price,
                菜品总数=len(selected_dishes),
                菜品列表=simplified_dishes,
            )
            menu_responses.append(response)

        logger.info(f"成功生成 {len(menu_responses)} 个差异化菜单方案。")
        return menu_responses

    except MenuPlanningError as e:
        # 捕获自定义的业务逻辑错误
        logger.warning(f"排菜逻辑错误：{e}")
        # 将错误信息向上抛出，以便返回给前端用户
        raise e
    except Exception as e:
        # 【安全网】捕获所有其他未知错误
        logger.error("执行遗传算法时发生未知错误。", exc_info=True)
        # 向上抛出一个统一的、对用户友好的内部错误提示
        raise MenuPlanningError("执行排菜算法时发生未知的内部错误，请联系技术支援。")