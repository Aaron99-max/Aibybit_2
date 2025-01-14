import ccxt.async_support as ccxt
from typing import Dict, List
import logging
from config.bybit_config import BybitConfig
import time
import json
import hmac
import hashlib
import aiohttp

logger = logging.getLogger(__name__)

class BybitClient:
    def __init__(self, config: BybitConfig = None):
        """
        Args:
            config: Bybit 설정
        """
        self.config = config or BybitConfig()
        
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
        
        # REST API base URL
        self.base_url = self.config.base_url
        
        # 테스트넷 설정
        if self.config.testnet:
            self.exchange.set_sandbox_mode(True)

    def setup_exchange(self):
        """API 설정"""
        self.exchange.apiKey = self.config.api_key
        self.exchange.secret = self.config.api_secret
        
        if self.config.is_testnet:
            self.exchange.urls['api'] = self.exchange.urls['test']
        
        self.exchange.options['defaultType'] = 'linear'

    async def v5_post(self, path: str, params: Dict = None) -> Dict:
        """V5 API POST 요청"""
        try:
            response = await self.exchange.private_post_v5(path, params)
            return response
        except Exception as e:
            logger.error(f"API 요청 실패 (POST {path}): {str(e)}")
            return None

    async def v5_get(self, path: str, params: Dict = None) -> Dict:
        """V5 API GET 요청"""
        try:
            # CCXT의 private_get_v5 대신 _request 사용
            response = await self._request("GET", f"/v5{path}", params)
            return response
        except Exception as e:
            logger.error(f"API 요청 실패 (GET {path}): {str(e)}")
            return None

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
                sign_payload = timestamp + self.config.api_key + recv_window + query_string
            else:
                sign_payload = timestamp + self.config.api_key + recv_window + json.dumps(request_params)
            
            # 서명 생성
            signature = hmac.new(
                bytes(self.config.api_secret, 'utf-8'),
                bytes(sign_payload, 'utf-8'),
                hashlib.sha256
            ).hexdigest()

            url = f"{self.base_url}{path}"
            headers = {
                'X-BAPI-API-KEY': self.config.api_key,
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

    async def fetch_my_trades(self, symbol: str, since: int = None, params: Dict = None) -> List[Dict]:
        """거래 내역 조회 API"""
        try:
            return await self.exchange.fetch_my_trades(symbol, since=since, params=params)
        except Exception as e:
            logger.error(f"거래 내역 조회 API 호출 실패: {str(e)}")
            return []

    async def get_positions(self, symbol: str) -> List[Dict]:
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

    async def get_balance(self) -> Dict:
        """잔고 조회"""
        try:
            # V5 API로 시도
            try:
                response = await self.v5_get("/account/wallet-balance", {
                    "accountType": "UNIFIED",
                    "coin": "USDT"  # USDT 잔고만 조회
                })
                logger.debug(f"V5 Balance Response: {response}")
                
                if response and response.get('retCode') == 0:
                    result = response.get('result', {})
                    wallet_info = result.get('list', [{}])[0]
                    coin_info = wallet_info.get('coin', [{}])[0]  # USDT 정보
                    
                    return {
                        'list': [{
                            'coin': [{
                                'walletBalance': coin_info.get('walletBalance', '0'),
                                'locked': coin_info.get('locked', '0'),
                                'availableToWithdraw': coin_info.get('availableToWithdraw', '0')
                            }]
                        }]
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

    async def close(self):
        """연결 종료"""
        if hasattr(self, 'exchange'):
            await self.exchange.close()