import ccxt.async_support as ccxt
import logging
import hmac
import hashlib
import time
import aiohttp
import json
from typing import Dict, List
from config.bybit_config import BybitConfig
import traceback
import asyncio

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
        
        # CCXT exchange 객체 초기화
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
        
        # REST API base URL 설정
        self.base_url = self.config.base_url  # config에서 가져오는 대신 직접 설정
        
        # 테스트넷 설정
        if self.config.testnet:
            self.exchange.set_sandbox_mode(True)
            self.base_url = "https://api-testnet.bybit.com"  # 테스트넷 URL
        else:
            self.base_url = "https://api.bybit.com"  # 메인넷 URL

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
            timestamp = str(int(time.time() * 1000))
            request_params = params.copy() if params else {}
            request_params['timestamp'] = timestamp
            
            # recv_window 값 설정
            recv_window = '5000'
            
            # 서명 생성
            param_str = '&'.join([f"{k}={v}" for k, v in sorted(request_params.items())])
            sign_str = timestamp + self.config.api_key + recv_window + param_str
            signature = hmac.new(
                self.config.api_secret.encode('utf-8'),
                sign_str.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            # API 요청 헤더
            headers = {
                'X-BAPI-API-KEY': self.config.api_key,
                'X-BAPI-SIGN': signature,
                'X-BAPI-TIMESTAMP': timestamp,
                'X-BAPI-RECV-WINDOW': recv_window
            }

            # URL 경로 수정 (v5 중복 제거)
            if path.startswith('/v5'):
                path = path[3:]
            elif path.startswith('v5/'):
                path = path[3:]
            url = f"{self.base_url}/v5{path}"
            
            logger.info(f"서명 문자열: {sign_str}")
            logger.info(f"API 요청: URL={url}, params={request_params}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=request_params, headers=headers) as response:
                    text = await response.text()
                    logger.info(f"API 응답 텍스트: {text}")
                    if text:
                        result = json.loads(text)
                        return result
                    return None

        except Exception as e:
            logger.error(f"API 요청 실패: {str(e)}")
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
            return await self._request('GET', '/position/closed-pnl/list', params)
        except Exception as e:
            logger.error(f"closed-pnl API 호출 실패: {str(e)}")
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

    async def fetch_my_trades(self, symbol: str, since: int = None, params: Dict = None) -> List[Dict]:
        """거래 내역 조회 API"""
        try:
            trades = await self.exchange.fetch_my_trades(symbol, since=since, params=params)
            if trades:
                logger.debug(f"조회된 거래 수: {len(trades)}건")
            return trades
        except Exception as e:
            logger.error(f"거래 내역 조회 API 호출 실패: {str(e)}")
            return []

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
            response = await self.v5_get("/account/wallet-balance", {
                "accountType": "UNIFIED"
            })
            return response
        except Exception as e:
            logger.error(f"잔고 조회 API 호출 실패: {str(e)}")
            return {}

    async def get_positions(self, symbol: str = None) -> Dict:
        """포지션 조회 API 호출"""
        try:
            params = {
                "category": "linear",
                "settleCoin": "USDT"
            }
            if symbol:
                params["symbol"] = symbol

            response = await self.v5_get("/position/list", params)
            return response
                
        except Exception as e:
            logger.error(f"포지션 조회 API 호출 실패: {str(e)}")
            return None

    # 아래 메서드들은 현재 사용하지 않으므로 주석 처리
    '''
    async def fetch_closed_positions(self, symbol: str, start_time: int = None, end_time: int = None) -> List[Dict]:
        """포지션 조회 API 호출"""
        try:
            params = {
                "category": "linear",
                "symbol": symbol,
                "limit": 100
            }
            
            if start_time:
                params["startTime"] = start_time
            if end_time:
                params["endTime"] = end_time
                
            response = await self.v5_get("/position/closed-pnl/list", params)
            if response and response.get('retCode') == 0:
                return response.get('result', {}).get('list', [])
            return []
                
        except Exception as e:
            logger.error(f"포지션 조회 API 호출 실패: {str(e)}")
            return []
    '''
