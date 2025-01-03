import logging
import traceback
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
import json
from exchange.bybit_client import BybitClient
import asyncio
from config import config
from telegram_bot.formatters.order_formatter import OrderFormatter

logger = logging.getLogger('order_service')

class OrderService:
    def __init__(self, bybit_client, telegram_bot=None):
        self.bybit_client = bybit_client
        self.telegram_bot = telegram_bot
        self.symbol = 'BTCUSDT'
        self.order_formatter = OrderFormatter()
        
    async def place_order(self, order_params):
        # 주문 전 포지션 체크는 TradeManager에서 수행하도록 이동
        try:
            response = await self.bybit_client.place_order(order_params)
            return response
        except Exception as e:
            logger.error(f"주문 실패: {str(e)}")
            return None

    def _validate_side(self, side: str) -> str:
        """주문 방향 검증 및 변환"""
        side = str(side).upper()
        if side not in ['BUY', 'SELL']:
            raise ValueError(f"잘못된 주문 방향: {side}. 'Buy' 또는 'Sell'이어야 합니다.")
        return side

    async def create_order(self, **params) -> Dict:
        """주문 생성"""
        try:
            # 방향 검증
            params['side'] = self._validate_side(params['side'])
            
            # 필수 파라미터 체크
            required_params = ['symbol', 'side', 'position_size', 'leverage', 'entry_price']
            for param in required_params:
                if param not in params:
                    logger.error(f"필수 파라미터 누락: {param}")
                    return None

            # 선택적 파라미터 기본값 설정
            params.setdefault('stop_loss', None)
            params.setdefault('take_profit', None)
            params.setdefault('reduceOnly', False)
            params.setdefault('is_btc_unit', False)

            # 레버리지 설정 (한 번만)
            try:
                await self.set_leverage(params['leverage'])
            except Exception as e:
                logger.warning(f"레버리지 설정 중 오류 (무시됨): {str(e)}")

            # 수량 계산
            if params['is_btc_unit']:
                quantity = float(params['position_size'])
            else:
                balance = await self.bybit_client.get_balance()
                if not balance:
                    logger.error("잔고 조회 실패")
                    return None
                
                available_balance = float(balance.get('totalWalletBalance', 0))
                position_value = available_balance * (params['position_size'] / 100) * params['leverage']
                quantity = position_value / float(params['entry_price'])
            
            # 소수점 3자리로 반올림 (바이비트 규칙)
            quantity = round(quantity, 3)
            
            # 최소 수량 체크
            if quantity < 0.001:
                logger.error(f"주문 수량이 최소 수량(0.001 BTC)보다 작음: {quantity} BTC")
                return None

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
                "reduceOnly": params['reduceOnly']
            }

            # 주문 실행 전 로깅
            logger.info(f"주문 실행 시도: {order_params}")
            
            # 주절/익절 설정이 있는 경우에만 추가
            if params['stop_loss'] is not None:
                order_params["stopLoss"] = str(params['stop_loss'])
            if params['take_profit'] is not None:
                order_params["takeProfit"] = str(params['take_profit'])

            # 주문 실행
            result = await self.bybit_client.v5_post("/order/create", order_params)
            
            # 상세 응답 로깅
            logger.info("=== 주문 요청 �� 응답 상세 ===")
            logger.info(f"요청 파라미터:\n{json.dumps(order_params, indent=2)}")
            logger.info(f"API 응답:\n{json.dumps(result, indent=2)}")

            if not result:
                logger.error("주문 생성 실패: 응답 없음")
                return None

            # retCode 확인
            ret_code = result.get('retCode')
            ret_msg = result.get('retMsg')
            if ret_code != 0:
                logger.error(f"주문 생성 실패: [{ret_code}] {ret_msg}")
                return None

            # 주문 상세 정보 확인
            order_info = result.get('result', {})
            if not order_info:
                logger.error("주문 정보 없음")
                return None

            if result:
                # 상세 로깅
                logger.info("=== 주문 생성 성공 ===")
                logger.info(f"주문 ID: {order_info.get('orderId')}")
                logger.info(f"심볼: {params['symbol']}")
                logger.info(f"방향: {params['side']}")
                logger.info(f"수량: {quantity}")
                logger.info(f"가격: {params['entry_price']}")
                logger.info(f"손절가: {params['stop_loss']}")
                logger.info(f"익절가: {params['take_profit']}")

                # OrderFormatter를 사용하여 텔레그램 알림 메시지 생성
                if self.telegram_bot:
                    order_data = {
                        'type': 'LIMIT',
                        'side': params['side'].upper(),
                        'symbol': params['symbol'],
                        'price': params['entry_price'],
                        'amount': quantity,
                        'status': 'NEW',
                        'leverage': params['leverage'],
                        'stop_loss': params['stop_loss'],
                        'take_profit': params['take_profit'],
                        'order_id': order_info.get('orderId'),
                        'position_size': params['position_size']
                    }
                    message = self.order_formatter.format_order(order_data)
                    await self.telegram_bot.send_message_to_all(message)

            return result

        except Exception as e:
            logger.error(f"주문 생성 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    async def set_leverage(self, leverage: int) -> bool:
        """레버리지 설정"""
        try:
            # 레버리지 설정 (바이비트 API 호출)
            response = await self.bybit_client.v5_post("/position/set-leverage", {
                "category": "linear",
                "symbol": self.symbol,
                "buyLeverage": str(leverage),
                "sellLeverage": str(leverage)
            })
            
            if response and response.get('retCode') == 0:
                logger.info(f"레버리지 설정 완료: {leverage}x")
                return True
            else:
                logger.error(f"레버리지 설정 실패: {response}")
                return False
            
        except Exception as e:
            logger.error(f"레버리지 설정 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False
