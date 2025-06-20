# menu_planner/core/config.py

import os
from pydantic_settings import BaseSettings
from pydantic import Field

class GAConfig(BaseSettings):
    """遗传算法相关配置"""
    population_size: int = Field(int(os.getenv("APP_GA_POPULATION_SIZE", 50)), description="种群大小")
    generations: int = Field(int(os.getenv("APP_GA_GENERATIONS", 40)), description="迭代代数")
    crossover_rate: float = Field(float(os.getenv("APP_GA_CROSSOVER_RATE", 0.8)), description="交叉概率")
    mutation_rate: float = Field(float(os.getenv("APP_GA_MUTATION_RATE", 0.2)), description="变异概率")
    hall_of_fame_size: int = Field(int(os.getenv("APP_GA_HALL_OF_FAME_SIZE", 3)), description="名人堂大小，即返回的最优解数量")
    dish_count_add_on: int = Field(int(os.getenv("APP_GA_DISH_COUNT_ADD_ON", 2)), description="推荐菜品数 = 人数 + N")
    
    # 各种评分项的权重
    weight_price: float = Field(float(os.getenv("APP_GA_WEIGHT_PRICE", 0.4)), description="价格权重")
    weight_dish_count: float = Field(float(os.getenv("APP_GA_WEIGHT_DISH_COUNT", 0.2)), description="菜品数量权重")
    weight_variety: float = Field(float(os.getenv("APP_GA_WEIGHT_VARIETY", 0.2)), description="多样性权重")
    weight_balance: float = Field(float(os.getenv("APP_GA_WEIGHT_BALANCE", 0.15)), description="荤素平衡权重")
    weight_high_value: float = Field(float(os.getenv("APP_GA_WEIGHT_HIGH_VALUE", 0.05)), description="高价值菜品权重")


class RedisConfig(BaseSettings):
    """Redis 缓存配置"""
    host: str = Field(os.getenv("REDIS_HOST", "localhost"), description="Redis 主机")
    port: int = Field(int(os.getenv("APP_REDIS_PORT", 6379)), description="Redis 端口")
    db: int = Field(int(os.getenv("APP_REDIS_DB", 0)), description="Redis 数据库")
    menu_cache_ttl_seconds: int = Field(int(os.getenv("APP_REDIS_MENU_CACHE_TTL_SECONDS", 3600)), description="菜单缓存过期时间（秒）")
    # --- 新增 ---
    plan_cache_ttl_seconds: int = Field(int(os.getenv("APP_REDIS_PLAN_CACHE_TTL_SECONDS", 600)), description="排菜方案缓存过期时间（秒），用于处理不同用户的相同请求")


class APIConfig(BaseSettings):
    """外部 API 配置"""
    mock_dish_api_url: str = Field(os.getenv("MOCK_DISH_API_URL", "http://127.0.0.1:8001"), description="模拟菜品API地址")


class AppConfig(BaseSettings):
    """应用总配置"""
    ga: GAConfig = GAConfig()
    redis: RedisConfig = RedisConfig()
    api: APIConfig = APIConfig()
    
    # 进程池配置
    # 'N-1' 策略
    # 确保核心数至少为1
    cpu_cores = os.cpu_count() or 1
    default_workers = max(1, cpu_cores - 1) 

    process_pool_max_workers: int = Field(
        int(os.getenv("APP_PROCESS_POOL_MAX_WORKERS", os.cpu_count() or 1)),
        description="处理遗传算法的进程池最大工作进程数"
    )

    dynamic_queue_mem_threshold_percent: float = Field(
        float(os.getenv("APP_DYNAMIC_QUEUE_MEM_THRESHOLD_PERCENT", 80.0)),
        description="动态任务队列的内存使用率阈值(%)。超过此值将拒绝新任务。",
        ge=0,
        le=100
    )

# 实例化一个全局可用的配置对象
settings = AppConfig()