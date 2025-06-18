# menu_planner/core/cache.py
import redis.asyncio as redis
from contextlib import asynccontextmanager
from menu_planner.core.config import settings  # 修复：正确导入配置
import logging

logger = logging.getLogger(__name__)

class RedisManager:
    """一个异步Redis连接池管理器"""
    def __init__(self):
        self.pool = None

    def initialize(self):
        """在应用启动时创建连接池"""
        if self.pool is None:
            logger.info(f"正在初始化Redis连接池: {settings.redis.host}:{settings.redis.port}")
            self.pool = redis.ConnectionPool(
                host=settings.redis.host,        # 修复：使用正确的配置路径
                port=settings.redis.port,        # 修复：使用正确的配置路径
                db=settings.redis.db,            # 修复：使用正确的配置路径
                decode_responses=True # 自动将bytes解码为str
            )

    def close(self):
        """在应用关闭时关闭连接池"""
        if self.pool:
            logger.info("正在关闭Redis连接池...")
            # redis-py的asyncio实现会在后台自动管理连接关闭
            self.pool.disconnect()

    @asynccontextmanager
    async def get_connection(self):
        """提供一个上下文管理的Redis连接"""
        if not self.pool:
            raise RuntimeError("Redis连接池尚未初始化。请在应用启动时调用 initialize()。")
        
        client = None
        try:
            client = redis.Redis(connection_pool=self.pool)
            yield client
        except Exception as e:
            logger.error(f"Redis 操作失败: {e}", exc_info=True)
            raise
        finally:
            if client:
                # 连接是从池中获取的，调用 close() 会将其返回池中
                await client.close()

# 创建一个全局实例，方便在应用中共享
redis_manager = RedisManager()