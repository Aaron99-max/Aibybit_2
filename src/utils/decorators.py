import logging
import functools
import traceback
from typing import Callable, Any

logger = logging.getLogger(__name__)

def error_handler(func: Callable) -> Callable:
    """에러 핸들링 데코레이터"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} 실행 중 에러: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    return wrapper
