import logging
from typing import Dict, List, Tuple
from decimal import Decimal
from datetime import datetime
import json
import traceback

logger = logging.getLogger('order_formatter')

class OrderFormatter:
    """주문 정보 포맷팅 클래스"""

    ORDER_TYPES = {'LIMIT', 'MARKET', 'STOP', 'TAKE_PROFIT'}
    ORDER_SIDES = {'BUY', 'SELL'}
    ORDER_STATUSES = {'NEW', 'PARTIALLY_FILLED', 'FILLED', 'CANCELED', 'REJECTED'}
    
    def __init__(self):
        self.current_time = datetime.now()

    def _get_current_time(self) -> str:
        """현재 시간 포맷팅"""
        return self.current_time.strftime("%Y-%m-%d %H:%M:%S KST")

    @classmethod
    def _validate_order(cls, order: Dict) -> Tuple[bool, str]:
        """주문 데이터 검증"""
        if not order:
            return False, "주문 정보가 없습니다."
            
        required_fields = {
            'type': str,
            'side': str,
            'price': (int, float),
            'amount': (int, float),
            'status': str
        }
        
        for field, expected_type in required_fields.items():
            value = order.get(field)
            if value is None:
                return False, f"필수 필드 누락: {field}"
            if not isinstance(value, expected_type):
                return False, f"잘못된 데이터 타입: {field}"
                
        order_type = order['type'].upper()
        if order_type not in cls.ORDER_TYPES:
            return False, f"잘못된 주문 유형: {order_type}"
            
        side = order['side'].upper()
        if side not in cls.ORDER_SIDES:
            return False, f"잘못된 주문 방향: {side}"
            
        status = order['status'].upper()
        if status not in cls.ORDER_STATUSES:
            return False, f"잘못된 주문 상태: {status}"
            
        return True, ""
    
    @staticmethod
    def _format_number(value: float, decimals: int = 2) -> str:
        """숫자 포맷팅"""
        try:
            decimal_value = Decimal(str(value))
            return f"{float(decimal_value.normalize()):.{decimals}f}"
        except:
            return str(value)
    
    @classmethod
    def _get_order_emoji(cls, side: str, status: str) -> str:
        """주문 상태별 이모지 선택"""
        status_emojis = {
            'NEW': '📝',
            'PARTIALLY_FILLED': '⏳',
            'FILLED': '✅',
            'CANCELED': '❌',
            'REJECTED': '⛔'
        }
        
        side_emoji = "🟢" if side == "BUY" else "🔴"
        status_emoji = status_emojis.get(status, '❓')
        
        return f"{status_emoji} {side_emoji}"
    
    def format_order(self, order: Dict) -> str:
        """주문 정보 포맷팅"""
        try:
            if not order:
                return "주문 정보 없음"

            # 주문 정보 추출
            entry_price = float(order.get('price', order.get('entry_price', 0)))
            btc_quantity = float(order.get('qty', order.get('amount', 0)))  
            leverage = int(order.get('leverage', 1))
            stop_loss = float(order.get('stopLoss', order.get('stop_loss', 0)))
            take_profit = float(order.get('takeProfit', order.get('take_profit', 0)))
            
            # 이모지 설정
            side = order.get('side', '').lower()
            position_side = '숏' if side == 'sell' else '롱'
            side_emoji = "🔴" if side == 'sell' else "🟢"

            # 메시지 구성
            message = (
                f"🤖 자동매매 신호\n\n"
                f"{side_emoji} {position_side} 포지션\n"
                f"레버리지: {leverage}x\n"
                f"주문수량: {btc_quantity:.3f} BTC\n"
                f"진입가격: ${entry_price:,.0f}\n"
                f"손절가격: ${stop_loss:,.0f}\n"
                f"목표가격: ${take_profit:,.0f}\n\n"
                f"시간: {self._get_current_time()}"
            )
            
            return message
            
        except Exception as e:
            logger.error(f"주문 정보 포맷팅 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return "주문 정보 포맷팅 실패"

    @classmethod
    def format_open_orders(cls, orders: List[Dict]) -> str:
        """미체결 주문 목록 포맷팅"""
        try:
            if not orders:
                return "미체결 주문이 없습니다."
                
            # 주문을 심볼별로 그룹화
            orders_by_symbol = {}
            for order in orders:
                symbol = order.get('symbol', 'UNKNOWN')
                if symbol not in orders_by_symbol:
                    orders_by_symbol[symbol] = []
                orders_by_symbol[symbol].append(order)
            
            # 심볼별로 주문 정보 포맷팅
            messages = ["📋 미체결 주문 목록\n"]
            
            for symbol, symbol_orders in orders_by_symbol.items():
                messages.append(f"== {symbol} ==")
                for order in symbol_orders:
                    side = order.get('side', '').upper()
                    side_emoji = "🟢" if side == "BUY" else "🔴"
                    price = float(order.get('price', 0))
                    amount = float(order.get('amount', 0))
                    
                    messages.append(
                        f"{side_emoji} {side} {cls._format_number(amount, 3)}개"
                        f" @ ${cls._format_number(price)}"
                    )
                messages.append("")
            
            return "\n".join(messages).strip()

        except Exception as e:
            logger.error(f"미체결 주문 포맷팅 중 오류: {str(e)}")
            return "미체결 주문 포맷팅 실패"

    @classmethod
    async def format_trade_signal(cls, trading_signal: Dict) -> str:
        """거래 신호 통일된 포맷"""
        try:
            signal = trading_signal['trading_signals']
            action = signal['primary_signal']['action']
            
            message = [
                "💡 거래 신호\n",
                f"• 방향: {action}",
                f"• 진입가: ${cls._format_number(signal['entry_price'])}",
                f"• 손절가: ${cls._format_number(signal['stopLoss'])}",
                f"• 목표가: ${cls._format_number(signal['takeProfit'])}",
                f"• 레버리지: {signal['recommended_leverage']}x",
                f"• 크기: {signal['position_size']}%",
                f"• 신뢰도: {trading_signal['신뢰도']}%"
            ]
            
            return "\n".join(message)
            
        except Exception as e:
            logger.error(f"거래 신호 포맷팅 중 오류: {str(e)}")
            return "❌ 포맷팅 오류"

    @classmethod
    def format_trade_result(cls, order_result: Dict) -> str:
        """거래 실행 결과 포맷"""
        try:
            return "\n".join([
                "✅ 거래 실행 완료\n",
                f"• 주문 ID: {order_result['id']}",
                f"• 상태: {order_result['status']}",
                f"• 체결가: ${cls._format_number(order_result['price'])}",
                f"• 수량: {cls._format_number(order_result['amount'], 4)}"
            ])
            
        except Exception as e:
            logger.error(f"거래 결과 포맷팅 중 오류: {str(e)}")
            return "❌ 포맷팅 오류"

    def format_order_failure(self, params: Dict, error_msg: str) -> str:
        """주문 실패 메시지 포맷팅"""
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
            side = 'BUY' if params.get('position_suggestion') == 'BUY' else 'SELL'
            
            message = [
                f"📝 ❌ 주문 실패 ({current_time})",
                "",
                "📋 주문 정보:",
                f"• 심볼: {params.get('symbol', 'BTCUSDT')}",
                f"• 방향: {'롱' if side == 'BUY' else '숏'}",
                f"• 레버리지: {params.get('leverage', '10')}x",
                "",
                "💰 거래 정보:",
                f"• 진입가: ${self._format_number(params.get('price', 0))}",
                f"• 수량: {params.get('position_size')}% (계산 중)",
                f"• 손절가: ${self._format_number(params.get('stop_loss', 0))}",
                f"• 익절가: ${self._format_number(params.get('take_profit1', 0))}",
                "",
                "📊 상태:",
                "• 주문상태: REJECTED",
                f"• {error_msg}"
            ]
            
            return "\n".join(message)
            
        except Exception as e:
            logger.error(f"실패 메시지 포맷팅 중 오류: {str(e)}")
            return "❌ 포맷팅 오류"

    def format_confidence_message(self, result: Dict) -> str:
        """매매 신호 부재 관련 메시지 포맷"""
        try:
            message = [
                "⚠ 자동매매 실행 안됨\n",
                "💡 현재 상태:",
                f"• 신뢰도: {result.get('confidence', 0)}%",
                f"• 추세 강도: {result.get('strength', 0)}%",
                "• 자동매매는 신뢰도와 추세 강도가 충분할 때 실행"
            ]
            
            return "\n".join(message)
            
        except Exception as e:
            logger.error(f"신뢰도 메시지 포맷팅 중 오류: {str(e)}")
            return "❌ 포맷팅 오류"

    def _calculate_btc_quantity(self, order_data: Dict) -> float:
        """BTC 수량 계산"""
        try:
            price = float(order_data['price'])
            position_size = float(order_data['position_size'])
            leverage = float(order_data['leverage'])
            
            # 예시: 10만 USDT * 10% * 5x / 95000 = 약 0.053 BTC
            return (100000 * (position_size / 100) * leverage) / price
        except Exception as e:
            logger.error(f"BTC 수량 계산 중 오류: {str(e)}")
            return 0.0

    def format_order_message(self, order_params: Dict) -> str:
        """주문 메시지 포맷팅"""
        try:
            # BTC 수량 계산
            btc_size = self._calculate_btc_size(order_params)
            
            # 주문 타입에 따른 메시지
            if order_params.get('reduceOnly'):
                return self._format_reduce_message(order_params, btc_size)
            else:
                return self._format_new_position_message(order_params, btc_size)
                    
        except Exception as e:
            logger.error(f"주문 포맷팅 중 오류: {str(e)}")
            return "주문 메시지 생성 실패"

    def _calculate_btc_size(self, order_params: Dict) -> float:
        """BTC 수량 계산"""
        try:
            price = float(order_params.get('price', 0))
            qty = float(order_params.get('qty', 0))
            position_value = price * qty
            return position_value
        except Exception as e:
            logger.error(f"BTC 수량 계산 중 오류: {str(e)}")
            return 0.0

    def _format_new_position_message(self, order_params: Dict, btc_size: float) -> str:
        """신규 포지션 생성 메시지"""
        try:
            side = order_params.get('side', '')
            symbol = order_params.get('symbol', '')
            price = order_params.get('price', '')
            stop_loss = order_params.get('stopLoss', '')
            take_profit = order_params.get('takeProfit', '')
            
            message = (
                f"🔄 신규 {side} 주문\n"
                f"심볼: {symbol}\n"
                f"수량: {btc_size} BTC\n"
                f"진입가: ${price}\n"
                f"손절가: ${stop_loss}\n"
                f"익절가: ${take_profit}\n"
                f"\n"
                f"주문시각: {self._get_current_time()}"
            )
            return message
            
        except Exception as e:
            logger.error(f"신규 포지션 메시지 포맷팅 중 오류: {str(e)}")
            return "메시지 생성 실패"

    def _format_reduce_message(self, order_params: Dict, btc_size: float) -> str:
        """포지션 감소 메시지"""
        try:
            side = order_params.get('side', '')
            symbol = order_params.get('symbol', '')
            price = order_params.get('price', '')
            
            message = (
                f"🔄 포지션 {side} 주문\n"
                f"심볼: {symbol}\n"
                f"수량: {btc_size} BTC\n"
                f"가격: ${price}\n"
                f"\n"
                f"주문시각: {self._get_current_time()}"
            )
            return message
            
        except Exception as e:
            logger.error(f"포지션 감소 메시지 포맷팅 중 오류: {str(e)}")
            return "메시지 생성 실패"
