import ccxt.async_support as ccxt
from typing import Dict
import logging
import traceback
import hmac
import hashlib
import time
import requests
import aiohttp
import json
import os

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
        
        # REST API base URL - 테스트넷 여부에 따라 설정
        if testnet:
            self.base_url = "https://api-testnet.bybit.com"
            self.exchange.set_sandbox_mode(True)
        else:
            self.base_url = "https://api.bybit.com"

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
            recv_window = "20000"
            params = params or {}
            
            # GET 요청의 경우 쿼리 문자열 생성
            if method == "GET":
                # 필수 파라미터 추가
                params_with_auth = {
                    **params,
                    'api_key': self.api_key,
                    'timestamp': timestamp,
                    'recv_window': recv_window
                }
                # 파라미터를 알파벳 순으로 정렬
                sorted_params = dict(sorted(params_with_auth.items()))
                # 쿼리 문자열 생성
                query_string = '&'.join([f"{k}={v}" for k, v in sorted_params.items()])
                # 서명 생성
                signature = hmac.new(
                    bytes(self.api_secret, 'utf-8'),
                    bytes(query_string, 'utf-8'),
                    hashlib.sha256
                ).hexdigest()
                # 서명을 쿼리 파라미터에 추가
                params_with_auth['sign'] = signature
                params = params_with_auth
            else:
                # POST 요청의 경우도 동일한 방식으로 처리
                params_with_auth = {
                    **params,
                    'api_key': self.api_key,
                    'timestamp': timestamp,
                    'recv_window': recv_window
                }
                query_string = '&'.join([f"{k}={v}" for k, v in sorted(params_with_auth.items())])
                signature = hmac.new(
                    bytes(self.api_secret, 'utf-8'),
                    bytes(query_string, 'utf-8'),
                    hashlib.sha256
                ).hexdigest()
                params_with_auth['sign'] = signature
                params = params_with_auth

            url = f"{self.base_url}{path}"
            headers = {'Content-Type': 'application/json'} if method == "POST" else {}
            
            logger.debug(f"요청 URL: {url}")
            logger.debug(f"요청 파라미터: {params}")
            
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(url, params=params, headers=headers) as response:
                        response_text = await response.text()
                        if response.status != 200:
                            logger.error(f"API 응답 상태 코드: {response.status}")
                            logger.error(f"응답 내용: {response_text}")
                            return None
                        return json.loads(response_text)
                else:
                    async with session.post(url, json=params, headers=headers) as response:
                        response_text = await response.text()
                        if response.status != 200:
                            logger.error(f"API 응답 상태 코드: {response.status}")
                            logger.error(f"응답 내용: {response_text}")
                            return None
                        return json.loads(response_text)

        except Exception as e:
            logger.error(f"API 요청 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
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
        try:
            # path가 이미 /v5로 시작하는지 확인
            if not path.startswith('/v5'):
                path = f"/v5{path}"
            
            logger.debug(f"V5 GET 요청 경로: {path}")
            return await self._request("GET", path, params)
        except Exception as e:
            logger.error(f"V5 GET 요청 실패: {str(e)}")
            logger.error(traceback.format_exc())
            return None

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

    async def get_closed_trades(self, symbol: str = "BTCUSDT", limit: int = 50):
        """완료된 거래 내역 조회"""
        try:
            logger.debug(f"현재 base_url: {self.base_url}")
            logger.debug(f"테스트넷 모드: {self.testnet}")

            params = {
                "category": "linear",
                "symbol": symbol,
                "limit": str(limit),
                "execType": "Trade"  # 실제 체결된 거래만
            }
            
            logger.debug(f"거래 내역 조회 요청 파라미터: {params}")
            
            # 개인 거래 내역 조회 엔드포인트로 변경
            response = await self.v5_get("/execution/list", params)
            logger.debug(f"거래 내역 조회 응답: {response}")
            
            if response and response.get("retCode") == 0:
                trades = response.get("result", {}).get("list", [])
                logger.info(f"거래 내역 조회 성공: {len(trades)}건")
                
                formatted_trades = []
                for trade in trades:
                    logger.debug(f"거래 데이터: {trade}")
                    
                    formatted_trade = {
                        "symbol": trade.get("symbol"),
                        "side": trade.get("side"),
                        "size": float(trade.get("execQty", 0)),
                        "entry_price": float(trade.get("execPrice", 0)),
                        "exit_price": float(trade.get("execPrice", 0)),
                        "realized_pnl": float(trade.get("closedPnl", 0)),
                        "timestamp": int(trade.get("execTime", time.time() * 1000))
                    }
                    formatted_trades.append(formatted_trade)
                
                return formatted_trades
            else:
                logger.error(f"거래 내역 조회 실패: {response}")
                return []
                
        except Exception as e:
            logger.error(f"거래 내역 조회 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return []