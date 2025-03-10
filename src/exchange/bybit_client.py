import ccxt.async_support as ccxt
import logging
import hmac
import hashlib
import time
import aiohttp
import json
from typing import Dict
import traceback
import ssl
import certifi

logger = logging.getLogger(__name__)

class BybitClient:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        if not api_key or not api_secret:
            logger.error("API 키가 설정되지 않았습니다")
            logger.error(f"api_key: {api_key}, api_secret: {api_secret}")
            raise ValueError("API key와 secret이 필요합니다")
            
        self.config = type('Config', (), {
            'api_key': api_key,
            'api_secret': api_secret,
            'testnet': testnet,
            'base_url': "https://api-testnet.bybit.com" if testnet else "https://api.bybit.com"
        })
        
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
            },
            'verify': True,
            'certifi': certifi.where(),
            'ssl': {
                'ca': certifi.where()
            }
        })
        
        # CCXT exchange 설정
        if testnet:
            self.exchange.set_sandbox_mode(True)

        self.last_time_sync = 0
        self.time_offset = 0
        self.ssl_context = ssl.create_default_context(cafile=certifi.where())
        self.SYNC_INTERVAL = 3600  # 1시간마다 동기화
        
    async def _should_sync_time(self):
        """시간 동기화가 필요한지 확인"""
        current_time = int(time.time())
        return (current_time - self.last_time_sync) > self.SYNC_INTERVAL

    async def _init_time_offset(self):
        """서버 시간과 로컬 시간 동기화"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.config.base_url}/v5/market/time", ssl=self.ssl_context) as response:
                    result = await response.json()
                    if result.get("retCode") == 0:
                        server_time = int(result["result"]["timeSecond"]) * 1000  # 초 단위를 밀리초로 변환
                        local_time = int(time.time() * 1000)
                        self.time_offset = server_time - local_time
                        self.last_time_sync = int(time.time())
                        logger.info(f"서버 시간 동기화 완료: server_time={server_time}, local_time={local_time}, offset={self.time_offset}ms")
                    else:
                        logger.error(f"서버 시간 조회 실패: {result}")
                        self.time_offset = 0
        except Exception as e:
            logger.error(f"서버 시간 동기화 실패: {str(e)}")
            self.time_offset = 0

    async def _ensure_time_sync(self):
        """API 요청 전 시간 동기화 확인"""
        if await self._should_sync_time():
            await self._init_time_offset()

    async def _request(self, method: str, path: str, params: Dict = None) -> Dict:
        """API 요청 공통 처리"""
        try:
            await self._ensure_time_sync()
            
            # 1. 요청 파라미터 준비 (None이면 빈 딕셔너리로)
            request_params = params.copy() if params else {}
            
            # 2. 타임스탬프 생성 (서버 시간 오프셋 적용)
            timestamp = str(int(time.time() * 1000) + self.time_offset)
            recv_window = '5000'
            
            # 3. 서명 생성
            if method == "GET":
                # GET 요청은 모든 파라미터를 쿼리 스트링으로
                sign_params = request_params.copy()
                sign_params['api_key'] = self.config.api_key
                sign_params['timestamp'] = timestamp
                sign_params['recv_window'] = recv_window
                
                # 정렬된 파라미터로 쿼리 스트링 생성
                sorted_params = sorted(sign_params.items())
                query_string = '&'.join([f"{k}={v}" for k, v in sorted_params])
                
                # 서명 페이로드 생성
                sign_payload = timestamp + self.config.api_key + recv_window + query_string
                
                # 디버그 로그
                logger.debug(f"Query string: {query_string}")
                logger.debug(f"Sign payload: {sign_payload}")
                
                # 요청 파라미터 업데이트
                request_params.update(sign_params)
            else:
                # POST 요청은 timestamp, api_key, recv_window를 먼저 서명
                sign_payload = timestamp + self.config.api_key + recv_window
                if request_params:
                    sign_payload += json.dumps(request_params)
            
            # 디버그 로그
            logger.debug(f"Sign payload: {sign_payload}")
            
            # 4. 서명 생성
            signature = hmac.new(
                self.config.api_secret.encode('utf-8'),
                sign_payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # 5. API 요청 준비
            url = f"{self.config.base_url}{path}"
            headers = {
                'X-BAPI-SIGN': signature,
                'X-BAPI-API-KEY': self.config.api_key,
                'X-BAPI-TIMESTAMP': timestamp,
                'X-BAPI-RECV-WINDOW': recv_window
            }
            
            if method == "POST":
                headers['Content-Type'] = 'application/json'
            
            # 디버그 로그
            logger.debug(f"Final request URL: {url}")
            logger.debug(f"Final request headers: {headers}")
            if method == "POST":
                logger.debug(f"Final request body: {request_params}")
            
            # 6. API 요청 실행
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    # GET 요청은 파라미터를 쿼리 스트링으로 전달
                    async with session.get(url, params=request_params, headers=headers, ssl=self.ssl_context) as response:
                        result = await response.json()
                        logger.debug(f"API Response: {result}")
                        return result
                else:  # POST
                    # POST 요청은 파라미터를 본문으로 전달
                    async with session.post(url, json=request_params, headers=headers, ssl=self.ssl_context) as response:
                        result = await response.json()
                        logger.debug(f"API Response: {result}")
                        return result

        except Exception as e:
            logger.error(f"API 요청 실패: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    async def v5_get_closed_pnl(self, params: Dict = None) -> Dict:
        """V5 API Closed PnL 조회"""
        return await self._request("GET", "/v5/position/closed-pnl", params)

    async def v5_get(self, path: str, params: Dict = None) -> Dict:
        """V5 API GET 요청"""
        try:
            return await self._request('GET', f"/v5{path}", params)
        except Exception as e:
            logger.error(f"API 요청 실패 (GET {path}): {str(e)}")
            return None

    async def v5_post(self, path: str, params: Dict = None) -> Dict:
        """V5 API POST 요청"""
        try:
            return await self._request('POST', f"/v5{path}", params)
        except Exception as e:
            logger.error(f"API 요청 실패 (POST {path}): {str(e)}")
            return None

    async def v5_get_positions(self, symbol: str = None) -> Dict:
        """포지션 조회"""
        try:
            params = {
                "category": "linear",
                "symbol": symbol
            }
            response = await self.v5_get("/position/list", params)
            if response and response.get('retCode') == 0:
                return response.get('result', {}).get('list', [])
            return []
        except Exception as e:
            logger.error(f"포지션 조회 중 오류: {str(e)}")
            return []

    async def v5_get_executions(self, params: Dict) -> Dict:
        """V5 API execution/list 조회"""
        try:
            return await self.v5_get("/execution/list", params)
        except Exception as e:
            logger.error(f"API 호출 실패: {str(e)}")
            return None

    async def close(self):
        """연결 종료"""
        if hasattr(self, 'exchange'):
            await self.exchange.close()

    async def get_funding_rate(self, symbol: str) -> float:
        """자금 조달 비율 조회"""
        try:
            params = {
                'category': 'linear',
                'symbol': symbol
            }
            response = await self.exchange.fetch_funding_rate(symbol, params=params)
            return float(response.get('fundingRate', 0))
        except Exception as e:
            logger.error(f"자금 조달 비율 조회 실패: {str(e)}")
            return 0.0

    async def v5_set_leverage(self, symbol: str, leverage: int, mode: str = 'isolated') -> Dict:
        """레버리지 및 마진 모드 설정"""
        try:
            logger.info(f"레버리지 설정 시도: {leverage}x")
            
            # V5 API 엔드포인트로 직접 요청
            path = "/v5/position/set-leverage"
            params = {
                "category": "linear",
                "symbol": symbol,
                "buyLeverage": str(leverage),
                "sellLeverage": str(leverage)
            }
            
            response = await self._request("POST", path, params)
            if response and response.get('retCode') in [0, 110043]:
                logger.info(f"레버리지 설정 성공: {leverage}x")
                return response
            else:
                logger.error(f"레버리지 설정 실패: {response}")
                return None
            
        except Exception as e:
            logger.error(f"레버리지 설정 중 오류: {str(e)}")
            return None

    async def v5_create_order(self, params: Dict) -> Dict:
        """V5 API 주문 생성 요청"""
        try:
            logger.info(f"주문 파라미터: {params}")
            result = await self._request("POST", "/v5/order/create", params)
            
            if result and result.get('retCode') == 0:
                logger.info(f"주문 API 응답: {result}")
                return result
            else:
                logger.error(f"주문 API 오류: {result}")
                return None

        except Exception as e:
            logger.error(f"주문 API 요청 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    async def get_balance(self) -> Dict:
        """잔고 조회"""
        try:
            # CCXT를 통해 잔고 조회
            balance = await self.exchange.fetch_balance({'type': 'unified'})
            logger.debug(f"CCXT Balance Response: {balance}")
            
            # CCXT 응답을 우리 형식으로 변환
            return {
                'retCode': 0,
                'result': {
                    'list': [{
                        'totalWalletBalance': balance.get('total', {}).get('USDT', 0),
                        'totalAvailableBalance': balance.get('free', {}).get('USDT', 0),
                        'totalInitialMargin': balance.get('used', {}).get('USDT', 0)
                    }]
                }
            }
        except Exception as e:
            logger.error(f"잔고 조회 실패: {str(e)}")
            return None
