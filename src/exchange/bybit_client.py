import ccxt.async_support as ccxt
import logging
import hmac
import hashlib
import time
import aiohttp
from typing import Dict
from config.bybit_config import BybitConfig

logger = logging.getLogger(__name__)

class BybitClient:
    def __init__(self, config: BybitConfig = None):
        """
        Args:
            config: Bybit 설정
        """
        self.config = config or BybitConfig()
        self.base_url = self.config.base_url
        
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

    async def _request(self, method: str, path: str, params: Dict = None) -> Dict:
        """API 요청 공통 메서드"""
        try:
            timestamp = str(int(time.time() * 1000))
            params = params or {}
            params['timestamp'] = timestamp
            params = dict(sorted(params.items()))
            
            param_str = '&'.join([f"{k}={v}" for k, v in params.items()])
            sign_str = timestamp + self.config.api_key + "5000" + param_str
            signature = hmac.new(
                self.config.api_secret.encode('utf-8'),
                sign_str.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            headers = {
                'X-BAPI-API-KEY': self.config.api_key,
                'X-BAPI-SIGN': signature,
                'X-BAPI-SIGN-TYPE': '2',
                'X-BAPI-TIMESTAMP': timestamp,
                'X-BAPI-RECV-WINDOW': '5000',
                'Content-Type': 'application/json'
            }
            
            url = f"{self.config.base_url}{path}"
            
            async with aiohttp.ClientSession() as session:
                if method == 'GET':
                    async with session.get(url, params=params, headers=headers) as response:
                        return await response.json()
                elif method == 'POST':
                    async with session.post(url, json=params, headers=headers) as response:
                        return await response.json()
                    
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
            return await self.v5_get("/position/closed-pnl", params)
        except Exception as e:
            logger.error(f"API 호출 실패: {str(e)}")
            return None

    async def v5_get_positions(self, params: Dict) -> Dict:
        """V5 API positions 조회"""
        try:
            return await self.v5_get("/position/list", params)
        except Exception as e:
            logger.error(f"API 호출 실패: {str(e)}")
            return None

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
