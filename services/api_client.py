# menu_planner/services/api_client.py
import httpx
from typing import List, Dict, Any
import logging

from ..core.config import settings

logger = logging.getLogger(__name__)

async def fetch_dishes_from_external_api(restaurant_id: str) -> List[Dict[str, Any]]:
    """
    通过异步HTTP请求从外部API获取指定餐厅的菜品列表。
    """
    api_url = f"{settings.api.mock_dish_api_url}/dishes/{restaurant_id}"
    logger.info(f"📞 正在调用外部API获取菜品: {api_url}")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(api_url)
            
            # 抛出HTTP错误状态（如 404, 500）的异常
            response.raise_for_status()
            
            dishes_data = response.json()
            logger.info(f"✅ 成功从外部API获取到 {len(dishes_data)} 道菜品。")
            return dishes_data

    except httpx.HTTPStatusError as e:
        logger.error(f"🚨 调用外部API时发生HTTP错误: {e.response.status_code} for URL {e.request.url}")
        # 如果是404（找不到餐厅），返回空列表是合理的
        if e.response.status_code == 404:
            return []
        # 其他服务端错误，也返回空列表，避免服务崩溃
        return []
    except httpx.RequestError as e:
        logger.error(f"🚨 调用外部API时发生网络错误: {e}")
        return []
    except Exception as e:
        logger.error(f"🚨 解析外部API响应时发生未知错误: {e}", exc_info=True)
        return []