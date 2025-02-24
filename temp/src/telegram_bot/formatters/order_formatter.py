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
    
    def format_order(self, order: Dict) -> str:
        """주문 정보 통합 포맷팅"""
        try:
            # 기본 정보 추출
            side = order.get('side', '').upper()
            status = order.get('status', 'NEW').upper()
            emojis = self._get_order_emoji(side, status)
            
            # 현재 시간
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
            
            # 수량 표시 형식 결정
            is_btc_unit = order.get('is_btc_unit', True)
            quantity = order.get('amount', 0)
            position_size = order.get('position_size', '')
            
            # BTC 단위와 퍼센트 모두 표시하도록 수정
            if is_btc_unit:
                quantity_display = f"{self._format_number(quantity, 3)} BTC"
            else:
                quantity_display = f"{position_size}% ({self._format_number(quantity, 3)} BTC)"
            
            # 주문 유형에 따라 다른 메시지 포맷 사용
            if order.get('skip_reason') == 'confidence':
                return self.format_confidence_message(order)
            elif order.get('skip_reason') == 'min_size':
                message = [
                    "📢 주문 수량 부족",
                    "",
                    "📋 주문 정보:",
                    f"• 심볼: {order.get('symbol', 'BTCUSDT')}",
                    f"• 방향: {'롱' if side == 'BUY' else '숏'}",
                    f"• 레버리지: {order.get('leverage', '10')}x",
                    "",
                    "💰 수량 정보:",
                    f"• 계산된 수량: {self._format_number(order.get('amount', 0), 3)} BTC",
                    f"• 최소 주문 수량: 0.001 BTC",
                    "",
                    "💡 주문이 너뛰어졌습니다."
                ]
            elif order.get('skip_reason') == 'size_diff':
                if order.get('leverage_check'):
                    message = [
                        "✅ 레버리지 확인",
                        "",
                        "📋 포지션 정보:",
                        f"• 심볼: {order.get('symbol', 'BTCUSDT')}",
                        f"• 방향: {'롱' if side == 'BUY' else '숏'}",
                        f"• 현재 레버리지: {order.get('leverage', '5')}x",
                        f"• 목표 레버리지: {order.get('target_leverage', '5')}x",
                        "",
                        "💡 레버리지 차이가 허용 범위 내여서 현재 설정을 유지합니다."
                    ]
                else:
                    message = [
                        "✅ 포지션 수량 확인",
                        "",
                        "📋 포지션 정보:",
                        f"• 심볼: {order.get('symbol', 'BTCUSDT')}",
                        f"• 방향: {'롱' if side == 'BUY' else '숏'}",
                        f"• 레버리지: {order.get('leverage', '5')}x",
                        "",
                        "💰 수량 정보:",
                        f"• 현재 수량: {self._format_number(order.get('current_size', 0), 3)} BTC",
                        f"• 목표 수량: {self._format_number(order.get('target_size', 0), 3)} BTC",
                        f"• 차이: {self._format_number(abs(order.get('size_diff', 0)), 3)} BTC",
                        "",
                        "💡 현재 포지션이 목표 범위 내에 있어 조정이 필요하지 않습니다."
                    ]
            else:
                # 기존 정상 주문 메시지 유지
                message = [
                    f"{emojis} 주문 생성 완료 ({current_time})",
                    "",
                    "📋 주문 정보:",
                    f"• 심볼: {order.get('symbol', 'BTCUSDT')}",
                    f"• 방향: {'롱' if side == 'BUY' else '숏'}",
                    f"• 레버리지: {order.get('leverage', '10')}x",
                    "",
                    "💰 거래 정보:",
                    f"• 진입가: ${self._format_number(order.get('price', 0))}",
                    f"• 수량: {quantity_display}"  # 퍼센트와 BTC 단위 모두 표시
                ]
                
                # 신규 주문인 경우에만 손절/익절가 표시
                if not order.get('reduceOnly', False):
                    message.extend([
                        f"• 손절가: ${self._format_number(order.get('stopLoss', 0))}",
                        f"• 익절가: ${self._format_number(order.get('takeProfit', 0))}"
                    ])
                
                message.extend([
                    "",
                    "📊 상태:",
                    f"• 주문상태: {status}",
                    f"• 주문ID: {order.get('order_id', '-')}"
                ])
            
            return "\n".join(message)

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
            
            message = [
                f"❌ 주문 실패 ({current_time})",
                "",
                "📋 주문 정보:",
                f"• 심볼볼: {params.get('symbol', 'BTCUSDT')}",
                f"• 방향: {'롱' if params['side'] == 'BUY' else '숏'}",
                f"• 레버리지: {params.get('leverage', '10')}x",
                "",
                "💰 거래 정보:",
                f"• 진입가: ${self._format_number(params.get('entry_price', 0))}",
                f"• 수량: {params.get('position_size')}%",
                "",
                "⚠️ 오류:",
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
