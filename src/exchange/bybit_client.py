import ccxt.async_support as ccxt
from typing import Dict, List
import logging
from config.bybit_config import BybitConfig

logger = logging.getLogger(__name__)

class BybitClient:
    def __init__(self, config: BybitConfig = None):
        """
        Args:
            config: Bybit 설정
        """
        self.config = config or BybitConfig()
        self.exchange = ccxt.bybit()
        self.setup_exchange()

    def setup_exchange(self):
        """API 설정"""
        # API 키 설정
        self.exchange.apiKey = self.config.api_key
        self.exchange.secret = self.config.api_secret
        
        # 테스트넷 설정
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
            response = await self.exchange.private_get_v5(path, params)
            return response
        except Exception as e:
            logger.error(f"API 요청 실패 (GET {path}): {str(e)}")
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
            params = {
                'accountType': 'UNIFIED',
                'coin': 'USDT'
            }
            response = await self.v5_get("/account/wallet-balance", params)
            if response and response.get('retCode') == 0:
                return response.get('result', {})
            return None
        except Exception as e:
            logger.error(f"잔고 조회 중 오류: {str(e)}")
            return None