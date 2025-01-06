import logging
import traceback
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from functools import wraps
import time
from config.trading_config import trading_config

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
            
            # Raw 데이터 조회 및 로깅
            positions = await self.bybit_client.get_positions(symbol)
            logger.info(f"Raw 포지션 데이터: {positions}")
            
            # 포지션 데이터 파싱
            if positions:
                parsed = self._parse_positions(positions, symbol)
                logger.info(f"파싱된 포지션 데이터: {parsed}")
                return parsed
            
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
                    'leverage': int(float(pos.get('leverage', trading_config.DEFAULT_LEVERAGE))),
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
        try:
            symbol = signal.get('symbol', 'BTCUSDT')
            side = signal.get('side')
            target_leverage = int(signal.get('leverage'))
            
            # 퍼센트를 BTC 단위로 변환 (상세 로그 제거)
            balance = await self.bybit_client.get_balance()
            if not balance:
                logger.error("잔고 조회 실패")
                return False
            
            available_balance = float(balance.get('totalWalletBalance', 0))
            target_btc = (available_balance * float(signal.get('size', 0)) / 100 * target_leverage) / float(signal.get('entry_price'))
            target_btc = round(target_btc, trading_config.DECIMAL_PLACES)
            if target_btc < trading_config.MIN_POSITION_SIZE:
                logger.warning(f"계산된 수량({target_btc})이 최소 주문 수량({trading_config.MIN_POSITION_SIZE})보다 작아 조정")
                target_btc = trading_config.MIN_POSITION_SIZE
            
            # 현재 포지션 확인 (Raw 데이터 로그 제거)
            current_positions = await self.get_positions(symbol)
            
            if not current_positions:
                logger.info(f"신규 포지션 진입: {side} {target_btc} BTC x{target_leverage}")
                return await self._open_new_position(symbol, side, target_leverage, target_btc, float(signal.get('entry_price')))

            current_pos = current_positions[0]
            current_btc = abs(float(current_pos.get('size', 0)))
            current_side = current_pos.get('side', '').title()
            current_leverage = int(current_pos.get('leverage', 1))

            logger.info(f"포지션 조정 - 현재: {current_side} {current_btc} BTC x{current_leverage} -> 목표: {side} {target_btc} BTC x{target_leverage}")
            
            if current_side == side:
                if current_leverage == target_leverage:
                    return await self._adjust_position_size(symbol, side, current_btc, target_btc, float(signal.get('entry_price')), target_leverage)
                else:
                    return await self._change_leverage_position(symbol, side, current_btc, target_btc, float(signal.get('entry_price')), 
                                                             current_leverage, target_leverage)
            else:
                return await self._reverse_position(symbol, side, current_btc, target_btc, float(signal.get('entry_price')), target_leverage)

        except Exception as e:
            logger.error(f"포지션 처리 중 오류: {str(e)}")
            return False

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
        if side not in ['Buy', 'Sell']:
            return False, f"잘못된 포지션 방향: {side}"

        return True, ""

    def _calculate_sl_tp(self, side: str, price: float) -> Tuple[float, float]:
        """스탑로/테이크프로핏 계산"""
        try:
            price = float(price)
            
            if side == 'Buy':
                stop_loss = price * (1 - trading_config.LONG_SL_PERCENT/100)
                take_profit = price * (1 + trading_config.LONG_TP_PERCENT/100)
            else:
                stop_loss = price * (1 + trading_config.SHORT_SL_PERCENT/100)
                take_profit = price * (1 - trading_config.SHORT_TP_PERCENT/100)
                
            return stop_loss, take_profit
            
        except Exception as e:
            logger.error(f"SL/TP 계산 중 에러: {str(e)}")
            # 에러 시에도 설정값 사용
            if side == 'Buy':
                return (price * (1 - trading_config.LONG_SL_PERCENT/100),
                       price * (1 + trading_config.LONG_TP_PERCENT/100))
            else:
                return (price * (1 + trading_config.SHORT_SL_PERCENT/100),
                       price * (1 - trading_config.SHORT_TP_PERCENT/100))

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
                position_size=size,
                leverage=leverage,
                entry_price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                order_type='limit'
            )
            return order is not None
        except Exception as e:
            logger.error(f"신규 포지션 진입 중 오류: {str(e)}")
            return False

    async def _adjust_position_size(self, symbol: str, side: str, current_btc: float, target_btc: float, price: float, leverage: int) -> bool:
        """포지션 크기 조정 (BTC 단위)"""
        try:
            btc_diff = target_btc - current_btc
            
            if abs(btc_diff) == 0:
                logger.info("포지션 크기가 정확히 일치하여 조정하지 않음")
                return {'success': True, 'order_created': False}
            
            if abs(btc_diff) < trading_config.MIN_POSITION_SIZE:
                logger.info(f"차이가 최소 주문 단위({trading_config.MIN_POSITION_SIZE})보다 작아 조정하지 않음")
                return {'success': True, 'order_created': False}

            if btc_diff > 0:  # 증가
                # TP/SL 계산 - 원래 방향 그대로
                stop_loss, take_profit = self._calculate_sl_tp(side, price)
                order = await self.order_service.create_order(
                    symbol=symbol,
                    side=side,
                    position_size=btc_diff,
                    entry_price=price,
                    order_type='limit',
                    leverage=leverage,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    is_btc_unit=True
                )
            else:  # 감소
                close_side = 'Sell' if side == 'Buy' else 'Buy'
                # 청산 주문에는 TP/SL 설정 제외
                order = await self.order_service.create_order(
                    symbol=symbol,
                    side=close_side,
                    position_size=abs(btc_diff),
                    entry_price=price,
                    order_type='limit',
                    leverage=leverage,
                    reduce_only=True,
                    is_btc_unit=True
                )
            return order is not None
            
        except Exception as e:
            logger.error(f"포지션 크기 조정 중 오류: {str(e)}")
            return False

    async def _change_leverage_position(self, symbol: str, side: str, current_btc: float,
                                      target_btc: float, price: float, current_leverage: int,
                                      target_leverage: int) -> bool:
        """레버리지 변경을 위한 포지션 재설정"""
        logger.info(f"레버리지 변경 (현재: {current_leverage}x -> 목표: {target_leverage}x)")
        
        # 1. 현재 포지션 종료
        close_side = 'buy' if side == 'SHORT' else 'sell'
        if not await self.order_service.close_position(symbol, close_side, current_btc):
            return False

        # 2. 새로운 레버리지로 재진입
        return await self._open_new_position(symbol, side, target_leverage, target_btc, price)

    async def _reverse_position(self, symbol: str, new_side: str, current_btc: float,
                              target_btc: float, price: float, target_leverage: int) -> bool:
        """반대 방향 포지션으로 전환"""
        logger.info(f"반대 방향 포지션 전환 (현재: {current_btc} -> 방향: {new_side}, 크기: {target_btc})")
        
        # 1. 현재 포지션 전체 청산
        close_side = 'Buy' if new_side == 'Sell' else 'Sell'
        if not await self.order_service.close_position(symbol, close_side, current_btc, price):
            return False

        # 2. 반대 방향으로 새로 진입
        return await self._open_new_position(symbol, new_side, target_leverage, target_btc, price)

    @error_handler
    async def get_balance(self) -> Dict:
        """잔고 조회"""
        balance = await self.bybit_client.get_balance()
        if balance:
            logger.debug(f"Raw balance data: {balance}")
            result = {
                'timestamp': int(time.time() * trading_config.TIMESTAMP_MULTIPLIER),
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
