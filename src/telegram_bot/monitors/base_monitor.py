import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseMonitor(ABC):
    """모니터링 기본 클래스"""
    
    def __init__(self, bot, bybit_client):
        self.bot = bot
        self.bybit_client = bybit_client
    
    @abstractmethod
    async def start(self):
        """모니터링 시작"""
        pass
