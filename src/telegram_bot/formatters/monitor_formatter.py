import logging
from typing import Dict, Union
from .base_formatter import BaseFormatter

logger = logging.getLogger(__name__)

class MonitorFormatter(BaseFormatter):
    """실시간 모니터링 알림 포맷터"""

    # 트레이딩 관련 이모지
    TRADING_EMOJIS = {
        'order_created': '🔔',
        'order_filled': '✅',
        'order_cancelled': '❌',
        'position_update': '📊',
        'position_closed': '🔚',
        'execution': '💫',
        'long': '🟢',
        'short': '🔴',
        'profit': '🟢',
        'loss': '🔴'
    }

    def format_balance(self, balance: Dict) -> str:
        """잔고 정보 포맷팅"""
        try:
            if not self.validate_data(balance, ['total_equity', 'available_balance', 'used_margin']):
                return self.format_error("잔고 데이터 누락")

            total_equity = float(balance.get('total_equity', 0))
            available_balance = float(balance.get('available_balance', 0))
            used_margin = float(balance.get('used_margin', 0))
            
            return (
                f"💰 계정 잔고\n\n"
                f"총 자산: {self.format_number(total_equity)} USDT\n"
                f"사용 가능: {self.format_number(available_balance)} USDT\n"
                f"사용 중 마진: {self.format_number(used_margin)} USDT"
            )
        except Exception as e:
            logger.error(f"잔고 정보 포맷 오류: {str(e)}")
            return self.format_error("잔고 정보 포맷 오류")

    def format_position(self, position: Dict) -> str:
        """포지션 정보 포맷팅"""
        try:
            if not self.validate_data(position, ['symbol', 'side', 'size', 'entry_price', 'leverage']):
                return self.format_error("포지션 데이터 누락")

            symbol = position.get('symbol', '')
            side = position.get('side', '')  # Long/Short
            size = float(position.get('size', 0))
            entry_price = float(position.get('entry_price', 0))
            leverage = position.get('leverage', '')
            
            # 한글로 포지션 방향 표시
            direction = "롱" if side == "Long" else "숏"
            direction_emoji = self.TRADING_EMOJIS['long'] if side == "Long" else self.TRADING_EMOJIS['short']
            
            return (
                f"{self.TRADING_EMOJIS['position_update']} 포지션 정보\n\n"
                f"코인: {symbol}\n"
                f"방향: {direction_emoji} {direction}\n"
                f"크기: {self.format_number(size, 4)} BTC\n"
                f"진입가: {self.format_number(entry_price)}\n"
                f"레버리지: {leverage}x"
            )
        except Exception as e:
            logger.error(f"포지션 정보 포맷 오류: {str(e)}")
            return self.format_error("포지션 정보 포맷 오류")

    def format_status(self, status: Dict[str, Union[bool, str]]) -> str:
        """상태 정보 포맷팅"""
        try:
            if not self.validate_data(status, ['connection', 'monitoring']):
                return self.format_error("상태 데이터 누락")

            connection = status.get('connection', False)
            monitoring = status.get('monitoring', False)
            
            connection_emoji = "🟢" if connection else "🔴"
            monitoring_emoji = "🟢" if monitoring else "🔴"
            
            return (
                f"📊 모니터링 상태\n\n"
                f"연결: {connection_emoji} {'연결됨' if connection else '연결 끊김'}\n"
                f"모니터링: {monitoring_emoji} {'활성화' if monitoring else '비활성화'}"
            )
        except Exception as e:
            logger.error(f"상태 정보 포맷 오류: {str(e)}")
            return self.format_error("상태 정보 포맷 오류")

    def format_order_created(self, order_data: Dict) -> str:
        """주문 생성 알림 포맷"""
        try:
            if not self.validate_data(order_data, ['symbol', 'orderType', 'side', 'price', 'qty']):
                return self.format_error("주문 데이터 누락")

            symbol = order_data.get('symbol', '')
            order_type = order_data.get('orderType', '')
            side = order_data.get('side', '')  # 주문 방향 (Buy/Sell)
            price = float(order_data.get('price', 0))
            qty = float(order_data.get('qty', 0))
            
            return (
                f"{self.TRADING_EMOJIS['order_created']} 주문 생성\n\n"
                f"코인: {symbol}\n"
                f"유형: {order_type}\n"
                f"방향: {side}\n"
                f"가격: {self.format_number(price)}\n"
                f"수량: {self.format_number(qty, 4)} BTC"
            )
        except Exception as e:
            logger.error(f"주문 생성 알림 포맷 오류: {str(e)}")
            return self.format_error("주문 생성 알림 포맷 오류")

    def format_order_filled(self, order_data: Dict) -> str:
        """주문 체결 알림 포맷"""
        try:
            if not self.validate_data(order_data, ['symbol', 'side', 'price', 'qty']):
                return self.format_error("주문 데이터 누락")

            symbol = order_data.get('symbol', '')
            side = order_data.get('side', '')  # 주문 방향 (Buy/Sell)
            price = float(order_data.get('price', 0))
            qty = float(order_data.get('qty', 0))
            
            return (
                f"{self.TRADING_EMOJIS['order_filled']} 주문 체결\n\n"
                f"코인: {symbol}\n"
                f"방향: {side}\n"
                f"체결가: {self.format_number(price)}\n"
                f"수량: {self.format_number(qty, 4)} BTC"
            )
        except Exception as e:
            logger.error(f"주문 체결 알림 포맷 오류: {str(e)}")
            return self.format_error("주문 체결 알림 포맷 오류")

    def format_order_cancelled(self, order_data: Dict) -> str:
        """주문 취소 알림 포맷"""
        try:
            if not self.validate_data(order_data, ['symbol', 'orderType', 'side', 'price']):
                return self.format_error("주문 데이터 누락")

            symbol = order_data.get('symbol', '')
            order_type = order_data.get('orderType', '')
            side = order_data.get('side', '')
            price = float(order_data.get('price', 0))
            
            return (
                f"{self.TRADING_EMOJIS['order_cancelled']} 주문 취소\n\n"
                f"코인: {symbol}\n"
                f"유형: {order_type}\n"
                f"방향: {side}\n"
                f"가격: {self.format_number(price)}"
            )
        except Exception as e:
            logger.error(f"주문 취소 알림 포맷 오류: {str(e)}")
            return self.format_error("주문 취소 알림 포맷 오류")

    def format_position_update(self, position_data: Dict) -> str:
        """포지션 업데이트 알림 포맷"""
        try:
            if not self.validate_data(position_data, ['symbol', 'side', 'size', 'entryPrice', 'leverage']):
                return self.format_error("포지션 데이터 누락")

            symbol = position_data.get('symbol', '')
            side = position_data.get('side', '')  # Long/Short
            size = float(position_data.get('size', 0))
            entry_price = float(position_data.get('entryPrice', 0))
            leverage = position_data.get('leverage', '')
            
            # 한글로 포지션 방향 표시
            direction = "롱" if side == "Long" else "숏"
            direction_emoji = self.TRADING_EMOJIS['long'] if side == "Long" else self.TRADING_EMOJIS['short']
            
            return (
                f"{self.TRADING_EMOJIS['position_update']} 포지션 업데이트\n\n"
                f"코인: {symbol}\n"
                f"방향: {direction_emoji} {direction}\n"
                f"크기: {self.format_number(size, 4)} BTC\n"
                f"진입가: {self.format_number(entry_price)}\n"
                f"레버리지: {leverage}x"
            )
        except Exception as e:
            logger.error(f"포지션 업데이트 알림 포맷 오류: {str(e)}")
            return self.format_error("포지션 업데이트 알림 포맷 오류")

    def format_position_closed(self, position_data: Dict) -> str:
        """포지션 청산 알림 포맷"""
        try:
            if not self.validate_data(position_data, ['symbol', 'side', 'exitPrice', 'pnl']):
                return self.format_error("포지션 데이터 누락")

            symbol = position_data.get('symbol', '')
            side = position_data.get('side', '')  # Long/Short
            exit_price = float(position_data.get('exitPrice', 0))
            pnl = float(position_data.get('pnl', 0))
            
            # 한글로 포지션 방향 표시
            direction = "롱" if side == "Long" else "숏"
            direction_emoji = self.TRADING_EMOJIS['long'] if side == "Long" else self.TRADING_EMOJIS['short']
            pnl_emoji = self.TRADING_EMOJIS['profit'] if pnl >= 0 else self.TRADING_EMOJIS['loss']
            
            return (
                f"{self.TRADING_EMOJIS['position_closed']} 포지션 청산\n\n"
                f"코인: {symbol}\n"
                f"방향: {direction_emoji} {direction}\n"
                f"청산가: {self.format_number(exit_price)}\n"
                f"수익: {pnl_emoji} {self.format_number(pnl)} USDT"
            )
        except Exception as e:
            logger.error(f"포지션 청산 알림 포맷 오류: {str(e)}")
            return self.format_error("포지션 청산 알림 포맷 오류")

    def format_execution(self, execution_data: Dict) -> str:
        """체결 정보 알림 포맷"""
        try:
            if not self.validate_data(execution_data, ['symbol', 'side', 'price', 'qty', 'fee']):
                return self.format_error("체결 데이터 누락")

            symbol = execution_data.get('symbol', '')
            side = execution_data.get('side', '')  # Buy/Sell
            price = float(execution_data.get('price', 0))
            qty = float(execution_data.get('qty', 0))
            fee = float(execution_data.get('fee', 0))
            
            return (
                f"{self.TRADING_EMOJIS['execution']} 체결 완료\n\n"
                f"코인: {symbol}\n"
                f"방향: {side}\n"
                f"체결가: {self.format_number(price)}\n"
                f"수량: {self.format_number(qty, 4)} BTC\n"
                f"수수료: {self.format_number(fee, 6)} USDT"
            )
        except Exception as e:
            logger.error(f"체결 정보 알림 포맷 오류: {str(e)}")
            return self.format_error("체결 정보 알림 포맷 오류")
