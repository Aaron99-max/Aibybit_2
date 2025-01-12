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
        """주문 방향 검증"""
        if side not in ['Buy', 'Sell']:
            raise ValueError(f"잘못된 주문 방향: {side}")
        return side

    async def create_order(self, **params) -> Dict:
        """주문 생성"""
        try:
            # 방향 검증
            params['side'] = self._validate_side(params['side'])
            
            # takeProfit이 리스트인 경우 첫 번째 값만 사용
            if isinstance(params.get('takeProfit'), list) and params['takeProfit']:
                params['takeProfit'] = params['takeProfit'][0]

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
            if 0 < quantity < 0.001:
                # 최소 수량 달 알림
                order_data = {
                    'symbol': params['symbol'],
                    'side': params['side'],
                    'leverage': params['leverage'],
                    'amount': quantity,
                    'skip_reason': 'min_size',
                    'confidence': params.get('confidence', 0),
                    'timeframe': params.get('timeframe', '4h')
                }
                
                if self.telegram_bot:
                    message = self.order_formatter.format_order(order_data)
                    await self.telegram_bot.send_message_to_all(message)
                    
                return True  # 정상 처리로 간주
            
            elif quantity <= 0:
                logger.error("주문 수량이 0보다 작거나 같음")
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
                "reduceOnly": params.get('reduceOnly', False),
                "tpslMode": "Full",
                "stopLoss": str(params['stopLoss']) if params.get('stopLoss') else None,
                "takeProfit": str(params['takeProfit']) if params.get('takeProfit') else None
            }

            logger.info(f"주문 실행 시도: {order_params}")
            
            # 주문 실행
            result = await self.bybit_client.v5_post("/order/create", order_params)
            
            # 상세 응답 로깅
            logger.info("=== 주문 요청 및 응답 상세 ===")
            logger.info(f"요청 파라미터:\n{json.dumps(order_params, indent=2)}")
            logger.info(f"API 응답:\n{json.dumps(result, indent=2)}")

            if result and result.get('retCode') == 0:  # 성공
                # 주문 상세 정보 확인
                order_info = result.get('result', {})
                if not order_info:
                    logger.error("주문 정보 없음")
                    return None

                # 상세 로깅
                logger.info("=== 주문 생성 성공 ===")
                logger.info(f"주문 ID: {order_info.get('orderId')}")
                logger.info(f"심볼: {params['symbol']}")
                logger.info(f"방향: {params['side']}")
                logger.info(f"수량: {quantity}")
                logger.info(f"가격: {params['entry_price']}")
                logger.info(f"손절가: {params['stopLoss']}")
                logger.info(f"익절가: {params['takeProfit']}")

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
                        'stopLoss': params['stopLoss'],
                        'takeProfit': params['takeProfit'],
                        'order_id': order_info.get('orderId'),
                        'position_size': params['position_size']
                    }
                    message = self.order_formatter.format_order(order_data)
                    await self.telegram_bot.send_message_to_all(message)
            else:  # 실패
                error_msg = f"주문 생성 실패: [{result.get('retCode')}] {result.get('retMsg')}"
                logger.error(error_msg)
                
                # 실패 알림 추가
                if self.telegram_bot:
                    fail_message = self.order_formatter.format_order_failure(params, error_msg)
                    await self.telegram_bot.send_message_to_all(fail_message)
                return None

            return result

        except Exception as e:
            logger.error(f"주문 생성 중 오류: {str(e)}")
            if self.telegram_bot:
                await self.telegram_bot.send_message_to_all(f"❌ 주문 처리 중 오류 발생: {str(e)}")
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

    async def close_position(self, symbol: str, side: str, size: float, entry_price: float) -> bool:
        """포지션 청산"""
        try:
            # 주문 파라미터 설정
            order_params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,  # 그대로 Buy/Sell 사용
                "orderType": "Limit",
                "qty": str(size),
                "price": str(entry_price),  # 파라미터로 받은 진입가 사용
                "timeInForce": "GTC",
                "reduceOnly": True,
                "positionIdx": 0
            }
            
            logger.info(f"포지션 청산 시도: {order_params}")
            
            # 주문 실행
            result = await self.bybit_client.v5_post("/order/create", order_params)
            
            if result and result.get('retCode') == 0:
                logger.info(f"포지션 청산 성공: {size} {symbol}")
                return True
            else:
                logger.error(f"포지션 청산 실패패: {result}")
                return False
            
        except Exception as e:
            logger.error(f"포지션션 청산 중 오류: {str(e)}")
            return False

    async def create_market_order(self, symbol: str, side: str, position_size: float, 
                                reduce_only: bool = False, is_btc_unit: bool = True) -> Dict:
        """시장가 주문 생성"""
        try:
            order_params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": "Market",
                "qty": str(position_size),
                "timeInForce": "IOC",
                "reduceOnly": reduce_only,
                "positionIdx": 0
            }
            
            logger.info(f"시장가 주문 시도: {order_params}")
            
            result = await self.bybit_client.v5_post("/order/create", order_params)
            
            if result and result.get('retCode') == 0:
                order_info = result.get('result', {})
                logger.info(f"시장가 주문 성공: {position_size} {symbol}")
                return {
                    'orderId': order_info.get('orderId'),
                    'status': order_info.get('orderStatus', 'unknown'),
                    'info': order_info
                }
            else:
                logger.error(f"시장가 주문 실패: {result}")
                return None
            
        except Exception as e:
            logger.error(f"시장가 주문 생성 중 오류: {str(e)}")
            return None

    async def cancel_all_tpsl(self, symbol: str) -> bool:
        """모든 TP/SL 주문 취소"""
        try:
            # TP/SL 취소 파라미터
            params = {
                "category": "linear",
                "symbol": symbol,
                "positionIdx": 0
            }
            
            # TP/SL 취소 API 호출
            result = await self.bybit_client.v5_post("/position/trading-stop", params)
            
            if result and result.get('retCode') == 0:
                logger.info(f"TP/SL 취소 성공: {symbol}")
                return True
            else:
                logger.error(f"TP/SL 취소 실패: {result}")
                return False
            
        except Exception as e:
            logger.error(f"TP/SL 취소 중 오류: {str(e)}")
            return False

    async def get_order(self, order_id: str) -> Dict:
        """주문 상태 회"""
        try:
            params = {
                "category": "linear",
                "symbol": self.symbol,
                "orderId": order_id
            }
            result = await self.bybit_client.v5_get("/order/history", params)
            
            # 디버그 로깅 추가
            logger.info(f"주문 회 응답: {result}")
            
            if result and result.get('retCode') == 0:
                orders = result.get('result', {}).get('list', [])
                if orders:
                    order = orders[0]
                    # 주문 상태 매핑
                    status_map = {
                        'Created': 'new',
                        'New': 'new',
                        'Filled': 'filled',
                        'Cancelled': 'canceled',
                        'Rejected': 'rejected'
                    }
                    return {
                        'orderId': order.get('orderId'),
                        'status': status_map.get(order.get('orderStatus'), 'unknown'),
                        'filled': float(order.get('cumExecQty', 0)),
                        'remaining': float(order.get('leavesQty', 0))
                    }
            return None
        except Exception as e:
            logger.error(f"주문 회 중 오류: {str(e)}")
            return None

    async def handle_order_result(self, result: Dict):
        """주문 결과 처리"""
        try:
            # OrderFormatter를 통해 메시지 포맷팅
            message = self.order_formatter.format_order(result)
            
            # 텔레그램으로 메시지 전송 (send_message_to_all 사용)
            await self.telegram_bot.send_message_to_all(message)  # send_message 대신 send_message_to_all 사용
            
        except Exception as e:
            logger.error(f"주문 결과 처리 중 오류: {str(e)}")
