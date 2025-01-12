import functools
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)

def error_handler(func: Callable) -> Callable:
    """
    에러 처리를 위한 데코레이터
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}", exc_info=True)
            raise
    return wrapper 