import logging
import asyncio
from typing import Dict
from exchange.websocket_client import BybitWebsocketClient
from telegram_bot.formatters.order_formatter import OrderFormatter
from telegram_bot.formatters.position_formatter import PositionFormatter
from services.telegram_service import TelegramService

logger = logging.getLogger(__name__)

class MonitorService:
    def __init__(self, websocket_client: BybitWebsocketClient, telegram_service: TelegramService):
        self.ws_client = websocket_client
        self.telegram_service = telegram_service
        self.order_formatter = OrderFormatter()
        self.position_formatter = PositionFormatter()

    async def start(self):
        """모니터링 시작"""
        # 콜백 등록
        self.ws_client.add_callback('order', self._handle_order_update)
        self.ws_client.add_callback('position', self._handle_position_update)
        self.ws_client.add_callback('execution', self._handle_execution_update)
        
        # 모니터링 시작
        await self.ws_client.start_monitoring()

    async def _handle_order_update(self, data: Dict):
        """주문 업데이트 처리"""
        try:
            order_data = data.get('data', {})
            if not order_data:
                return

            # 주문 상태에 따른 메시지 생성
            status = order_data.get('orderStatus')
            if status == 'Created':
                message = self.order_formatter.format_order_created(order_data)
            elif status == 'Filled':
                message = self.order_formatter.format_order_filled(order_data)
            elif status == 'Cancelled':
                message = self.order_formatter.format_order_cancelled(order_data)
            else:
                return

            # 텔레그램으로 알림 전송
            await self.telegram_service.send_message(message)

        except Exception as e:
            logger.error(f"주문 업데이트 처리 중 오류: {str(e)}")

    async def _handle_position_update(self, data: Dict):
        """포지션 업데이트 처리"""
        try:
            position_data = data.get('data', {})
            if not position_data:
                return

            # position_side 필드 사용 (side는 청산 방향)
            position_side = position_data.get('position_side', '')
            size = float(position_data.get('size', 0))
            
            # 포지션 상태에 따른 메시지 생성
            if size > 0:  # 새로운 포지션 또는 포지션 크기 변경
                message = self.position_formatter.format_position_update(position_data)
            elif size == 0:  # 포지션 청산
                message = self.position_formatter.format_position_closed(position_data)
            else:
                return

            # 텔레그램으로 알림 전송
            await self.telegram_service.send_message(message)

        except Exception as e:
            logger.error(f"포지션 업데이트 처리 중 오류: {str(e)}")

    async def _handle_execution_update(self, data: Dict):
        """체결 업데이트 처리"""
        try:
            execution_data = data.get('data', {})
            if not execution_data:
                return

            # 체결 정보 포맷팅 및 알림 전송
            message = self.order_formatter.format_execution(execution_data)
            await self.telegram_service.send_message(message)

        except Exception as e:
            logger.error(f"체결 업데이트 처리 중 오류: {str(e)}")
