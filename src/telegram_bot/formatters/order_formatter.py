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
    
    def format_order(self, order_data: Dict) -> str:
        """주문 정보 통합 포맷팅"""
        try:
            # BTC 수량 계산 (가용잔고 * 목표비율 * 레버리지 / 진입가)
            btc_quantity = self._calculate_btc_quantity(order_data)
            
            message = f"""📝 {'🟢' if order_data['side'] == 'Buy' else '🔴'} 주문 생성 완료 ({self._get_current_time()})

📋 주문 정보:
• 심볼: {order_data['symbol']}
• 방향: {'롱' if order_data['side'] == 'Buy' else '숏'}
• 레버리지: {order_data['leverage']}x

💰 거래 정보:
• 진입가: ${float(order_data['entry_price']):,.2f}
• 수량: {order_data['position_size']}% ({btc_quantity:.3f} BTC)
• 손절가: ${float(order_data['stop_loss']):,.2f}
• 익절가: ${float(order_data['take_profit1']):,.2f}

📊 상태:
• 주문상태: {order_data.get('status', 'NEW')}
• 주문ID: {order_data.get('order_id', '-')}"""
            
            return message

        except Exception as e:
            logger.error(f"주문 포맷팅 중 오류: {str(e)}")
            return "❌ 포맷팅 오류"

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
                f"• 진입가: ${self._format_number(params.get('entry_price', 0))}",
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
            entry_price = float(order_data['entry_price'])
            position_size = float(order_data['position_size'])
            leverage = float(order_data['leverage'])
            
            # 예시: 10만 USDT * 10% * 5x / 95000 = 약 0.053 BTC
            return (100000 * (position_size / 100) * leverage) / entry_price
        except Exception as e:
            logger.error(f"BTC 수량 계산 중 오류: {str(e)}")
            return 0.0
