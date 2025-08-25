# menu_planner/core/config.py

import os
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import ClassVar

class GAConfig(BaseSettings):
    """遗传算法相关配置"""
    population_size: int = Field(int(os.getenv("APP_GA_POPULATION_SIZE", 100)), description="种群大小")
    generations: int = Field(int(os.getenv("APP_GA_GENERATIONS", 100)), description="迭代代数")
    crossover_rate: float = Field(float(os.getenv("APP_GA_CROSSOVER_RATE", 0.8)), description="交叉概率")
    mutation_rate: float = Field(float(os.getenv("APP_GA_MUTATION_RATE", 0.2)), description="变异概率")
    hall_of_fame_size: int = Field(int(os.getenv("APP_GA_HALL_OF_FAME_SIZE", 2)), description="名人堂大小，即返回的最优解数量")
    min_dishes_for_ga: int = Field(5, description="运行遗传算法所需的最少菜品数量")
    hof_min_difference_threshold: float = Field(0.5, description="名人堂方案的最低差异度阈值")

    # 基础评分项的权重
    weight_price: float = Field(float(os.getenv("APP_GA_WEIGHT_PRICE", 0.45)), description="价格权重")
    weight_variety: float = Field(float(os.getenv("APP_GA_WEIGHT_VARIETY", 0.20)), description="多样性权重")
    weight_balance: float = Field(float(os.getenv("APP_GA_WEIGHT_BALANCE", 0.1)), description="荤素平衡权重")
    weight_high_value: float = Field(float(os.getenv("APP_GA_WEIGHT_HIGH_VALUE", 0.05)), description="高价值菜品权重")
    weight_demographic_balance: float = Field(float(os.getenv("APP_GA_WEIGHT_DEMOGRAPHIC_BALANCE", 0.20)), description="人群菜品配额均衡权重")
    max_bonus_multiplier_preference: float = Field(float(os.getenv("APP_GA_MAX_BONUS_PREFERENCE", 0.3)), description="偏好达成率对总分的最大加成比例 (例如 0.3 表示最多提升30%)")
    

class RedisConfig(BaseSettings):
    """Redis 缓存配置"""
    host: str = Field(os.getenv("APP_REDIS_HOST", "localhost"), description="Redis 主机")
    port: int = Field(int(os.getenv("APP_REDIS_PORT", 6379)), description="Redis 端口")
    db: int = Field(int(os.getenv("APP_REDIS_DB", 0)), description="Redis 数据库")
    menu_cache_ttl_seconds: int = Field(int(os.getenv("APP_REDIS_MENU_CACHE_TTL_SECONDS", 36000)), description="菜单缓存过期时间（秒）")
    plan_cache_ttl_seconds: int = Field(int(os.getenv("APP_REDIS_PLAN_CACHE_TTL_SECONDS", 36000)), description="排菜方案缓存过期时间（秒），用于处理不同用户的相同请求")


class APIConfig(BaseSettings):
    """外部 API 配置"""
    mock_dish_api_url: str = Field(os.getenv("MOCK_DISH_API_URL", "http://127.0.0.1:8001"), description="模拟菜品API地址")


class AppConfig(BaseSettings):
    """应用总配置"""
    ga: GAConfig = GAConfig()
    redis: RedisConfig = RedisConfig()
    api: APIConfig = APIConfig()
    
    cpu_cores: ClassVar[int] = os.cpu_count() or 1
    default_workers: ClassVar[int] = max(1, cpu_cores - 1) 

    process_pool_max_workers: int = Field(
        int(os.getenv("APP_PROCESS_POOL_MAX_WORKERS", default_workers)),
        description="处理遗传算法的进程池最大工作进程数"
    )

settings = AppConfig()