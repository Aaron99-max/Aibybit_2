import os
import json
import time
import hmac
import hashlib
import logging
import aiohttp
import ccxt.async_support as ccxt
import traceback
import ssl
import certifi
import asyncio
from typing import Dict, Optional, List
from config.bybit_config import BybitConfig
from .websocket_client import BybitWebsocketClient

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
        
        # SSL 컨텍스트 설정
        self.ssl_context = ssl.create_default_context(cafile=certifi.where())
        
        # WebSocket 클라이언트 초기화
        self.ws_client = BybitWebsocketClient(self.config)
        
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
            },
            'verify': True,
            'certifi': certifi.where(),
            'ssl': {
                'ca': certifi.where()
            }
        })
        
        # 테스트넷 설정
        if self.config.testnet:
            self.exchange.set_sandbox_mode(True)

        # 세션 초기화
        self.session = None
        
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
            
            # 3. 서명용 파라미터 준비
            sign_params = request_params.copy()
            sign_params['timestamp'] = timestamp
            sign_params['api_key'] = self.config.api_key
            sign_params['recv_window'] = '5000'
            
            # 4. 정렬된 파라미터로 쿼리 스트링 생성 (알파벳 순서로 정렬)
            sorted_params = sorted(sign_params.items())
            query_string = '&'.join([f"{key}={value}" for key, value in sorted_params])
            
            # 디버그 로그
            logger.debug(f"Parameters for signature: {sign_params}")
            logger.debug(f"Query string for signature: {query_string}")
            
            # 5. 서명 생성
            signature = hmac.new(
                self.config.api_secret.encode('utf-8'),
                query_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # 6. 최종 요청 파라미터 준비
            request_params.update({
                'api_key': self.config.api_key,
                'timestamp': timestamp,
                'recv_window': '5000',
                'sign': signature
            })
            
            # 7. API 요청 준비
            url = f"{self.config.base_url}{path}"
            headers = {
                'Content-Type': 'application/json'
            }
            
            # 디버그 로그
            logger.debug(f"Final request URL: {url}")
            logger.debug(f"Final request params: {request_params}")
            logger.debug(f"Final request headers: {headers}")
            
            # 8. API 요청 실행
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

    async def v5_get_positions(self, params: Dict) -> Dict:
        """V5 API position/list 조회"""
        try:
            response = await self.exchange.private_get_v5_position_list(params)
            return response
        except Exception as e:
            logger.error(f"포지션 조회 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return {}

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

    async def start_ws(self):
        """웹소켓 연결 시작"""
        try:
            logger.info("웹소켓 연결 시작...")
            await self.ws_client.connect()
            asyncio.create_task(self.ws_client.start_monitoring())
            logger.info("웹소켓 모니터링 시작됨")
        except Exception as e:
            logger.error(f"웹소켓 시작 실패: {str(e)}")
            logger.error(traceback.format_exc())
