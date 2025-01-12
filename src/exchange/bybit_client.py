import ccxt.async_support as ccxt
from typing import Dict, List
import logging
import traceback
import hmac
import hashlib
import time
import requests
import aiohttp
import json
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

class BybitClient:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        if not api_key or not api_secret:
            logger.error("API 키가 설정되지 않았습니다")
            logger.error(f"api_key: {api_key}, api_secret: {api_secret}")
            raise ValueError("API key와 secret이 필요합니다")
            
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # CCXT exchange 객체 초기화
        self.exchange = ccxt.bybit({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'linear',
                'defaultMarket': 'linear',
                'accountType': 'UNIFIED',
                'recvWindow': 20000,
                'adjustForTimeDifference': True
            }
        })
        
        # REST API base URL
        self.base_url = "https://api.bybit.com"
        
        # CCXT exchange 설정
        if testnet:
            self.exchange.set_sandbox_mode(True)

    async def initialize(self):
        """초기화 및 연결 테스트"""
        try:
            # 시장 데이터 로드
            await self.exchange.load_markets()
            logger.info("Bybit 클라이언트 초기화 완료")
            return True
        except Exception as e:
            logger.error(f"Bybit 클라이언트 초기화 실패: {str(e)}")
            return False

    async def _request(self, method: str, path: str, params: Dict = None) -> Dict:
        """API 요청 공통 처리"""
        try:
            timestamp = str(int(time.time() * 1000))
            request_params = params.copy() if params else {}
            request_params['timestamp'] = timestamp
            
            # recv_window 값을 params에서 가져오거나 기본값 사용
            recv_window = str(request_params.get('recv_window', 5000))
            
            if method == "GET":
                query_string = '&'.join([f"{k}={v}" for k, v in sorted(request_params.items())])
                sign_payload = timestamp + self.api_key + recv_window + query_string
            else:
                sign_payload = timestamp + self.api_key + recv_window + json.dumps(request_params)
            
            # 서명 생성
            signature = hmac.new(
                bytes(self.api_secret, 'utf-8'),
                bytes(sign_payload, 'utf-8'),
                hashlib.sha256
            ).hexdigest()

            url = f"{self.base_url}{path}"
            headers = {
                'X-BAPI-API-KEY': self.api_key,
                'X-BAPI-SIGN': signature,
                'X-BAPI-TIMESTAMP': str(timestamp),
                'X-BAPI-RECV-WINDOW': recv_window
            }
            
            if method == "POST":
                headers['Content-Type'] = 'application/json'
            
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(url, params=request_params, headers=headers) as response:
                        return await response.json()
                else:  # POST
                    async with session.post(url, json=request_params, headers=headers) as response:
                        return await response.json()

        except Exception as e:
            logger.error(f"API 요청 실패: {str(e)}")
            return None

    async def v5_post(self, path: str, data: Dict = None) -> Dict:
        """V5 API POST 요청"""
        try:
            # recv_window를 더 크게 설정 (5초 -> 10초)
            if data is None:
                data = {}
            data['recv_window'] = 10000  # 5000 -> 10000으로 증가
            
            response = await self._request('POST', f'/v5{path}', data)
            return response
            
        except Exception as e:
            logger.error(f"Bybit V5 POST 요청 실패: {str(e)}")
            return None

    async def v5_get(self, path: str, params: Dict = None) -> Dict:
        """V5 API GET 요청"""
        if params is None:
            params = {}
        params['recv_window'] = 10000  # 추가
        return await self._request("GET", f"/v5{path}", params)

    async def close(self):
        """연결 종료"""
        try:
            if hasattr(self, 'exchange'):
                await self.exchange.close()
            logger.info("Bybit 클라이언트 연결 종료")
        except Exception as e:
            logger.error(f"Bybit 클라이언트 종료 중 오류: {str(e)}")

    async def get_positions(self, symbol: str = None) -> list:
        """포지션 조회"""
        try:
            params = {
                'category': 'linear',
                'symbol': symbol
            }
            
            response = await self.exchange.private_get_v5_position_list(params)
            if not response or 'result' not in response:
                logger.info("포지션 정보 없음")
                return []
            
            positions = response['result'].get('list', [])
            if positions:
                logger.debug(f"포지션 데이터: {positions}")  # 상세 데이터는 debug 레벨로
            return positions
            
        except Exception as e:
            logger.error(f"포지션 조회 중 오류: {str(e)}")
            return []

    async def fetch_position_risk(self, symbol: str = None) -> dict:
        """포지션 리스크 정보 조회"""
        try:
            # V5 API의 position risk 엔드포인트 사용
            endpoint = '/v5/position/list'
            params = {
                'category': 'linear',
                'symbol': symbol
            }
            
            response = await self.exchange.private_get_v5_position_list(params)
            logger.info(f"Position risk response: {response}")
            return response
            
        except Exception as e:
            logger.error(f"포지션 리스크 조회 중 오류: {str(e)}")
            return {}

    async def get_balance(self) -> Dict:
        """잔고 조회"""
        try:
            # V5 API로 시도
            try:
                response = await self.v5_get("/account/wallet-balance", {
                    "accountType": "UNIFIED"  # CONTRACT -> UNIFIED로 변경
                })
                logger.debug(f"V5 Balance Response: {response}")
                
                if response and response.get('retCode') == 0:
                    # result.totalWalletBalance 값 반환
                    wallet_info = response.get('result', {}).get('list', [{}])[0]
                    return {
                        'totalWalletBalance': wallet_info.get('totalWalletBalance', '0'),
                        'totalAvailableBalance': wallet_info.get('totalAvailableBalance', '0')
                    }
                else:
                    logger.error(f"V5 API 잔고 조회 실패: {response}")
                    
            except Exception as e:
                logger.error(f"V5 API 잔고 조회 실패: {str(e)}")

            # CCXT 메서드로 재시도
            balance = await self.exchange.fetch_balance()
            logger.debug(f"CCXT Balance: {balance}")
            return balance
            
        except Exception as e:
            logger.error(f"잔고 조회 중 오류: {str(e)}")
            return {}

    def safe_float(self, value, default=0):
        """안전한 float 변환"""
        try:
            if value == '' or value is None:
                return default
            return float(value)
        except (ValueError, TypeError):
            return default

    async def set_leverage(self, symbol: str, leverage: int) -> Dict:
        """레버리지 설정"""
        try:
            # V5 API 엔드포인트로 수정
            path = "/v5/position/set-leverage"
            params = {
                "category": "linear",
                "symbol": symbol,
                "buyLeverage": str(leverage),
                "sellLeverage": str(leverage)
            }
            
            response = await self._request("POST", path, params)
            if response and response.get('retCode') == 0:
                logger.info(f"레버리지 설정 성공: {leverage}x")
                return response
            else:
                logger.error(f"레버리지 설정 실패: {response}")
                return None
                
        except Exception as e:
            logger.error(f"레버리지 설정 중 오류: {str(e)}")
            return None

    async def place_order(self, **params) -> Dict:
        """주문 실행"""
        try:
            path = "/v5/order/create"
            
            # side 값 검증 및 변환
            side = params.get('side', '').lower()
            if side not in ['buy', 'sell']:
                logger.error(f"잘못된 side 값: {side}")
                return None

            # 기본 파라미터 설정
            request_params = {
                "category": "linear",
                "symbol": params.get('symbol'),
                "side": "Buy" if side == 'buy' else "Sell",
                "orderType": "Limit",
                "timeInForce": "GoodTillCancel",
                "positionIdx": 0
            }

            # 일반 주문인 경우
            if 'position_size' in params and 'entry_price' in params:
                request_params.update({
                    "qty": str(params['position_size']),
                    "price": str(params['entry_price']),
                    "reduceOnly": False
                })
            # 조건부 주문(손절/익절)인 경우
            elif 'stop_price' in params or 'take_profit' in params:
                price = str(params.get('stop_price') or params.get('take_profit'))
                request_params.update({
                    "qty": str(params['position_size']),
                    "price": price,
                    "triggerPrice": price,
                    "triggerBy": "LastPrice",
                    "reduceOnly": True
                })
            else:
                logger.error("필수 파라미터 누락")
                return None
            
            # 파라미터 로깅
            logger.debug(f"주문 요청 파라미터: {request_params}")
            
            response = await self._request("POST", path, request_params)
            if response and response.get('retCode') == 0:
                logger.info(f"주문 실행 성공: {request_params}")
                return response
            else:
                logger.error(f"주문 실행 실패: {response}")
                return None
                
        except Exception as e:
            logger.error(f"주문 실행 중 오류: {str(e)}")
            return None

    async def get_order(self, order_id: str) -> Dict:
        """주문 조회"""
        try:
            params = {
                "category": "linear",
                "symbol": self.symbol,
                "orderId": order_id
            }
            
            response = await self.exchange.private_get_v5_order_history(params)
            return response
            
        except Exception as e:
            logger.error(f"주문 조회 실패: {str(e)}")
            return None

    async def get_closed_trades(self, symbol: str, limit: int = 1000, days: int = 90) -> List[Dict]:
        """
        완료된 거래 내역 조회 (7일씩 나눠서 조회)
        Args:
            symbol: 거래 심볼
            limit: 조회할 거래 수 (최대 1000)
            days: 조회할 기간 (일, 기본 90일)
        """
        try:
            current_time = int(time.time() * 1000)
            all_trades = []
            
            # days일 동안의 데이터를 7일씩 나눠서 조회
            for i in range(0, days, 7):
                end_time = current_time - (i * 24 * 60 * 60 * 1000)
                start_time = end_time - (7 * 24 * 60 * 60 * 1000)
                
                params = {
                    'category': 'linear',
                    'symbol': symbol,
                    'limit': limit,
                    'startTime': start_time,
                    'endTime': end_time
                }
                
                period_start = datetime.fromtimestamp(start_time/1000)
                period_end = datetime.fromtimestamp(end_time/1000)
                logger.info(f"거래 내역 조회 ({i+1}~{min(i+7, days)}일 전)")
                logger.debug(f"조회 기간: {period_start} ~ {period_end}")
                logger.debug(f"파라미터: {params}")
                
                try:
                    # 거래 내역 조회
                    trades = await self.exchange.fetch_my_trades(symbol=symbol, params=params)
                    if trades:
                        logger.info(f"조회된 거래 수: {len(trades)}건")
                        all_trades.extend(trades)
                    await asyncio.sleep(0.5)  # API 레이트 리밋 방지
                    
                except Exception as e:
                    logger.error(f"{period_start} ~ {period_end} 기간 거래 내역 조회 실패: {str(e)}")
                    continue
            
            if not all_trades:
                logger.info("전체 기간에 대한 거래 내역이 없습니다")
                return []
            
            # 거래 데이터 포맷팅
            formatted_trades = []
            for trade in all_trades:
                try:
                    formatted_trade = {
                        'id': trade['id'],
                        'timestamp': trade['timestamp'],
                        'symbol': trade['symbol'],
                        'side': trade['side'],
                        'price': float(trade['price']),
                        'amount': float(trade['amount']),
                        'cost': float(trade['cost']),
                        'fee': trade['fee'],
                        'realized_pnl': float(trade.get('info', {}).get('closed_pnl', 0))
                    }
                    formatted_trades.append(formatted_trade)
                except Exception as e:
                    logger.error(f"거래 데이터 포맷팅 실패: {str(e)}, trade: {trade}")
                    continue
            
            # 시간순 정렬 및 중복 제거
            formatted_trades.sort(key=lambda x: x['timestamp'], reverse=True)
            unique_trades = list({trade['id']: trade for trade in formatted_trades}.values())
            
            logger.info(f"최종 포맷팅된 거래 내역: {len(unique_trades)}건")
            return unique_trades
            
        except Exception as e:
            logger.error(f"거래 내역 조회 실패: {str(e)}")
            logger.error(traceback.format_exc())
            return []