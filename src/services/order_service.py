import logging
import traceback
import math
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
import json
from exchange.bybit_client import BybitClient
import asyncio
from config.trading_config import trading_config
from telegram_bot.formatters.order_formatter import OrderFormatter
from services.position_service import PositionService
from services.balance_service import BalanceService

logger = logging.getLogger('order_service')

class OrderService:
    def __init__(self, bybit_client: BybitClient, position_service: PositionService, 
                 balance_service: BalanceService, telegram_bot=None):
        self.bybit_client = bybit_client
        self.position_service = position_service
        self.balance_service = balance_service
        self.telegram_bot = telegram_bot
        self.order_formatter = OrderFormatter()
        self.symbol = 'BTCUSDT'
        
        # 메시지 타입 상수 정의
        self.MSG_TYPE_ORDER = 'order'
        self.MSG_TYPE_INFO = 'info'
        self.MSG_TYPE_ERROR = 'error'

    def _validate_side(self, side: str) -> str:
        """주문 방향 검증"""
        if side not in ['Buy', 'Sell']:
            raise ValueError(f"잘못된 주문 방향: {side}")
        return side

    async def place_order(self, signal: Dict) -> bool:
        """주문 실행"""
        try:
            logger.info(f"주문 시도: {signal}")
            
            # 1. 미체결 주문 확인 및 처리
            open_orders = await self.bybit_client.exchange.fetch_open_orders(
                symbol=signal['symbol'],
                params={'category': 'linear'}
            )
            
            if open_orders:
                logger.info(f"미체결 주문 {len(open_orders)}개 발견 - 취소 처리")
                # 모든 미체결 주문 취소
                await self.bybit_client.exchange.cancel_all_orders(
                    symbol=signal['symbol'],
                    params={'category': 'linear'}
                )
                await asyncio.sleep(1)  # 주문 취소 처리 대기
            
            # 2. 현재 포지션 확인
            current_position = await self.position_service.get_position(signal['symbol'])
            
            # 3. 포지션 없는 경우 신규 진입 (size가 0이거나 current_position이 None인 경우)
            if not current_position or float(current_position.get('size', 0)) == 0:
                logger.info("포지션 없음 - 신규 진입 시도")
                return await self.create_new_position(signal, skip_notification=False)
                
            # 4. 포지션 있는 경우 관리
            return await self.manage_existing_position(current_position, signal)
            
        except Exception as e:
            logger.error(f"주문 실행 중 오류: {str(e)}")
            logger.error(f"상세 에러: {traceback.format_exc()}")
            logger.error(f"주문 파라미터: {signal}")
            return False

    async def create_new_position(self, order_info: Dict, skip_notification: bool = False) -> bool:
        """신규 포지션 생성"""
        try:
            logger.info(f"신규 포지션 생성 시도: {order_info}")
            
            # CCXT 형식에 맞게 side 변환
            side = order_info.get('side', '')
            side = 'Buy' if side.upper() == 'BUY' else 'Sell'
            
            # 나머지 주문 정보
            symbol = order_info.get('symbol', self.symbol)
            leverage = order_info.get('leverage', 1)
            position_size = order_info.get('position_size', 0)
            entry_price = order_info.get('entry_price', 0)
            stop_loss = order_info.get('stop_loss', 0)
            take_profit = order_info.get('take_profit', 0)
            is_btc_unit = order_info.get('is_btc_unit', False)
            
            # 레버리지 설정
            logger.info(f"레버리지 설정 시도: {leverage}x")
            await self.set_leverage(leverage)
            logger.info(f"레버리지 설정 확인: {leverage}x")
            
            # 잔고 조회
            balance = await self.get_balance()
            if not balance:
                logger.error("잔고 조회 실패")
                return False
                
            logger.info(f"USDT 잔고 - 총자산: ${balance['total_equity']:,.2f}, 가용잔고: ${balance['available_balance']:,.2f}, 사용중: ${balance['used_margin']:,.2f}")
            
            # 수량 계산
            btc_qty = await self._calculate_position_size(
                total_equity=balance['total_equity'],
                unrealized_pnl=balance['unrealized_pnl'],
                position_ratio=position_size / 100,  # percentage to decimal
                leverage=leverage,
                entry_price=entry_price,
                is_btc_unit=is_btc_unit
            )
            
            # CCXT 주문 파라미터 설정
            order_params = {
                'symbol': symbol,
                'side': side,
                'type': 'limit',
                'amount': btc_qty,
                'price': entry_price,
                'params': {
                    'category': 'linear',
                    'timeInForce': 'GTC',
                    'positionIdx': 0,
                    'stopLoss': str(stop_loss),
                    'takeProfit': str(take_profit)  # take_profit으로 통일
                }
            }
            
            # CCXT를 통한 주문 실행
            logger.info(f"신규 포지션 생성 시도: {order_params}")
            order_result = await self.bybit_client.exchange.create_order(**order_params)
            
            if order_result:
                logger.info(f"신규 포지션 생성 성공: {order_params}")
                logger.info("주문 결과:")
                logger.info(json.dumps(order_result, indent=2))
                
                # 텔레그램 알림 전송 (skip_notification이 False일 때만)
                if self.telegram_bot and not skip_notification:
                    formatted_message = self.order_formatter.format_order({
                        'type': 'new_position',
                        'symbol': symbol,
                        'side': side,
                        'qty': btc_qty,
                        'price': entry_price,
                        'leverage': leverage,
                        'stop_loss': stop_loss,
                        'take_profit': take_profit  # take_profit으로 통일
                    })
                    await self.telegram_bot.send_message_to_all(formatted_message, self.MSG_TYPE_ORDER)
                
                return True
            else:
                logger.error(f"신규 포지션 생성 실패")
                return False
            
        except Exception as e:
            logger.error(f"신규 포지션 생성 중 오류: {str(e)}")
            logger.error(f"상세 에러: {traceback.format_exc()}")
            return False

    async def manage_existing_position(self, current_position: Dict, signal: Dict) -> bool:
        """기존 포지션 관리"""
        try:
            current_side = current_position['side']
            current_leverage = int(current_position['leverage'])
            target_leverage = int(signal['leverage'])
            
            # 포지션 방향이 같은 경우 (Short-Sell 또는 Long-Buy)
            is_same_direction = (current_side == 'Short' and signal['side'] == 'Sell') or \
                              (current_side == 'Long' and signal['side'] == 'Buy')
            
            if not is_same_direction:
                logger.info("포지션 방향이 다름 - 시장가 청산 후 신규 진입")
                if not await self.create_market_order(
                    symbol=current_position['symbol'].split(':')[0],
                    side='Buy' if current_position['side'] == 'Short' else 'Sell',
                    size=abs(current_position['size']),
                    reduce_only=True
                ):
                    return False
                    
                # 청산 알림 전송
                if self.telegram_bot:
                    close_message = self.order_formatter.format_order({
                        'type': 'close_position',
                        'symbol': current_position['symbol'],
                        'side': 'Buy' if current_position['side'] == 'Short' else 'Sell',
                        'qty': abs(current_position['size']),
                        'price': current_position['entry_price'],
                        'status': 'FILLED',
                        'reason': '포지션 방향 변경'
                    })
                    await self.telegram_bot.send_message_to_all(close_message, self.MSG_TYPE_ORDER)
                
                # 신규 진입 시 알림 스킵 (청산 알림만 보냄)
                return await self.create_new_position(signal, skip_notification=True)
            
            # 레버리지 차이 확인
            leverage_diff = abs(current_leverage - target_leverage)
            max_leverage_diff = trading_config.leverage_settings['max_difference']
            
            # 레버리지 차이가 설정값 이상인 경우 -> 시장가 청산 후 신규 진입
            if leverage_diff >= max_leverage_diff:
                logger.info(f"레버리지 차이가 큼({leverage_diff}) - 시장가 청산 후 신규 진입")
                if not await self.create_market_order(
                    symbol=current_position['symbol'].split(':')[0],
                    side='Buy' if current_position['side'] == 'Short' else 'Sell',
                    size=abs(current_position['size']),
                    reduce_only=True
                ):
                    return False
                    
                # 청산 알림 전송
                if self.telegram_bot:
                    close_message = self.order_formatter.format_order({
                        'type': 'close_position',
                        'symbol': current_position['symbol'],
                        'side': 'Buy' if current_position['side'] == 'Short' else 'Sell',
                        'qty': abs(current_position['size']),
                        'price': current_position['entry_price'],
                        'status': 'FILLED',
                        'reason': f'레버리지 차이 ({current_leverage}x → {target_leverage}x)'
                    })
                    await self.telegram_bot.send_message_to_all(close_message, self.MSG_TYPE_ORDER)
                
                # 신규 진입 시 알림 스킵 (청산 알림만 보냄)
                return await self.create_new_position(signal, skip_notification=True)
            
            # 레버리지 차이가 설정값 미만인 경우 -> 크기만 조정
            logger.info(f"레버리지 차이가 작음({leverage_diff}) - 크기만 조정")
            
            # 계좌 잔고 조회
            balance = await self.balance_service.get_balance()
            if not balance:
                return False
                
            usdt_balance = balance['currencies']['USDT']
            logger.info(f"가용 잔고: ${usdt_balance['available_balance']}, 총 자산: ${usdt_balance['total_equity']}, 사용중: ${usdt_balance['used_margin']}")
            
            # 목표 포지션 크기 계산
            target_size = await self._calculate_position_size(
                total_equity=float(usdt_balance['total_equity']),
                percentage=signal['position_size'],
                leverage=signal['leverage'],
                entry_price=signal['entry_price']
            )
            
            # 크기 차이 계산
            current_size = abs(float(current_position['size']))
            size_diff = target_size - current_size
            
            if abs(size_diff) < 0.001:  # 최소 변경 크기
                logger.info("포지션 크기 차이가 미미함 - 조정 불필요")
                return True
            
            # 크기 조정 주문
            order_side = signal['side']
            if size_diff < 0:  # 크기 감소
                order_side = 'Sell' if current_side == 'Long' else 'Buy'
                size_diff = abs(size_diff)
            
            # 조정 주문 실행
            if not await self.create_market_order(
                symbol=current_position['symbol'].split(':')[0],
                side=order_side,
                size=size_diff,
                reduce_only=(size_diff < 0)
            ):
                return False
            
            # 크기 조정 알림 전송
            if self.telegram_bot:
                adjust_message = self.order_formatter.format_order({
                    'type': 'adjust_position',
                    'symbol': current_position['symbol'],
                    'side': order_side,
                    'qty': size_diff,
                    'price': signal['entry_price'],
                    'status': 'FILLED',
                    'current_size': current_size,
                    'target_size': target_size,
                    'reason': '포지션 크기 조정'
                })
                await self.telegram_bot.send_message_to_all(adjust_message, self.MSG_TYPE_ORDER)
            
            return True
            
        except Exception as e:
            logger.error(f"기존 포지션 관리 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def create_order(self, symbol: str, side: str, position_size: float, entry_price: float,
                          stop_loss: float, take_profit: float, leverage: int = None, is_btc_unit: bool = False) -> bool:
        """주문 생성"""
        try:
            # 현재 포지션 조회
            current_position = await self.position_service.get_position()
            is_reduce_only = False
            needs_sl_tp = True
            
            # 반대 방향 주문인지 확인 (청산 주문)
            if current_position and current_position.get('size', 0) > 0:
                current_side = current_position['side']  # Long or Short
                current_size = float(current_position['size'])
                
                if (current_side == 'Long' and side == 'Sell') or \
                   (current_side == 'Short' and side == 'Buy'):
                    # 주문 크기가 현재 포지션보다 작거나 같으면 순수 청산
                    if position_size <= current_size:
                        is_reduce_only = True
                        needs_sl_tp = False  # 순수 청산은 TP/SL 불필요
                    else:
                        # 주문 크기가 더 크면 청산 후 반대 포지션
                        # 이 경우 TP/SL 설정 필요
                        needs_sl_tp = True
            
            # 주문 상세 정보 로깅 (한 번만)
            logger.info(f"매매 신호 실행: {json.dumps({'symbol': symbol, 'side': side, 'leverage': leverage, 'position_size': position_size, 'entry_price': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'is_btc_unit': is_btc_unit, 'is_reduce_only': is_reduce_only, 'needs_sl_tp': needs_sl_tp}, indent=2)}")
            
            # 잔고 조회
            balance = await self.balance_service.get_balance()
            if not balance:
                return False
                
            usdt_balance = balance['currencies']['USDT']
            logger.info(f"USDT 잔고 - 총자산: ${usdt_balance['total_equity']}, 가용잔고: ${usdt_balance['available_balance']}, 사용중: ${usdt_balance['used_margin']}")
            
            # 수량 계산
            if is_btc_unit:
                qty = position_size  # BTC 단위로 직접 지정된 경우
            else:
                # USDT 단위로 지정된 경우, BTC 수량으로 변환
                qty = position_size  # 이미 BTC 단위로 변환된 수량
            
            # 주문 파라미터 설정
            order_params = {
                'symbol': symbol,
                'side': side,
                'orderType': 'Limit',
                'qty': f"{qty:.3f}",  # 소수점 3자리까지
                'price': str(entry_price),
                'timeInForce': 'GTC',
                'positionIdx': 0,
                'reduceOnly': is_reduce_only
            }
            
            # TP/SL이 필요한 경우에만 설정
            if needs_sl_tp:
                if stop_loss:
                    order_params['stopLoss'] = str(stop_loss)
                if take_profit:
                    order_params['takeProfit'] = str(take_profit)
                
            logger.info(f"주문 실행 시도: {order_params}")
            
            # 주문 실행
            response = await self.bybit_client.v5_post("/order/create", order_params)
            
            # 응답 로깅
            logger.info("=== 주문 요청 및 응답 상세 ===")
            logger.info(f"요청 파라미터:\n{json.dumps(order_params, indent=2)}")
            logger.info(f"API 응답:\n{json.dumps(response, indent=2)}")
            
            return response and response.get('retCode') == 0
            
        except Exception as e:
            logger.error(f"주문 생성 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def create_market_order(self, symbol: str, side: str, size: float, reduce_only: bool = False) -> bool:
        """시장가 주문 생성"""
        try:
            # CCXT 형식에 맞게 side 변환
            side = 'Buy' if side.upper() == 'BUY' else 'Sell'
            
            params = {
                'category': 'linear',
                'reduceOnly': reduce_only
            }
            
            # 주문 파라미터 설정
            order_params = {
                'symbol': symbol,
                'side': side,
                'type': 'market',
                'amount': size,
                'params': params
            }
            
            # CCXT를 통한 주문 실행
            order = await self.bybit_client.exchange.create_order(**order_params)
            
            if order:
                logger.info(f"시장가 주문 성공: {order}")
                return True
            else:
                logger.error(f"시장가 주문 실패")
                return False
                
        except Exception as e:
            logger.error(f"시장가 주문 생성 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def set_leverage(self, leverage: int) -> None:
        """레버리지 설정"""
        try:
            await self.bybit_client.exchange.set_leverage(
                leverage=leverage,
                symbol=self.symbol,
                params={'category': 'linear'}
            )
        except Exception as e:
            if "leverage not modified" in str(e):
                logger.info(f"레버리지가 이미 {leverage}x로 설정되어 있습니다")
            else:
                raise e

    async def _calculate_position_size(self, total_equity: float, unrealized_pnl: float, 
                                position_ratio: float, leverage: int, entry_price: float, is_btc_unit: bool = False) -> float:
        """
        포지션 크기 계산 (BTC)
        Args:
            total_equity: 총 자산 (USDT)
            unrealized_pnl: 미실현 손익 (USDT)
            position_ratio: 포지션 크기 (0.0 ~ 1.0)
            leverage: 레버리지
            entry_price: 진입가격
            is_btc_unit: BTC 단위로 직접 지정 여부
        Returns:
            float: BTC 수량
        """
        try:
            # BTC 단위로 직접 지정된 경우
            if is_btc_unit:
                btc_size = position_ratio  # position_ratio가 직접 BTC 수량
                logger.info(f"직접 지정된 BTC 수량: {btc_size}")
            else:
                # 순수 자산 계산
                net_equity = total_equity - unrealized_pnl
                logger.info(f"순수 자산: ${net_equity:,.2f}")
                
                # USDT 값 계산 (레버리지 적용)
                position_value = net_equity * position_ratio * leverage
                logger.info(f"포지션 가치(USDT): ${position_value:,.2f}")
                
                # BTC 수량 계산
                btc_size = position_value / entry_price
                logger.info(f"계산된 BTC 수량: {btc_size:.3f}")
            
            # 최소 주문 수량 확인 (0.001 BTC)
            if btc_size < 0.001:
                logger.warning("계산된 수량이 최소 주문 수량보다 작습니다. 최소 수량으로 설정합니다.")
                btc_size = 0.001
            
            # 최대 주문 수량 확인 (10 BTC)
            if btc_size > 10:
                logger.warning("계산된 수량이 최대 주문 수량을 초과합니다. 최대 수량으로 제한합니다.")
                btc_size = 10
            
            # 최종 반올림 (소수점 3자리)
            final_size = round(btc_size, 3)
            logger.info(f"최종 BTC 수량(반올림): {final_size:.3f}")
            
            if final_size <= 0:
                logger.error("계산된 포지션 크기가 0 이하입니다!")
                raise ValueError("Invalid position size calculated")
            
            return final_size
            
        except Exception as e:
            logger.error(f"포지션 크기 계산 중 오류 발생: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    async def get_unrealized_pnl(self) -> float:
        """현재 포지션의 미실현 손익 조회"""
        try:
            positions = await self.bybit_client.get_positions(self.symbol)
            if positions and len(positions) > 0 and positions[0].get('size', '0') != '0':
                # 포지션 정보에서 직접 계산
                size = float(positions[0].get('size', '0'))
                avg_price = float(positions[0].get('avgPrice', '0'))
                mark_price = float(positions[0].get('markPrice', '0'))
                side = positions[0].get('side', '')
                
                if side == 'Buy':
                    pnl = size * (mark_price - avg_price)
                elif side == 'Sell':
                    pnl = size * (avg_price - mark_price)
                else:
                    pnl = 0
                
                logger.info(f"계산된 미실현 손익: ${pnl} (size: {size}, avgPrice: {avg_price}, markPrice: {mark_price}, side: {side})")
                return pnl
            return 0.0
        except Exception as e:
            logger.error(f"미실현 손익 조회 중 오류: {str(e)}")
            return 0.0

    async def _close_position_market(self, position: Dict) -> bool:
        """포지션 시장가 청산"""
        try:
            close_side = 'Sell' if position['side'] == 'Buy' else 'Buy'
            
            order_params = {
                "category": "linear",
                "symbol": position['symbol'],
                "side": close_side,
                "orderType": "Market",
                "qty": str(position['size']),
                "reduceOnly": True,
                "timeInForce": "GTC",
                "positionIdx": 0
            }
            
            response = await self.bybit_client.v5_create_order(order_params)
            if response and response.get('retCode') == 0:
                logger.info("포지션 청산 성공")
                return True
            else:
                logger.error(f"포지션 청산 실패: {response}")
                return False
                
        except Exception as e:
            logger.error(f"포지션 청산 중 오류: {str(e)}")
            return False

    def safe_float(self, value):
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    async def execute_trade(self, signals: Dict) -> bool:
        """매매 신호 실행"""
        try:
            # 주문 파라미터 설정
            order_params = {
                'symbol': signals.get('symbol', self.symbol),  # signals에서 심볼을 가져오거나 기본값 사용
                'side': signals.get('side', 'Buy' if signals['position_suggestion'] == 'BUY' else 'Sell'),
                'leverage': signals['leverage'],
                'position_size': signals['position_size'],
                'entry_price': signals['entry_price'],
                'stop_loss': signals['stop_loss'],
                'take_profit': signals['take_profit1'],  # take_profit1을 take_profit으로 사용
                'is_btc_unit': signals.get('is_btc_unit', False)
            }
            
            # 주문 상세 정보 로깅 (한 번만)
            logger.info(f"매매 신호 실행: {json.dumps(order_params, indent=2)}")
            
            # 주문 실행
            return await self.place_order(order_params)
            
        except Exception as e:
            logger.error(f"매매 신호 실행 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def get_balance(self) -> Optional[Dict]:
        """잔고 조회"""
        try:
            balance = await self.balance_service.get_balance()
            if not balance:
                return None
                
            usdt_balance = balance['currencies']['USDT']
            
            # 포지션 미실현 손익 조회
            positions = await self.position_service.get_position(self.symbol)
            unrealized_pnl = float(positions.get('unrealizedPnl', 0)) if positions else 0
            
            return {
                'total_equity': usdt_balance['total_equity'],
                'used_margin': usdt_balance['used_margin'],
                'available_balance': usdt_balance['available_balance'],
                'unrealized_pnl': unrealized_pnl
            }
            
        except Exception as e:
            logger.error(f"잔고 조회 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    async def process_trading_signal(self, signal: Dict) -> bool:
        """매매 신호 처리"""
        try:
            if not signal:
                logger.error("매매 신호가 없습니다")
                return False

            logger.info(f"매매 신호 실행: {signal}")
            
            # 주문 정보 구성
            order_info = {
                'symbol': signal.get('symbol', 'BTCUSDT'),
                'side': signal.get('position_suggestion'),
                'leverage': signal.get('leverage', 5),
                'position_size': signal.get('position_size', 10),
                'entry_price': signal.get('entry_price'),
                'stop_loss': signal.get('stop_loss'),
                'take_profit': signal.get('take_profit1'),
                'is_btc_unit': False
            }
            
            logger.info(f"주문 시도: {order_info}")
            logger.info(f"주문 상세 정보: {json.dumps(order_info, indent=2)}")
            
            # 미체결 주문 취소
            await self.cancel_all_orders()
            
            # 현재 포지션 조회
            current_position = await self.get_position()
            logger.info(f"현재 포지션: {current_position}")
            
            # 포지션이 없으면 신규 진입
            if not current_position:
                logger.info("포지션 없음 - 신규 진입 시도")
                return await self.create_new_position(order_info, skip_notification=False)
            
            # 포지션이 있으면 관리
            logger.info("기존 포지션 관리 시도")
            return await self.manage_existing_position(current_position, order_info)
            
        except Exception as e:
            logger.error(f"주문 파라미터: {signal}")
            return False
