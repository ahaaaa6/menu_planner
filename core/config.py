from pydantic_settings import BaseSettings
from pydantic import Field

class GAConfig(BaseSettings):
    """遗传算法相关配置"""
    population_size: int = Field(50, description="种群大小")
    generations: int = Field(40, description="迭代代数")
    crossover_rate: float = Field(0.8, description="交叉概率")
    mutation_rate: float = Field(0.2, description="变异概率")
    hall_of_fame_size: int = Field(3, description="名人堂大小，即返回的最优解数量")
    dish_count_add_on: int = Field(2, description="推荐菜品数 = 人数 + N")
    
    # 各种评分项的权重
    weight_price: float = Field(0.4, description="价格权重")
    weight_dish_count: float = Field(0.2, description="菜品数量权重")
    weight_variety: float = Field(0.2, description="多样性权重")
    weight_balance: float = Field(0.15, description="荤素平衡权重")
    weight_high_value: float = Field(0.05, description="高价值菜品权重")


class RedisConfig(BaseSettings):
    """Redis 缓存配置"""
    host: str = Field("localhost", description="Redis 主机")
    port: int = Field(6379, description="Redis 端口")
    db: int = Field(0, description="Redis 数据库")
    menu_cache_ttl_seconds: int = Field(3600, description="菜单缓存过期时间（秒）")


class APIConfig(BaseSettings):
    """外部 API 配置"""
    mock_dish_api_url: str = Field("http://127.0.0.1:8001/api/v1", description="模拟菜品API地址")


# [新增] 创建一个顶层 AppConfig 类来整合所有配置
class AppConfig(BaseSettings):
    """应用总配置"""
    ga: GAConfig = GAConfig()
    redis: RedisConfig = RedisConfig()
    api: APIConfig = APIConfig()
    
    # 进程池配置
    process_pool_max_workers: int = Field(4, description="处理遗传算法的进程池最大工作进程数")

# 实例化一个全局可用的配置对象
settings = AppConfig()