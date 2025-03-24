import logging
from typing import Dict, List
from exchange.bybit_client import BybitClient
import traceback

logger = logging.getLogger(__name__)

class MonitorManager:
    def __init__(self, telegram_bot, bybit_client: BybitClient):
        """모니터 매니저 초기화"""
        self.telegram_bot = telegram_bot
        self.bybit_client = bybit_client
        self.is_monitoring = False
        self._monitors = []
        
        # 주문/포지션 모니터 초기화
        from .order_monitor import OrderMonitor
        self.order_monitor = OrderMonitor(
            bot=telegram_bot,
            bybit_client=bybit_client
        )
        self._monitors.append(self.order_monitor)
        
    async def start_all_monitors(self) -> None:
        """모든 모니터링 시작"""
        try:
            if self.is_monitoring:
                logger.warning("모니터링이 이미 실행 중입니다.")
                return
                
            self.is_monitoring = True
            logger.info("모든 모니터링을 시작합니다.")
            
            # 각 모니터 시작
            for monitor in self._monitors:
                await monitor.start()
            
        except Exception as e:
            logger.error(f"모니터링 시작 중 에러: {str(e)}")
            logger.error(traceback.format_exc())
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
            
            # 각 모니터 중지
            for monitor in self._monitors:
                try:
                    # 웹소켓 콜백 제거
                    if hasattr(monitor, 'ws_client'):
                        monitor.ws_client.remove_callback('order')
                        monitor.ws_client.remove_callback('position')
                        monitor.ws_client.remove_callback('execution')
                    # 모니터 중지
                    await monitor.stop()
                except Exception as e:
                    logger.error(f"모니터 {monitor.__class__.__name__} 중지 중 오류: {str(e)}")
            
        except Exception as e:
            logger.error(f"모니터링 중지 중 에러: {str(e)}")
            logger.error(traceback.format_exc())
            raise
            
    async def add_monitor(self, monitor) -> None:
        """모니터 추가"""
        self._monitors.append(monitor)
        if self.is_monitoring:
            await monitor.start()
        
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
