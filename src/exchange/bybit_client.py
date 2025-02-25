import ccxt.async_support as ccxt
import logging
import hmac
import hashlib
import time
import aiohttp
import json
from typing import Dict
from config.bybit_config import BybitConfig
import traceback

logger = logging.getLogger(__name__)

class BybitClient:
    def __init__(self, config: BybitConfig = None):
        """
        Args:
            config: Bybit 설정
        """
        self.config = config or BybitConfig()
        self.time_offset = 0
        self.last_time_sync = 0
        self.SYNC_INTERVAL = 3600  # 1시간마다 동기화
        
        # CCXT exchange 객체 초기화 (market_data_service에서 필요)
        self.exchange = ccxt.bybit({
            'apiKey': self.config.api_key,
            'secret': self.config.api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'linear',
                'defaultMarket': 'linear',
                'accountType': 'UNIFIED',
                'recvWindow': 20000,
                'adjustForTimeDifference': True
            }
        })
        
        # 테스트넷 설정
        if self.config.testnet:
            self.exchange.set_sandbox_mode(True)

    async def _should_sync_time(self):
        """시간 동기화가 필요한지 확인"""
        current_time = int(time.time())
        return (current_time - self.last_time_sync) > self.SYNC_INTERVAL

    async def _init_time_offset(self):
        """서버 시간과 로컬 시간 동기화"""
        try:
            server_time = await self.exchange.fetch_time()
            local_time = int(time.time() * 1000)
            self.time_offset = server_time - local_time
            self.last_time_sync = int(time.time())
            logger.info(f"서버 시간 동기화 완료: offset = {self.time_offset}ms")
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
            
            timestamp = str(int(time.time() * 1000) + self.time_offset)
            request_params = params.copy() if params else {}
            
            # GET 요청 처리
            if method == "GET":
                # 1. 파라미터에 타임스탬프 추가
                request_params['timestamp'] = timestamp
                
                # 2. 정렬된 파라미터로 쿼리 스트링 생성
                sorted_params = sorted(request_params.items())
                query_string = '&'.join([f"{k}={v}" for k, v in sorted_params])
                
                # 디버그 로그
                logger.debug(f"Query string for signature: {query_string}")
                
                # 3. 서명 생성
                signature = hmac.new(
                    bytes(self.config.api_secret, 'utf-8'),
                    bytes(query_string, 'utf-8'),
                    hashlib.sha256
                ).hexdigest()

            url = f"{self.config.base_url}{path}"
            headers = {
                'X-BAPI-API-KEY': self.config.api_key,
                'X-BAPI-SIGN': signature,
                'X-BAPI-TIMESTAMP': timestamp,
                'X-BAPI-RECV-WINDOW': "5000",
                'Content-Type': 'application/json'
            }
            
            # 디버그 로그
            logger.debug(f"Request URL: {url}")
            logger.debug(f"Request params: {request_params}")
            logger.debug(f"Request headers: {headers}")
            
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(url, params=request_params, headers=headers) as response:
                        result = await response.json()
                        logger.debug(f"Response: {result}")  # 응답 로그 추가
                        return result
                else:  # POST
                    async with session.post(url, json=request_params, headers=headers) as response:
                        return await response.json()

        except Exception as e:
            logger.error(f"API 요청 실패: {str(e)}")
            logger.error(traceback.format_exc())  # 스택 트레이스 추가
            return None

    async def v5_post(self, path: str, params: Dict = None) -> Dict:
        """V5 API POST 요청"""
        try:
            return await self._request('POST', f"/v5{path}", params)
        except Exception as e:
            logger.error(f"API 요청 실패 (POST {path}): {str(e)}")
            return None

    async def v5_get(self, path: str, params: Dict = None) -> Dict:
        """V5 API GET 요청"""
        try:
            return await self._request('GET', f"/v5{path}", params)
        except Exception as e:
            logger.error(f"API 요청 실패 (GET {path}): {str(e)}")
            return None

    async def v5_get_closed_pnl(self, params: Dict) -> Dict:
        """V5 API closed-pnl 조회"""
        try:
            # 디버그 로그 추가
            logger.debug(f"closed-pnl API 요청: {params}")
            response = await self.v5_get("/position/closed-pnl", params)
            logger.debug(f"closed-pnl API 응답: {response}")
            return response
        except Exception as e:
            logger.error(f"API 호출 실패: {str(e)}")
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
            result = await self.v5_post("/order/create", params)
            
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
        """잔고 조회 API 호출"""
        try:
            # V5 API로 시도
            response = await self.v5_get("/account/wallet-balance", {
                "accountType": "UNIFIED"
            })
            return response
            
        except Exception as e:
            logger.error(f"잔고 조회 API 호출 실패: {str(e)}")
            return {}
