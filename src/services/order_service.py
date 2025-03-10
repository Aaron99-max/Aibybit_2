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

    def _validate_side(self, side: str) -> str:
        """주문 방향 검증"""
        if side not in ['Buy', 'Sell']:
            raise ValueError(f"잘못된 주문 방향: {side}")
        return side

    async def place_order(self, signal: Dict) -> bool:
        """주문 실행"""
        try:
            logger.info(f"주문 시도: {signal}")
            
            # 1. 현재 포지션 확인
            current_position = await self.position_service.get_position(signal['symbol'])
            logger.info(f"현재 포지션: {current_position}")
            
            # 2. 포지션 없는 경우 신규 진입 (size가 0이거나 current_position이 None인 경우)
            if not current_position or float(current_position.get('size', 0)) == 0:
                logger.info("포지션 없음 - 신규 진입 시도")
                return await self.create_new_position(signal)
                
            # 3. 포지션 있는 경우 관리
            return await self.manage_existing_position(current_position, signal)
            
        except Exception as e:
            logger.error(f"주문 실행 중 오류: {str(e)}")
            logger.error(f"상세 에러: {traceback.format_exc()}")
            logger.error(f"주문 파라미터: {signal}")
            return False

    async def create_new_position(self, signal: Dict) -> bool:
        """신규 포지션 생성"""
        try:
            logger.info(f"신규 포지션 생성 시도: {signal}")
            
            # 레버리지 설정
            if not await self.set_leverage(signal['leverage']):
                logger.error("레버리지 설정 실패")
                return False

            # 잔고 조회로 실제 BTC 수량 계산
            balance = await self.balance_service.get_balance()
            if not balance:
                logger.error("잔고 조회 실패")
                return False
                
            total_equity = float(balance.get('currencies', {}).get('USDT', {}).get('total_equity', 0))
            if total_equity <= 0:
                logger.error(f"총 자산이 부족합니다: ${total_equity}")
                return False
            
            # 포지션 크기 계산 (BTC)
            btc_quantity = await self._calculate_position_size(
                total_equity=total_equity,
                percentage=signal['position_size'],
                leverage=signal['leverage'],
                entry_price=float(signal['entry_price'])
            )
            
            logger.info(f"계산된 BTC 수량: {btc_quantity} (총자산: ${total_equity}, 목표비율: {signal['position_size']}%, 레버리지: {signal['leverage']}x)")
            
            # 주문 파라미터 설정
            order_params = {
                "category": "linear",
                "symbol": signal['symbol'],
                "side": signal['side'],
                "qty": str(btc_quantity),
                "price": str(signal['entry_price']),
                "orderType": "Limit",
                "timeInForce": "GTC",
                "positionIdx": 0,
                "stopLoss": str(signal['stop_loss']) if signal.get('stop_loss') else None,
                "takeProfit": str(signal['take_profit']) if signal.get('take_profit') else None
            }
            
            # 주문 실행
            response = await self.bybit_client.v5_create_order(order_params)
            
            if response and response.get('retCode') == 0:
                logger.info(f"신규 포지션 생성 성공: {order_params}")
                logger.info("주문 결과:")
                logger.info(json.dumps(response, indent=2))
                return True
            else:
                logger.error(f"신규 포지션 생성 실패: {response}")
                logger.error("주문 결과:")
                logger.error(json.dumps(response, indent=2))
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
            
            # 방향이 다른 경우 -> 시장가 청산 후 신규 진입
            if current_side != signal['side']:
                logger.info("포지션 방향이 다름 - 시장가 청산 후 신규 진입")
                if not await self.create_market_order(
                    symbol=current_position['symbol'],
                    side='Sell' if current_position['side'] == 'Buy' else 'Buy',
                    position_size=current_position['size'],
                    reduce_only=True
                ):
                    return False
                return await self.create_new_position(signal)
            
            # 레버리지 차이 확인
            leverage_diff = abs(current_leverage - target_leverage)
            max_leverage_diff = trading_config.leverage_settings['max_difference']
            
            # 레버리지 차이가 설정값 이상인 경우 -> 시장가 청산 후 신규 진입
            if leverage_diff >= max_leverage_diff:
                logger.info(f"레버리지 차이가 큼({leverage_diff}) - 시장가 청산 후 신규 진입")
                if not await self.create_market_order(
                    symbol=current_position['symbol'],
                    side='Sell' if current_position['side'] == 'Buy' else 'Buy',
                    position_size=current_position['size'],
                    reduce_only=True
                ):
                    return False
                return await self.create_new_position(signal)
            
            # 레버리지 차이가 설정값 미만인 경우 -> 크기만 조정 (지정가)
            logger.info(f"레버리지 차이가 작음({leverage_diff}) - 크기만 조정")
            return await self._adjust_position_size(current_position, signal)

        except Exception as e:
            logger.error(f"포지션 관리 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def create_order(self, **params) -> Dict:
        """주문 생성"""
        try:
            # 방향 검증
            params['side'] = self._validate_side(params['side'])
            
            # 수량 계산
            if not params.get('is_btc_unit', False):
                balance = await self.balance_service.get_balance()
                if not balance:
                    logger.error("잔고 조회 실패")
                    return None
                    
                # 현재 포지션 확인
                current_position = await self.position_service.get_position(params['symbol'])
                current_size = float(current_position.get('size', 0)) if current_position else 0
                
                # 가용 잔고 확인
                available_balance = float(balance.get('totalWalletBalance', 0))
                target_value = available_balance * (params['position_size'] / 100) * params['leverage']
                target_quantity = target_value / float(params['entry_price'])
                target_quantity = round(target_quantity, 3)
                
                # 포지션 크기 차이 계산
                if current_size > 0:
                    quantity = abs(target_quantity - current_size)
                else:
                    quantity = target_quantity
                
                # 최소 주문 수량 체크 (0.001 BTC)
                if quantity < 0.001:
                    quantity = 0.001
            else:
                quantity = float(params['position_size'])

            # 주문 파라미터 설정
            order_params = {
                "category": "linear",
                "symbol": params['symbol'],
                "side": params['side'],
                "orderType": "Limit",
                "qty": str(quantity),
                "price": str(params['entry_price']),
                "timeInForce": "GTC",
                "positionIdx": 0,
                "reduceOnly": params.get('reduceOnly', False)
            }

            # TP/SL 설정
            if params.get('stop_loss'):
                order_params['stopLoss'] = str(params['stop_loss'])
            if params.get('take_profit'):
                order_params['takeProfit'] = str(params['take_profit'])

            logger.info(f"주문 실행 시도: {order_params}")
            
            # 주문 실행
            result = await self.bybit_client.v5_post("/order/create", order_params)
            
            # 상세 응답 로깅
            logger.info("=== 주문 요청 및 응답 상세 ===")
            logger.info(f"요청 파라미터:\n{json.dumps(order_params, indent=2)}")
            logger.info(f"API 응답:\n{json.dumps(result, indent=2)}")

            return result

        except Exception as e:
            logger.error(f"주문 생성 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    async def set_leverage(self, leverage: int) -> bool:
        """레버리지 설정"""
        try:
            logger.info(f"레버리지 설정 시도: {leverage}x")
            
            # 레버리지 설정 (바이비트 API 호출)
            response = await self.bybit_client.v5_post("/position/set-leverage", {
                "category": "linear",
                "symbol": self.symbol,
                "buyLeverage": str(leverage),
                "sellLeverage": str(leverage)
            })
            
            # retCode가 0(성공) 또는 110043(이미 설정됨)인 경우 성공으로 처리
            if response and (response.get('retCode') == 0 or response.get('retCode') == 110043):
                logger.info(f"레버리지 설정 확인: {leverage}x")
                return True
            else:
                logger.error(f"레버리지 설정 실패: {response}")
                return False
            
        except Exception as e:
            logger.error(f"레버리지 설정 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def _calculate_position_size(self, total_equity: float, percentage: float, 
                                leverage: int, entry_price: float) -> float:
        """
        포지션 크기 계산 (BTC)
        Args:
            total_equity: 총 자산 (USDT)
            percentage: 포지션 크기 (%)
            leverage: 레버리지
            entry_price: 진입가격
        Returns:
            float: BTC 수량
        """
        try:
            # 미실현 손익을 제외한 순수 자산으로 계산
            unrealized_pnl = await self.get_unrealized_pnl()
            logger.info(f"계산 입력값 - 총자산: ${total_equity}, 미실현손익: ${unrealized_pnl}, " 
                        f"비율: {percentage}%, 레버리지: {leverage}배, 진입가: ${entry_price}")
            
            # 순수 자산 계산
            net_equity = total_equity - unrealized_pnl
            logger.info(f"순수 자산: ${net_equity}")
            
            # USDT 값 계산
            position_value = net_equity * (percentage / 100) * leverage
            logger.info(f"포지션 가치(USDT): ${position_value}")
            
            # BTC 수량 계산
            btc_size = position_value / entry_price
            logger.info(f"계산된 BTC 수량: {btc_size}")
            
            # 최종 반올림
            final_size = round(btc_size, 3)
            logger.info(f"최종 BTC 수량(반올림): {final_size}")
            
            if final_size <= 0:
                logger.error("계산된 포지션 크기가 0 이하입니다!")
                raise ValueError("Invalid position size calculated")
            
            return final_size
            
        except Exception as e:
            logger.error(f"포지션 크기 계산 중 오류 발생: {str(e)}")
            logger.error(traceback.format_exc())
            raise  # 에러를 상위로 전파

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

    async def _adjust_position_size(self, current_position: Dict, signal: Dict) -> bool:
        """포지션 크기 조정 (지정가)"""
        try:
            current_size = self.safe_float(current_position.get('size', 0))
            logger.info(f"현재 포지션 크기: {current_size} BTC")
            
            balance = await self.balance_service.get_balance()
            if not balance:
                logger.error("잔고 조회 실패")
                return False
                
            available_balance = float(balance['currencies']['USDT']['available_balance'])
            total_equity = float(balance['currencies']['USDT']['total_equity'])
            unrealized_pnl = await self.get_unrealized_pnl()
            logger.info(f"가용 잔고: ${available_balance}, 총 자산: ${total_equity}, 미실현 손익: ${unrealized_pnl}")
            
            # 목표 BTC 수량 계산
            try:
                target_size = await self._calculate_position_size(
                    total_equity=total_equity,
                    percentage=signal['position_size'],
                    leverage=signal['leverage'],
                    entry_price=float(signal['entry_price'])
                )
            except Exception as e:
                logger.error(f"목표 포지션 크기 계산 실패: {str(e)}")
                return False
            
            logger.info(f"목표 포지션 크기: {target_size} BTC")
            
            # 크기 차이 계산 (원래 값 로깅)
            size_diff = target_size - current_size
            logger.info(f"계산된 크기 차이(원본): {size_diff} BTC")
            
            # 소수점 3자리로 반올림하고 부호 유지
            size_diff = round(abs(size_diff), 3) * (1 if size_diff > 0 else -1)
            logger.info(f"조정된 크기 차이(반올림): {size_diff} BTC")
            
            # 최소 주문 수량 체크 (0.001 BTC)
            if abs(size_diff) < trading_config.MIN_POSITION_SIZE:
                logger.info(f"크기 차이가 최소 주문 단위보다 작음: {abs(size_diff)} BTC")
                return True

            # 크기 조정 주문 (지정가)
            side = 'Buy' if size_diff > 0 else 'Sell'
            is_reduce_only = size_diff < 0  # 포지션 감소 여부
            
            order_params = {
                "category": "linear",
                "symbol": signal['symbol'],
                "side": side,
                "orderType": "Limit",
                "qty": str(abs(size_diff)),
                "price": str(signal['entry_price']),
                "timeInForce": "GTC",
                "positionIdx": 0,
                "reduceOnly": is_reduce_only,
                "stopLoss": None if is_reduce_only else str(signal['stop_loss']),
                "takeProfit": None if is_reduce_only else str(signal['take_profit'])
            }
            
            # 주문 전 로깅
            logger.info(f"주문 시도: {order_params}")
            
            response = await self.bybit_client.v5_create_order(order_params)
            if response and response.get('retCode') == 0:
                logger.info(f"포지션 크기 조정 성공: {order_params}")
                return True
            else:
                logger.error(f"포지션 크기 조정 실패: {response}")
                return False

        except Exception as e:
            logger.error(f"포지션 크기 조정 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False

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
            logger.info(f"매매 신호 실행: {signals}")

            # 주문 파라미터 설정
            order_params = {
                'symbol': self.symbol,  # 기본 심볼 사용
                'side': 'Buy' if signals['position_suggestion'] == 'BUY' else 'Sell',
                'leverage': signals['leverage'],
                'position_size': signals['position_size'],
                'entry_price': signals['entry_price'],
                'stop_loss': signals['stop_loss'],
                'take_profit': signals['take_profit1'],  # take_profit1을 take_profit으로 사용
                'is_btc_unit': False
            }
            
            logger.info(f"주문 시도: {order_params}")
            logger.info(f"주문 상세 정보: {json.dumps(order_params, indent=2)}")
            return await self.place_order(order_params)
            
        except Exception as e:
            logger.error(f"매매 신호 실행 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False
