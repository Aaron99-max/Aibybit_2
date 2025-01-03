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
        """API 요청 실행"""
        try:
            if not self.api_key or not self.api_secret:
                logger.error("API 키가 설정되지 않았습니다")
                return None
                
            timestamp = str(int(time.time() * 1000))
            recv_window = "5000"
            params = params or {}
            
            # V5 API 서명 생성
            if method == "GET":
                # GET 요청의 경우 쿼리 문자열 생성
                query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
                sign_payload = timestamp + self.api_key + recv_window + query_string
            else:
                # POST 요청의 경우 JSON 문자열 사용
                sign_payload = timestamp + self.api_key + recv_window + json.dumps(params)
            
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
                'X-BAPI-TIMESTAMP': timestamp,
                'X-BAPI-RECV-WINDOW': recv_window
            }
            
            if method == "POST":
                headers['Content-Type'] = 'application/json'
            
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(url, params=params, headers=headers) as response:
                        return await response.json()
                else:  # POST
                    async with session.post(url, json=params, headers=headers) as response:
                        return await response.json()

        except Exception as e:
            logger.error(f"API 요청 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    async def v5_post(self, path: str, params: Dict = None) -> Dict:
        """V5 API POST 요청"""
        return await self._request("POST", f"/v5{path}", params)

    async def v5_get(self, path: str, params: Dict = None) -> Dict:
        """V5 API GET 요청"""
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

    async def get_closed_trades(self, symbol: str = 'BTCUSDT') -> List[Dict]:
        """완료된 거래 내역 조회"""
        try:
            params = {
                'category': 'linear',
                'symbol': symbol,
                'limit': 50
            }
            
            # V5 API 엔드포인트 사용
            response = await self.exchange.private_get_v5_position_closed_pnl(params)
            
            if response and response.get('result', {}).get('list'):
                trades = response['result']['list']
                return [{
                    'symbol': trade['symbol'],
                    'side': trade['side'],
                    'size': float(trade['qty']),
                    'entry_price': float(trade['avgEntryPrice']),
                    'exit_price': float(trade['avgExitPrice']),
                    'realized_pnl': float(trade['closedPnl']),
                    'timestamp': int(trade['updatedTime'])
                } for trade in trades]
            
            return []
            
        except Exception as e:
            logger.error(f"거래 내역 조회 실패: {str(e)}")
            logger.error(traceback.format_exc())  # 상세 에러 로그 추가
            return []