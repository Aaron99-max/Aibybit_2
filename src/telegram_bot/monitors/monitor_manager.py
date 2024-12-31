import logging
from typing import Dict, List
from src.exchange.bybit_client import BybitClient

logger = logging.getLogger(__name__)

class MonitorManager:
    def __init__(self, bybit_client: BybitClient):
        """모니터 매니저 초기화"""
        self.bybit_client = bybit_client
        self.is_monitoring = False
        self._monitors = []
        
    async def start_all_monitors(self) -> None:
        """모든 모니터링 시작"""
        try:
            if self.is_monitoring:
                logger.warning("모니터링이 이미 실행 중입니다.")
                return
                
            self.is_monitoring = True
            logger.info("모든 모니터링을 시작합니다.")
            
            # 여기에 실제 모니터링 로직 추가
            # 예: 가격 모니터링, 포지션 모니터링 등
            
        except Exception as e:
            logger.error(f"모니터링 시작 중 에러: {str(e)}")
            self.is_monitoring = False
            raise
            
    async def stop_all_monitors(self) -> None:
        """모든 모니터링 중지"""
        try:
            if not self.is_monitoring:
                logger.warning("모니터링이 이미 중지되어 있습니다.")
                return
                
            self.is_monitoring = False
            logger.info("모든 모니터링을 중지합니다.")
            
            # 여기에 모니터링 중지 로직 추가
            
        except Exception as e:
            logger.error(f"모니터링 중지 중 에러: {str(e)}")
            raise
            
    async def add_monitor(self, monitor) -> None:
        """모니터 추가"""
        self._monitors.append(monitor)
        
    async def remove_monitor(self, monitor) -> None:
        """모니터 제거"""
        if monitor in self._monitors:
            self._monitors.remove(monitor)
            
    async def get_status(self) -> Dict:
        """모니터링 상태 조회"""
        return {
            'is_monitoring': self.is_monitoring,
            'monitor_count': len(self._monitors)
        }
