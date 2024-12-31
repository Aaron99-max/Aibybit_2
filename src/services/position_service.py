import logging
import traceback
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from functools import wraps
import time

logger = logging.getLogger('position_service')

def error_handler(func):
    """에러 처리 데코레이터"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} 실행 중 에러: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    return wrapper

class PositionService:
    def __init__(self, bybit_client, config=None):
        self.bybit_client = bybit_client
        self.config = config
        self.order_service = None  # 초기에는 None으로 설정
        self.symbol = 'BTCUSDT'

    def set_order_service(self, order_service):
        """OrderService 설정"""
        self.order_service = order_service

    @error_handler
    async def get_positions(self, symbol: str) -> List[Dict]:
        """포지션 목록 조회"""
        try:
            logger.info(f"포지션 목록 조회 시작: {symbol}")
            
            # 1. Raw 데이터 조회
            positions = await self.bybit_client.get_positions(symbol)
            
            # 2. 포지션 데이터 파싱
            if positions:
                return self._parse_positions(positions, symbol)
            
            logger.info("활성 포지션 없음")
            return []
            
        except Exception as e:
            logger.error(f"포지션 목록 조회 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return []

    def _parse_positions(self, positions: List[Dict], symbol: str) -> List[Dict]:
        """포지션 데이터 파싱"""
        active_positions = []
        
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            
            size = float(pos.get('size', 0) or pos.get('contracts', 0) or 
                        pos.get('positionAmt', 0) or 0)
            
            if abs(size) > 0:
                active_pos = {
                    'symbol': pos.get('symbol', '').replace('USDT', ''),
                    'side': pos.get('side', 'None').upper(),
                    'size': abs(size),
                    'leverage': int(float(pos.get('leverage', 1))),
                    'entryPrice': float(pos.get('avgPrice', 0) or 0),
                    'markPrice': float(pos.get('markPrice', 0) or 0),
                    'unrealizedPnl': float(pos.get('unrealisedPnl', 0) or 0),
                    'liquidationPrice': float(pos.get('liqPrice', 0) or 0),
                    'stopLoss': float(pos.get('stopLoss', 0) or 0),
                    'takeProfit': float(pos.get('takeProfit', 0) or 0)
                }
                logger.info(f"활성 포지션: {active_pos['symbol']} {active_pos['side']} x{active_pos['leverage']} "
                           f"크기: {active_pos['size']} 진입가: {active_pos['entryPrice']}")
                active_positions.append(active_pos)
        
        return active_positions

    def safe_float(self, value, default=0):
        try:
            if value == '' or value is None:
                return default
            return float(value)
        except (ValueError, TypeError):
            return default

    @error_handler
    async def get_position(self, symbol: str) -> Optional[Dict]:
        """단일 포지션 조회"""
        positions = await self.get_positions(symbol)
        return positions[0] if positions else None

    @error_handler
    async def handle_position_for_signal(self, signal: Dict) -> bool:
        """트레이딩 신호에 따른 포지션 관리"""
        # 1. 신호 검증
        validation_result = self._validate_signal(signal)
        if not validation_result[0]:
            logger.error(validation_result[1])
            return False

        symbol = signal.get('symbol', 'BTCUSDT')
        side = signal.get('side')
        target_leverage = int(signal.get('leverage'))
        size = float(signal.get('size'))
        price = float(signal.get('entry_price'))

        # 2. 현재 포지션 확인
        current_positions = await self.get_positions(symbol)
        
        # 3. 포지션 상태에 따 처리
        if not current_positions:
            return await self._open_new_position(symbol, side, target_leverage, size, price)

        current_pos = current_positions[0]
        current_size = abs(float(current_pos.get('size', 0)))
        current_side = current_pos.get('side', '')
        current_leverage = int(current_pos.get('leverage', 1))

        if current_side == side:
            if current_leverage == target_leverage:
                return await self._adjust_position_size(symbol, side, current_size, size, price, target_leverage)
            else:
                return await self._change_leverage_position(symbol, side, current_size, size, price, 
                                                         current_leverage, target_leverage)
        else:
            return await self._reverse_position(symbol, side, current_size, size, price, target_leverage)

    def _validate_signal(self, signal: Dict) -> Tuple[bool, str]:
        """신호 데이터 검증"""
        required_fields = {
            'side': str,
            'leverage': (int, float),
            'size': (int, float),
            'entry_price': (int, float)
        }

        for field, expected_type in required_fields.items():
            value = signal.get(field)
            if value is None:
                return False, f"필수 필드 누락: {field}"
            if not isinstance(value, expected_type):
                return False, f"잘못된 이터 타입: {field}"

        side = signal.get('side')
        if side not in ['LONG', 'SHORT']:
            return False, f"잘못된 포지션 방향: {side}"

        return True, ""

    def _calculate_sl_tp(self, side: str, price: float) -> Tuple[float, float]:
        """스탑로/테이크프로핏 계산"""
        try:
            price = float(price)  # 확실하게 float으로 변환
            
            if side == 'LONG':
                stop_loss = price * 0.99  # Decimal 대신 float 사용
                take_profit = price * 1.02
            else:  # SHORT
                stop_loss = price * 1.01
                take_profit = price * 0.98
                
            return stop_loss, take_profit
            
        except Exception as e:
            logger.error(f"SL/TP 계산 중 에러: {str(e)}")
            # 기본값 반환 (진입가 기준 ±1%)
            return price * 0.99 if side == 'LONG' else price * 1.01, \
                   price * 1.01 if side == 'LONG' else price * 0.99

    async def _open_new_position(self, symbol: str, side: str, leverage: int, size: float, price: float) -> bool:
        """신규 포지션 진입"""
        try:
            logger.info(f"신규 포지션 진입 (방향: {side}, 레버리지: {leverage}x, 크기: {size})")
            
            # 스탑로스/테이크프로핏 계산
            stop_loss, take_profit = self._calculate_sl_tp(side, price)

            # OrderService를 통한 주문 실행
            order = await self.order_service.create_order(
                symbol=symbol,
                side=side,
                price=price,
                size=size,
                leverage=leverage,
                stop_loss=stop_loss,
                take_profit=take_profit,
                order_type='limit'
            )
            return order is not None
        except Exception as e:
            logger.error(f"신규 포지션 진입 중 오류: {str(e)}")
            return False

    async def _adjust_position_size(self, symbol: str, side: str, current_size: float, 
                                  target_size: float, price: float) -> bool:
        """포지션 크기 조정"""
        try:
            size_diff = target_size - current_size
            if abs(size_diff) < 0.001:  # 최소 변경 크기
                return True

            order = await self.order_service.create_order(
                symbol=symbol,
                side=side,
                price=price,
                size=abs(size_diff),
                order_type='limit'
            )
            return order is not None
        except Exception as e:
            logger.error(f"포지션 크기 조정 중 오류: {str(e)}")
            return False

    async def _change_leverage_position(self, symbol: str, side: str, current_size: float,
                                      target_size: float, price: float, current_leverage: int,
                                      target_leverage: int) -> bool:
        """레버리지 변경을 위한 포지션 재설정"""
        logger.info(f"레버리지 변경 (현재: {current_leverage}x -> 목표: {target_leverage}x)")
        
        # 1. 현재 포지션 종료
        close_side = 'buy' if side == 'SHORT' else 'sell'
        if not await self.order_service.close_position(symbol, close_side, current_size):
            return False

        # 2. 새로운 레버리지로 재진입
        return await self._open_new_position(symbol, side, target_leverage, target_size, price)

    async def _reverse_position(self, symbol: str, new_side: str, current_size: float,
                              target_size: float, price: float, target_leverage: int) -> bool:
        """반대 방향 포지션으로 전환"""
        logger.info(f"반대 방향 포지션 전환 (현재: {current_size} -> 방: {new_side}, 크기: {target_size})")
        
        # 1. 현재 포지션 종료
        close_side = 'buy' if new_side == 'LONG' else 'sell'
        if not await self.order_service.close_position(symbol, close_side, current_size):
            return False

        # 2. 반대 방향으로 진입
        return await self._open_new_position(symbol, new_side, target_leverage, target_size, price)

    @error_handler
    async def get_balance(self) -> Dict:
        """잔고 조회"""
        balance = await self.bybit_client.get_balance()
        if balance:
            logger.debug(f"Raw balance data: {balance}")
            result = {
                'timestamp': int(time.time() * 1000),
                'currencies': {}
            }
            
            # USDT 잔고
            if 'USDT' in balance:
                usdt = balance['USDT']
                result['currencies']['USDT'] = {
                    'total_equity': float(usdt.get('total', 0)),
                    'used_margin': float(usdt.get('used', 0)),
                    'available_balance': float(usdt.get('free', 0))
                }
            
            # BTC 잔고
            if 'BTC' in balance:
                btc = balance['BTC']
                result['currencies']['BTC'] = {
                    'total_equity': float(btc.get('total', 0)),
                    'used_margin': float(btc.get('used', 0)),
                    'available_balance': float(btc.get('free', 0))
                }
                
            return result
            
        logger.error("잔고 정보를 찾을 수 없습니다")
        return None

    async def _close_position(self, symbol: str, side: str, size: float, price: float) -> bool:
        """포지션 청산 (지정)"""
        try:
            close_side = 'sell' if side == 'long' else 'buy'
            order = await self.order_service.create_order(
                symbol=symbol,
                side=close_side,
                price=price,
                size=size,
                order_type='limit',
                reduce_only=True
            )
            return order is not None
        except Exception as e:
            logger.error(f"포지션 청산 중 오류: {str(e)}")
            return False

    async def get_current_position(self) -> Optional[Dict]:
        """현재 포지션 조회"""
        try:
            # 기존의 get_position 메서드 사용
            position = await self.get_position(self.symbol)
            if position:
                return {
                    'symbol': self.symbol,
                    'side': position['side'],
                    'size': float(position['size']),
                    'entry_price': float(position['entryPrice']),
                    'leverage': int(position['leverage']),
                    'unrealized_pnl': float(position['unrealizedPnl']),
                    'liquidation_price': float(position['liquidationPrice'])
                }
            return None
            
        except Exception as e:
            logger.error(f"포지션 조회 중 오류: {str(e)}")
            return None

    async def create_position(self, trading_signals: Dict) -> bool:
        """포지션 생성"""
        try:
            # OrderService를 통한 주문 생성
            return await self.order_service.create_position_order(trading_signals)
            
        except Exception as e:
            logger.error(f"포지션 생성 중 오류: {str(e)}")
            return False

    async def set_position_sl_tp(self, symbol: str, stop_loss: float = None, take_profit: float = None) -> bool:
        """포지션 손절/익절가 설정"""
        try:
            params = {
                'category': 'linear',
                'symbol': symbol,
                'stopLoss': str(stop_loss) if stop_loss else '',
                'takeProfit': str(take_profit) if take_profit else '',
                'positionIdx': 0  # 단일 포지션
            }
            
            response = await self.bybit_client.exchange.private_post_v5_position_trading_stop(params)
            logger.info(f"SL/TP 설정 응답: {response}")
            
            return response and response.get('retCode') == '0'
            
        except Exception as e:
            logger.error(f"SL/TP 설정 중 오류: {str(e)}")
            return False
