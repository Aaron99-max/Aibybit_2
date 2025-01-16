import functools
import logging
import traceback
from typing import Callable, Any
import asyncio

logger = logging.getLogger(__name__)

def error_handler(func: Callable) -> Callable:
    """에러 처리를 위한 데코레이터"""
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs) -> Any:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
            
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
            
    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper