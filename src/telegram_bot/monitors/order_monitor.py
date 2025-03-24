import logging
from typing import Dict
from .base_monitor import BaseMonitor
from exchange.websocket_client import BybitWebsocketClient
from ..formatters.monitor_formatter import MonitorFormatter
import time

logger = logging.getLogger(__name__)

class OrderMonitor(BaseMonitor):
    """주문/포지션 모니터링"""
    
    def __init__(self, bot, bybit_client):
        super().__init__(bot, bybit_client)
        # Use the existing WebSocket client from bybit_client instead of creating a new one
        self.ws_client = bybit_client.ws_client
        self.monitor_formatter = MonitorFormatter()
        # 체결 알림 누적을 위한 변수들
        self._execution_buffer = {}  # orderId별 체결 정보 누적
        self._last_notification = {}  # orderId별 마지막 알림 시간
        self._notification_interval = 5  # 최소 알림 간격 (초)

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
            # 데이터가 리스트인 경우 각 항목 처리
            if isinstance(data, list):
                for item in data:
                    await self._process_order_data(item)
            else:
                await self._process_order_data(data)
                
        except Exception as e:
            logger.error(f"주문 업데이트 처리 중 오류: {str(e)}")

    async def _process_order_data(self, data: Dict):
        """개별 주문 데이터 처리"""
        try:
            order_data = data.get('data', {})
            if not order_data:
                return

            # 주문 상태에 따른 메시지 생성
            status = order_data.get('orderStatus')
            if status == 'Created':
                message = self.monitor_formatter.format_order_created(order_data)
            elif status == 'Filled':
                message = self.monitor_formatter.format_order_filled(order_data)
            elif status == 'Cancelled':
                message = self.monitor_formatter.format_order_cancelled(order_data)
            else:
                return

            # 텔레그램으로 알림 전송
            if message:
                await self.bot.send_order_notification(message)
                
        except Exception as e:
            logger.error(f"주문 데이터 처리 중 오류: {str(e)}")

    async def _handle_position_update(self, data: Dict):
        """포지션 업데이트 처리"""
        try:
            # 데이터가 리스트인 경우 각 항목 처리
            if isinstance(data, list):
                for item in data:
                    await self._process_position_data(item)
            else:
                await self._process_position_data(data)
                
        except Exception as e:
            logger.error(f"포지션 업데이트 처리 중 오류: {str(e)}")

    async def _process_position_data(self, data: Dict):
        """개별 포지션 데이터 처리"""
        try:
            position_data = data.get('data', {})
            if not position_data:
                return

            # 포지션 메시지 생성
            message = self.monitor_formatter.format_position_update(position_data)
            
            # 텔레그램으로 알림 전송
            if message:
                await self.bot.send_position_notification(message)
                
        except Exception as e:
            logger.error(f"포지션 데이터 처리 중 오류: {str(e)}")

    async def _handle_execution_update(self, data: Dict):
        """체결 업데이트 처리"""
        try:
            # 데이터가 리스트인 경우 각 항목 처리
            if isinstance(data, list):
                for item in data:
                    await self._process_execution_data(item)
            else:
                await self._process_execution_data(data)
                
        except Exception as e:
            logger.error(f"체결 업데이트 처리 중 오류: {str(e)}")

    async def _process_execution_data(self, data: Dict):
        """개별 체결 데이터 처리"""
        try:
            execution_data = data.get('data', {})
            if not execution_data:
                return

            order_id = execution_data.get('orderId')
            if not order_id:
                return

            current_time = time.time()
            
            # 새로운 주문이면 버퍼 초기화
            if order_id not in self._execution_buffer:
                self._execution_buffer[order_id] = {
                    'symbol': execution_data.get('symbol'),
                    'side': execution_data.get('side'),
                    'total_qty': 0,
                    'avg_price': 0,
                    'executions': []
                }

            # 체결 정보 누적
            exec_qty = float(execution_data.get('execQty', 0))
            exec_price = float(execution_data.get('execPrice', 0))
            
            buffer = self._execution_buffer[order_id]
            buffer['executions'].append({
                'qty': exec_qty,
                'price': exec_price,
                'time': current_time
            })
            
            # 평균 가격과 총 수량 계산
            total_value = 0
            total_qty = 0
            for exec in buffer['executions']:
                total_value += exec['qty'] * exec['price']
                total_qty += exec['qty']
            
            buffer['total_qty'] = total_qty
            buffer['avg_price'] = total_value / total_qty if total_qty > 0 else 0

            # 알림 전송 여부 결정
            last_notification = self._last_notification.get(order_id, 0)
            should_notify = (
                current_time - last_notification >= self._notification_interval or  # 일정 시간이 지났거나
                len(buffer['executions']) == 1 or  # 첫 체결이거나
                buffer['total_qty'] >= float(execution_data.get('orderQty', 0))  # 주문이 완전히 체결됐을 때
            )

            if should_notify:
                # 누적된 체결 정보로 메시지 생성
                message = (
                    f"💫 체결 알림 (누적)\n"
                    f"심볼: {buffer['symbol']}\n"
                    f"방향: {buffer['side']}\n"
                    f"체결 수량: {buffer['total_qty']:.3f}\n"
                    f"평균 가격: {buffer['avg_price']:.1f}"
                )
                
                await self.bot.send_message_to_all(message, self.bot.MSG_TYPE_EXECUTION)
                self._last_notification[order_id] = current_time
                
                # 완전 체결된 경우 버퍼 정리
                if buffer['total_qty'] >= float(execution_data.get('orderQty', 0)):
                    del self._execution_buffer[order_id]
                    del self._last_notification[order_id]

        except Exception as e:
            logger.error(f"체결 데이터 처리 중 오류: {str(e)}")
