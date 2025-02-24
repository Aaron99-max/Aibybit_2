import logging
import traceback
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from functools import wraps
import time
from config.trading_config import trading_config
import asyncio

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
    def __init__(self, bybit_client):
        self.bybit_client = bybit_client
        self.symbol = trading_config.symbol

    async def get_position(self, symbol: str = None) -> Dict:
        """포지션 조회"""
        try:
            symbol = symbol or self.symbol
            positions = await self.bybit_client.get_positions(symbol)
            
            if not positions:
                return {}
                
            position = positions[0]  # 첫 번째 포지션 사용
            return position
            
        except Exception as e:
            logger.error(f"포지션 조회 중 오류: {str(e)}")
            return {}

    async def get_positions(self, symbol: str) -> List[Dict]:
        """포지션 목록 조회"""
        try:
            positions = await self.bybit_client.get_positions(symbol)
            return self._parse_positions(positions, symbol)
        except Exception as e:
            logger.error(f"포지션 조회 중 오류: {str(e)}")
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
    async def handle_position_for_signal(self, signal: Dict) -> bool:
        """거래 신호에 따른 포지션 처리"""
        try:
            logger.info(f"받은 신호 데이터: {signal}")
            
            # 신호 데이터 검증
            is_valid, error_msg = self._validate_signal(signal)
            if not is_valid:
                logger.error(f"신호 데이터 검증 실패: {error_msg}")
                return False

            symbol = signal.get('symbol', 'BTCUSDT')
            side = signal.get('side')
            target_leverage = int(signal.get('leverage', 1))
            target_percent = float(signal.get('size', 0))  # size는 퍼센트 단위
            entry_price = float(signal.get('entry_price', 0))
            stopLoss = float(signal.get('stopLoss', 0))
            takeProfit = float(signal.get('takeProfit', 0)) if not isinstance(signal.get('takeProfit'), list) else float(signal['takeProfit'][0])

            # 현재 포지션 확인
            current_positions = await self.get_positions(symbol)
            
            if not current_positions:
                # 신규 진입 (퍼센트 -> BTC 변환)
                balance = await self.balance_service.get_balance()
                if not balance:
                    logger.error("잔고 조회 실패")
                    return False
                    
                available_balance = float(balance.get('currencies', {}).get('USDT', {}).get('available_balance', 0))
                target_value = available_balance * (target_percent / 100) * target_leverage
                target_btc = target_value / entry_price
                
                logger.info(f"신규 진입 - {target_percent}% = {target_btc} BTC")
                
                return await self._open_new_position(
                    symbol=symbol,
                    side=side,
                    leverage=target_leverage,
                    size=target_btc,  # BTC 단위로 변환된 값
                    price=entry_price,
                    stopLoss=stopLoss,
                    takeProfit=takeProfit
                )

            current_pos = current_positions[0]
            current_btc = abs(float(current_pos.get('size', 0)))
            current_side = current_pos.get('side', '').title()
            current_leverage = int(current_pos.get('leverage', 1))

            logger.info(f"포지션 조정 - 현재: {current_side} {current_btc} BTC x{current_leverage} -> 목표: {side} {target_percent}% x{target_leverage}")
            
            if current_side == side:
                leverage_diff = abs(current_leverage - target_leverage)
                
                # 레버리지 차이가 허용 범위 내면
                if leverage_diff <= trading_config.leverage_settings['max_difference']:
                    logger.info(f"레버리지 차이({leverage_diff}) 허용 범위 내, 현재 레버리지({current_leverage}x) 유지")
                    
                    # 레버리지 체크 알림
                    order_data = {
                        'symbol': symbol,
                        'side': side,
                        'leverage': current_leverage,
                        'target_leverage': target_leverage,
                        'skip_reason': 'size_diff',
                        'leverage_check': True  # 레버리지 체크 플래그
                    }
                    
                    if self.order_service.telegram_bot:
                        message = self.order_service.order_formatter.format_order(order_data)
                        await self.order_service.telegram_bot.send_message_to_all(message)
                    
                    return await self._adjust_position_size(
                        symbol=symbol,
                        side=side,
                        current_btc=current_btc,
                        target_percent=target_percent,
                        price=entry_price,
                        leverage=current_leverage  # 현재 레버리지 유지
                    )
                else:
                    logger.info(f"TP/SL 설정값 - SL: {stopLoss}, TP: {takeProfit}")
                    return await self._change_leverage_position(
                        symbol=symbol,
                        side=side,
                        current_size=current_btc,
                        target_size=target_percent,
                        entry_price=entry_price,
                        current_leverage=current_leverage,
                        target_leverage=target_leverage,
                        stopLoss=stopLoss,
                        takeProfit=takeProfit
                    )
            else:
                return await self._reverse_position(symbol, side, current_btc, target_percent, entry_price, target_leverage)

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

    async def _open_new_position(self, symbol: str, side: str, leverage: int, size: float, 
                               price: float, stopLoss: float = None, takeProfit: float = None) -> bool:
        """신규 포지션 진입"""
        try:
            # takeProfit이 리스트인 경우 첫 번째 값만 사용
            if isinstance(takeProfit, list) and takeProfit:
                takeProfit = takeProfit[0]
            
            return await self.order_service.create_order(
                symbol=symbol,
                side=side,
                position_size=size,
                entry_price=price,
                leverage=leverage,
                stopLoss=stopLoss,
                takeProfit=takeProfit,
                is_btc_unit=True
            )
        except Exception as e:
            logger.error(f"신규 포지션 진입 중 오류: {str(e)}")
            return False

    async def _adjust_position_size(self, symbol: str, side: str, current_btc: float, target_percent: float, price: float, leverage: int) -> bool:
        """포지션 크기 조정"""
        try:
            # balance_service를 통한 잔고 조회
            balance = await self.balance_service.get_balance()
            if not balance:
                logger.error("잔고 조회 실패")
                return False
            
            # 로그 추가
            logger.info(f"잔고 정보: {balance}")
            
            # currencies['USDT']에서 available_balance 사용
            available_balance = float(balance.get('currencies', {}).get('USDT', {}).get('available_balance', 0))
            logger.info(f"사용 가능 잔고: {available_balance} USDT")
            
            # 목표 BTC 수량 계산
            target_value = available_balance * (target_percent / 100) * leverage
            target_btc = target_value / price
            
            logger.info(f"계산 과정:")
            logger.info(f"- 목표 가치: {target_value} USDT (잔고의 {target_percent}%)")
            logger.info(f"- 목표 BTC: {target_btc} BTC (가격: {price})")
            logger.info(f"- 현재 BTC: {current_btc} BTC")
            
            btc_diff = target_btc - current_btc
            logger.info(f"- 차이: {btc_diff} BTC")
            
            if abs(btc_diff) == 0:
                logger.info("포지션 크기가 정확히 일치")
                return await self.order_service.cancel_all_tpsl(symbol)
            
            if abs(btc_diff) < trading_config.MIN_POSITION_SIZE:
                # 수량 차이가 무 작을 때 알림
                order_data = {
                    'symbol': symbol,
                    'side': side,
                    'current_size': current_btc,
                    'target_size': target_btc,
                    'size_diff': btc_diff,
                    'skip_reason': 'size_diff',
                    'leverage_check': False  # 수량 체크 플래그
                }
                
                if self.order_service.telegram_bot:
                    message = self.order_service.order_formatter.format_order(order_data)
                    await self.order_service.telegram_bot.send_message_to_all(message)
                
                logger.info(f"수량 차이({abs(btc_diff)} BTC)가 최소 주문 단위보다 작음")
                return True

            if btc_diff > 0:  # 증가
                # TP/SL 계산 - 원래 방향 그대로
                stopLoss, takeProfit = self._calculate_sl_tp(side, price)
                order = await self.order_service.create_order(
                    symbol=symbol,
                    side=side,
                    position_size=btc_diff,
                    entry_price=price,
                    order_type='limit',
                    leverage=leverage,
                    stopLoss=stopLoss,
                    takeProfit=takeProfit,
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

    async def _wait_for_order_fill(self, order_id: str, timeout: int = 60) -> bool:
        """주문 체결 대기"""
        try:
            start_time = time.time()
            while time.time() - start_time < timeout:
                order = await self.order_service.get_order(order_id)
                if not order:
                    logger.error("주문 정보 조회 실패")
                    return False
                    
                status = order.get('status')
                if status == 'filled':
                    logger.info(f"주문 체결 완료: {order_id}")
                    return True
                elif status in ['canceled', 'rejected']:
                    logger.error(f"주문 실패 (상태: {status})")
                    return False
                    
                await asyncio.sleep(1)
                
            logger.error(f"주문 체결 타임아웃: {timeout}초 초과")
            return False
            
        except Exception as e:
            logger.error(f"주문 체결 대기 중 오류: {str(e)}")
            return False

    async def _change_leverage_position(self, symbol: str, side: str, current_size: float, 
                                    target_size: float, entry_price: float, 
                                    current_leverage: int, target_leverage: int,
                                    stopLoss: float = None,
                                    takeProfit: float = None) -> bool:
        """레버리지 변경을 위한 포지션 조정"""
        try:
            logger.info(f"레버리지 변경 시작 (현재: {current_leverage}x -> 목표: {target_leverage}x)")
            
            # 1. 기존 포지션 시장가 청산
            close_side = 'Sell' if side == 'Buy' else 'Buy'
            close_order = await self.order_service.create_market_order(
                symbol=symbol,
                side=close_side,
                position_size=current_size,
                reduce_only=True,
                is_btc_unit=True
            )
            
            if not close_order:
                logger.error("포지션 청산 실패")
                return False
            
            # 2. 청산 확인 (포지션 조회로 확인)
            await asyncio.sleep(1)  # 약간의 지연
            
            positions = await self.get_positions(symbol)
            if positions:  # 아직 포지션이 있다면
                logger.error("포지션 청산 실패 (포지션이 여전히 존재)")
                return False
            
            logger.info("포지션 청산 확인됨")
            
            # 3. 레버리지 변경
            if not await self.order_service.set_leverage(target_leverage):
                logger.error("레버리지 변경 실패")
                return False
            
            logger.info(f"레버리지 변경 완료: {target_leverage}x")
            
            # 4. 신규 포지션 진입
            balance = await self.balance_service.get_balance()
            if not balance:
                logger.error("잔고 조회 실패")
                return False
            
            available_balance = float(balance.get('currencies', {}).get('USDT', {}).get('available_balance', 0))
            target_value = available_balance * (target_size / 100) * target_leverage
            target_btc = target_value / entry_price
            
            logger.info(f"신규 진입 시도: {target_btc} BTC")
            
            return await self._open_new_position(
                symbol=symbol,
                side=side,
                leverage=target_leverage,
                size=target_btc,
                price=entry_price,
                stopLoss=stopLoss,
                takeProfit=takeProfit
            )
            
        except Exception as e:
            logger.error(f"레버리지 변경 중 오류: {str(e)}")
            return False

    async def _reverse_position(self, symbol: str, new_side: str, current_btc: float,
                              target_btc: float, price: float, target_leverage: int) -> bool:
        """반대 방향 포지션으로 전환"""
        logger.info(f"반대대 방향 포지션 전환 (현재: {current_btc} -> 방향: {new_side}, 크기: {target_btc})")
        
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
            
        logger.error("잔고고 정보를 찾을 수 없없습니다")
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

    def _calculate_sl_tp(self, side: str, entry_price: float) -> Tuple[float, float]:
        """손손절가/익절가 계산"""
        if side == 'Buy':
            stop_loss = entry_price * 0.98  # 2% 손절
            take_profit = entry_price * 1.02  # 2% 익절
        else:
            stop_loss = entry_price * 1.02
            take_profit = entry_price * 0.98
        return stop_loss, take_profit
