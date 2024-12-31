import logging
from typing import Dict, Optional, Tuple
from decimal import Decimal

logger = logging.getLogger('position_formatter')

class PositionFormatter:
    """포지션 정보 포맷팅 클래스"""

    POSITION_SIDES = {'LONG', 'SHORT'}
    MIN_POSITION_SIZE = 0.001  # 최소 포지션 크기
    
    @classmethod
    def _validate_position(cls, position: Dict) -> Tuple[bool, str]:
        """포지션 데이터 검증"""
        if not position:
            return False, "포지션 정보가 없습니다."
            
        required_fields = {
            'symbol': str,
            'entryPrice': (int, float),
            'leverage': (int, float)
        }
        
        for field, expected_type in required_fields.items():
            value = position.get(field)
            if value is None:
                return False, f"필수 필드 누락: {field}"
            if not isinstance(value, expected_type):
                return False, f"잘못된 데이터 타입: {field}"
                
        size = float(position.get('contracts', position.get('size', 0)) or 0)
        if abs(size) < cls.MIN_POSITION_SIZE:
            return False, "포지션 크기가 너무 작습니다."
            
        return True, ""
    
    @staticmethod
    def _format_number(value: float, decimals: int = 2) -> str:
        """숫자 포맷팅"""
        try:
            decimal_value = Decimal(str(value))
            return f"{float(decimal_value.normalize()):.{decimals}f}"
        except:
            return str(value)
    
    @staticmethod
    def _get_pnl_emoji(pnl: float) -> str:
        """손익에 따른 이모지 선택"""
        if pnl > 0:
            return "📈"  # 수익
        elif pnl < 0:
            return "📉"  # 손실
        return "➖"  # 변동 없음
    
    @classmethod
    def format_position(cls, position: Optional[Dict]) -> str:
        """포지션 정보 포맷팅"""
        try:
            if position is None:
                return "포지션 정보가 없습니다."
                
            # 기본 정보 추출
            size = float(position.get('size', 0))
            side = "롱🟢" if position['side'] == 'BUY' else "숏🔴"
            entry_price = float(position['entryPrice'])
            leverage = float(position['leverage'])
            
            # 메시지 구성
            position_message = [
                "📊 현재 포지션",
                "",
                f"심볼: {position['symbol']}",
                f"방향: {side}",
                f"규모: {cls._format_number(abs(size), 3)}",
                f"진입가: ${cls._format_number(entry_price)}",
                f"레버리지: {int(leverage)}x"
            ]
            
            # 청절/익절가 정보 (설정되지 않은 경우도 표시)
            sl = position.get('stopLoss', 0)
            tp = position.get('takeProfit', 0)
            position_message.append(f"손절가: {'설정 없음' if sl == 0 else f'${cls._format_number(float(sl))}'}")
            position_message.append(f"익절가: {'설정 없음' if tp == 0 else f'${cls._format_number(float(tp))}'}")
            
            # 청산가 정보
            if position.get('liquidationPrice'):
                position_message.append(
                    f"청산가: ${cls._format_number(float(position['liquidationPrice']))}"
                )
            
            # 미실현 손익 정보
            unrealized_pnl = float(position.get('unrealizedPnl', 0))
            if unrealized_pnl != 0:
                pnl_emoji = cls._get_pnl_emoji(unrealized_pnl)
                position_message.append(
                    f"미실현 손익: {pnl_emoji} ${cls._format_number(unrealized_pnl)}"
                )
            
            return "\n".join(position_message)
            
        except Exception as e:
            logger.error(f"포지션 포맷팅 중 오류: {str(e)}")
            return "포지션 포맷팅 실패"

    @classmethod
    def format_balance(cls, balance: Optional[Dict]) -> str:
        """잔고 정보 포맷팅"""
        try:
            if not balance:
                return "잔고 정보를 가져올 수 없습니다."

            # USDT 잔고 추출
            usdt_balance = balance.get('USDT', {})
            if not usdt_balance:
                return "USDT 잔고 정보가 없습니다."

            # 잔고 정보 계산
            free = float(usdt_balance.get('free', 0))
            used = float(usdt_balance.get('used', 0))
            total = float(usdt_balance.get('total', 0))
            
            # 메시지 구성
            balance_message = [
                "💰 계정 잔고",
                "",
                f"사용 가능: ${cls._format_number(free)}",
                f"사용 중: ${cls._format_number(used)}",
                f"총 잔고: ${cls._format_number(total)}"
            ]
            
            # 사용률 계산 및 표시
            if total > 0:
                usage_rate = (used / total) * 100
                balance_message.append(f"사용률: {cls._format_number(usage_rate)}%")
            
            return "\n".join(balance_message)
            
        except Exception as e:
            logger.error(f"잔고 포맷팅 중 오류: {str(e)}")
            return "잔고 포맷팅 실패"
