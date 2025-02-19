import ccxt.async_support as ccxt
from typing import Dict, List
import logging
from config.bybit_config import BybitConfig
import time
import json
import hmac
import hashlib
import aiohttp
import asyncio

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
            
            # 요청 파라미터 검증
            if not isinstance(request_params, dict):
                raise ValueError("잘못된 요청 파라미터 형식")
            
            if method == "GET":
                query_string = '&'.join([f"{k}={v}" for k, v in sorted(request_params.items())])
                sign_payload = timestamp + self.config.api_key + recv_window + query_string
            else:
                sign_payload = timestamp + self.config.api_key + recv_window + json.dumps(request_params)
            
            # API 키 검증
            if not self.config.api_key or not self.config.api_secret:
                raise ValueError("API 키가 설정되지 않았습니다")
            
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
                for retry in range(3):  # 최대 3번 재시도
                    try:
                        if method == "GET":
                            async with session.get(url, params=request_params, headers=headers) as response:
                                result = await response.json()
                        else:  # POST
                            async with session.post(url, json=request_params, headers=headers) as response:
                                result = await response.json()
                                
                        # 응답 검증
                        if result.get('retCode') != 0:
                            logger.error(f"API 오류: {result.get('retMsg')}")
                            if retry < 2:  # 마지막 시도가 아니면 재시도
                                await asyncio.sleep(1 * (retry + 1))
                                continue
                        return result
                        
                    except aiohttp.ClientError as e:
                        logger.error(f"네트워크 오류 (시도 {retry + 1}/3): {str(e)}")
                        if retry < 2:
                            await asyncio.sleep(1 * (retry + 1))
                            continue
                        raise
                        
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

    async def get_funding_rate(self, symbol: str) -> Dict:
        """자금 조달 비율 조회"""
        try:
            params = {
                'category': 'linear',
                'symbol': symbol,
                'limit': 1  # 최신 데이터 1개만 조회
            }
            response = await self._request('GET', '/v5/market/funding/history', params)
            
            if response and response.get('retCode') == 0:
                funding_info = response.get('result', {}).get('list', [{}])[0]
                return {
                    'funding_rate': float(funding_info.get('fundingRate', 0)),
                    'next_funding_time': funding_info.get('fundingRateTimestamp'),
                    'predicted_funding_rate': float(funding_info.get('predictedFundingRate', 0))
                }
            return {'funding_rate': 0, 'next_funding_time': None, 'predicted_funding_rate': 0}
            
        except Exception as e:
            logger.error(f"자금 조달 비율 조회 실패: {str(e)}")
            return {'funding_rate': 0, 'next_funding_time': None, 'predicted_funding_rate': 0}

    async def get_open_interest(self, symbol: str) -> Dict:
        """미체결 약정 조회"""
        try:
            params = {
                'category': 'linear',
                'symbol': symbol,
                'intervalTime': '5min',  # intervalTime으로 수정
                'limit': 288  # 24시간 데이터 (288 = 24h/5min)
            }
            response = await self._request('GET', '/v5/market/open-interest', params)
            
            if response and response.get('retCode') == 0:
                data_list = response.get('result', {}).get('list', [])
                if not data_list:
                    return {'value': 0, 'change_24h': 0, 'timestamp': None}
                    
                current_oi = float(data_list[0].get('openInterest', 0))
                oi_24h_ago = float(data_list[-1].get('openInterest', 0)) if len(data_list) >= 288 else current_oi
                
                change_24h = ((current_oi - oi_24h_ago) / oi_24h_ago * 100) if oi_24h_ago > 0 else 0
                
                return {
                    'value': current_oi,
                    'change_24h': change_24h,
                    'timestamp': data_list[0].get('timestamp')
                }
            return {'value': 0, 'change_24h': 0, 'timestamp': None}
            
        except Exception as e:
            logger.error(f"미체결 약정 조회 실패: {str(e)}")
            return {'value': 0, 'change_24h': 0, 'timestamp': None}

    async def get_long_short_ratio(self, symbol: str) -> float:
        """롱/숏 비율 조회"""
        try:
            params = {
                'category': 'linear',
                'symbol': symbol,
                'period': '5min',
                'limit': 1
            }
            response = await self._request('GET', '/v5/market/account-ratio', params)
            
            if response and response.get('retCode') == 0:
                ratio_data = response.get('result', {}).get('list', [{}])[0]
                long_ratio = float(ratio_data.get('longAccount', 0))
                short_ratio = float(ratio_data.get('shortAccount', 0))
                
                return round(long_ratio / short_ratio, 2) if short_ratio > 0 else 1.0
                
            return 1.0
            
        except Exception as e:
            logger.error(f"롱/숏 비율 조회 실패: {str(e)}")
            return 1.0