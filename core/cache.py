# menu_planner/core/cache.py
import redis.asyncio as redis
from contextlib import asynccontextmanager
from .config import settings
import logging
import asyncio
from typing import Optional, Any
import time

logger = logging.getLogger(__name__)

class RedisConnectionError(Exception):
    """Redis连接相关的自定义异常"""
    pass

class RedisManager:
    """一个异步Redis连接池管理器，带重试逻辑"""
    def __init__(self):
        self.pool = None
        self._connection_healthy = False
        self._last_health_check = 0
        self._health_check_interval = 30  # 30秒检查一次连接健康状态

    def initialize(self):
        """在应用启动时创建连接池"""
        if self.pool is None:
            logger.info(f"正在初始化Redis连接池: {settings.redis.host}:{settings.redis.port}")
            
            # 使用简单的连接池配置，依赖应用级重试逻辑
            self.pool = redis.ConnectionPool(
                host=settings.redis.host,
                port=settings.redis.port,
                db=settings.redis.db,
                decode_responses=True,
                health_check_interval=30,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            logger.info("Redis连接池初始化完成，使用应用级重试逻辑")

    async def close(self):
        """在应用关闭时关闭连接池"""
        if self.pool:
            logger.info("正在关闭Redis连接池...")
            try:
                await self.pool.disconnect()
            except Exception as e:
                logger.warning(f"关闭Redis连接池时出现警告: {e}")
            finally:
                self.pool = None
                self._connection_healthy = False

    async def _check_connection_health(self) -> bool:
        """检查Redis连接健康状态"""
        current_time = time.time()
        
        # 如果距离上次检查时间不足间隔，直接返回缓存的状态
        if current_time - self._last_health_check < self._health_check_interval:
            return self._connection_healthy
        
        try:
            async with self._get_raw_connection() as client:
                await client.ping()
                self._connection_healthy = True
                logger.debug("Redis连接健康检查通过")
        except Exception as e:
            self._connection_healthy = False
            logger.warning(f"Redis连接健康检查失败: {e}")
        
        self._last_health_check = current_time
        return self._connection_healthy

    @asynccontextmanager
    async def _get_raw_connection(self):
        """获取原始Redis连接（不带应用级重试）"""
        if not self.pool:
            raise RedisConnectionError("Redis连接池尚未初始化。请在应用启动时调用 initialize()。")
        
        client = None
        try:
            client = redis.Redis(connection_pool=self.pool)
            yield client
        finally:
            if client:
                await client.close()

    async def execute_with_retry(
        self, 
        operation, 
        *args, 
        max_retries: int = 3,
        base_delay: float = 0.1,
        max_delay: float = 2.0,
        fallback_result: Any = None,
        **kwargs
    ) -> Any:
        """
        执行Redis操作，带应用级重试逻辑
        
        Args:
            operation: 要执行的Redis操作函数
            *args: 操作函数的位置参数
            max_retries: 最大重试次数
            base_delay: 基础延迟时间（秒）
            max_delay: 最大延迟时间（秒）
            fallback_result: 如果所有重试都失败，返回的默认值
            **kwargs: 操作函数的关键字参数
        
        Returns:
            操作结果或fallback_result
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):  # +1 因为第一次不算重试
            try:
                async with self._get_raw_connection() as client:
                    # 执行实际的Redis操作
                    if asyncio.iscoroutinefunction(operation):
                        result = await operation(client, *args, **kwargs)
                    else:
                        result = operation(client, *args, **kwargs)
                        if asyncio.iscoroutine(result):
                            result = await result
                    
                    # 操作成功，更新连接状态
                    self._connection_healthy = True
                    return result
                    
            except (redis.ConnectionError, redis.TimeoutError, OSError) as e:
                last_exception = e
                self._connection_healthy = False
                
                if attempt < max_retries:
                    # 计算延迟时间（指数退避）
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(
                        f"Redis操作失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}. "
                        f"{delay:.2f}秒后重试..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Redis操作在 {max_retries + 1} 次尝试后仍然失败: {e}",
                        exc_info=True
                    )
            
            except Exception as e:
                # 非连接相关的错误，不进行重试
                logger.error(f"Redis操作发生非连接错误: {e}", exc_info=True)
                raise
        
        # 所有重试都失败了
        if fallback_result is not None:
            logger.warning(f"Redis操作失败，返回默认值: {fallback_result}")
            return fallback_result
        else:
            raise RedisConnectionError(
                f"Redis操作在 {max_retries + 1} 次尝试后失败。最后的错误: {last_exception}"
            )

    @asynccontextmanager
    async def get_connection(self):
        """提供一个上下文管理的Redis连接（兼容现有代码）"""
        if not self.pool:
            raise RedisConnectionError("Redis连接池尚未初始化。请在应用启动时调用 initialize()。")
        
        client = None
        try:
            client = redis.Redis(connection_pool=self.pool)
            yield client
        except Exception as e:
            logger.error(f"Redis 操作失败: {e}", exc_info=True)
            raise
        finally:
            if client:
                await client.close()

    # 便捷方法，封装常用的Redis操作
    async def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """获取键值，带重试逻辑"""
        async def _get_operation(client, key):
            return await client.get(key)
        
        return await self.execute_with_retry(
            _get_operation, 
            key, 
            fallback_result=default
        )

    async def set(
        self,
        key: str,
        value: str,
        ex: Optional[int] = None,
        raise_on_failure: bool = False,
        **kwargs
    ) -> bool:
        """设置键值，带重试逻辑，并支持 nx 等额外参数。"""
        async def _set_operation(client, key, value, ex=None, **kwargs):
            # 将 ex 和其他所有关键字参数一起传递给底层的 set 方法
            return await client.set(key, value, ex=ex, **kwargs)

        try:
            result = await self.execute_with_retry(
                _set_operation,
                key,
                value,
                ex=ex,
                fallback_result=False if not raise_on_failure else None,
                **kwargs
            )
            return result if result is not None else False
        except RedisConnectionError:
            if raise_on_failure:
                raise
            return False

    async def delete(self, key: str) -> int:
        """删除键，带重试逻辑"""
        async def _delete_operation(client, key):
            return await client.delete(key)
        
        return await self.execute_with_retry(
            _delete_operation, 
            key, 
            fallback_result=0
        )

    async def ping(self) -> bool:
        """检查Redis连接，带重试逻辑"""
        async def _ping_operation(client):
            await client.ping()
            return True
        
        try:
            return await self.execute_with_retry(
                _ping_operation,
                fallback_result=False
            )
        except Exception:
            return False

    async def get_connection_status(self) -> dict:
        """获取连接状态信息"""
        is_healthy = await self._check_connection_health()
        
        return {
            "healthy": is_healthy,
            "pool_created": self.pool is not None,
            "last_health_check": self._last_health_check,
            "host": settings.redis.host,
            "port": settings.redis.port,
            "db": settings.redis.db
        }

# 创建一个全局实例，方便在应用中共享
redis_manager = RedisManager()

async def debug_redis_connection():
    """调试 Redis 连接的辅助函数"""
    print(f"=== Redis 连接调试信息 ===")
    print(f"配置的 Redis 主机: {settings.redis.host}")
    print(f"配置的 Redis 端口: {settings.redis.port}")
    print(f"配置的 Redis 数据库: {settings.redis.db}")
    
    # 初始化连接池
    redis_manager.initialize()
    
    # 检查连接状态
    status = await redis_manager.get_connection_status()
    print(f"连接状态: {status}")
    
    # 尝试 ping
    try:
        ping_result = await redis_manager.ping()
        print(f"Ping 结果: {ping_result}")
    except Exception as e:
        print(f"Ping 失败: {e}")
    
    # 尝试设置和获取一个测试键
    try:
        await redis_manager.set("test_key", "test_value", ex=10)
        result = await redis_manager.get("test_key")
        print(f"测试键值读写: {result}")
        await redis_manager.delete("test_key")
    except Exception as e:
        print(f"键值操作失败: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(debug_redis_connection())