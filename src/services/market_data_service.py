import logging
from typing import Dict, Optional, List, Tuple
import pandas as pd
from datetime import datetime, timedelta
from decimal import Decimal
from telegram_bot.utils.decorators import error_handler
import traceback
import ccxt.async_support as ccxt
import asyncio
from exchange.bybit_client import BybitClient
from config import config

logger = logging.getLogger(__name__)

class MarketDataService:
    """시장 데이터 관리 서비스"""
    
    # 필요한 시간대만 남기고 나머지 제거
    VALID_TIMEFRAMES = ['1m', '1h']
    CACHE_DURATION = {
        '1m': timedelta(minutes=1),
        '1h': timedelta(hours=1)
    }
    
    # 1시간봉 데이터만 필요
    TIMEFRAME_LIMITS = {
        '1m': 1,     # 현재가용
        '1h': 48,    # 2일치 데이터
    }
    
    # 시간대 매핑도 1시간만
    TIMEFRAME_MAP = {
        '1m': '1',
        '1h': '60'
    }
    
    def __init__(self, bybit_client: BybitClient):
        self.bybit_client = bybit_client
        self.exchange = bybit_client.exchange
        self.markets = {}
        
        # 설정 로드
        market_config = config.load_json_config('market_config.json')
        self.timeframe_limits = market_config['timeframes']['limits']
        self.cache_duration = market_config['timeframes']['cache_duration']
        self.symbol = market_config['symbols']['default']
        
    async def initialize(self):
        """마켓 데이터 초기화"""
        try:
            # 마켓 데이터 로드
            await self.bybit_client.exchange.load_markets()
            self.markets = self.bybit_client.exchange.markets
            logger.info("마켓 데이터 로드 완료")
            
        except ccxt.InvalidNonce as e:
            logger.error(f"타임스탬프 오류: {str(e)}")
            # 시간 동기화 후 재시도
            await asyncio.sleep(1)
            await self.initialize()
            
        except Exception as e:
            logger.error(f"마켓 데이터 로드 실패: {str(e)}")
            raise

    async def get_ohlcv(self, symbol: str, timeframe: str) -> List[Dict]:
        """OHLCV 데이터 조회"""
        try:
            logger.info(f"OHLCV 데이터 조회 시작 - 심볼: {symbol}, 시간대: {timeframe}")
            
            if timeframe not in self.VALID_TIMEFRAMES:
                logger.error(f"잘못된 시간대: {timeframe}")
                return []
            
            # 설정된 limit 사용
            limit = self.timeframe_limits.get(timeframe, 100)
            
            try:
                # fetch_ohlcv 사용
                response = await self.exchange.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=limit
                )
                
                if not response:
                    logger.error("OHLCV 데이터가 비어있습니다")
                    return []
                
                return [{
                    'timestamp': int(item[0]),  # 정수형으로 변환
                    'open': float(item[1]),     # 실수형으로 변환
                    'high': float(item[2]),
                    'low': float(item[3]),
                    'close': float(item[4]),
                    'volume': float(item[5])
                } for item in response]
                
            except ccxt.NetworkError as e:
                logger.error(f"네트워크 오류: {str(e)}")
                await asyncio.sleep(1)  # 재시도 전 대기
                return await self.get_ohlcv(symbol, timeframe)
                
            except Exception as e:
                logger.error(f"OHLCV 데이터 조회 중 오류: {str(e)}")
                return []
            
        except Exception as e:
            logger.error(f"OHLCV 데이터 조회 중 오류: {str(e)}")
            return []

    async def get_ticker(self, symbol: str) -> dict:
        """현재가 정보 조회"""
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            logger.error(f"현재가 조회 중 오류: {str(e)}")
            return {}

    async def get_market_data(self, symbol: str) -> Dict:
        """확장된 시장 데이터 조회"""
        try:
            # 기본 티커 데이터
            ticker = await self.get_ticker(symbol)
            if not ticker:
                return None

            # 24시간 가격 변동 계산
            price_change_24h = ((ticker.get('last', 0) - ticker.get('open', 0)) / ticker.get('open', 0)) * 100

            # 자금 조달 비율
            funding_info = await self.bybit_client.get_funding_rate(symbol)
            
            # 미체결 약정
            open_interest = await self.bybit_client.get_open_interest(symbol)
            
            # 롱/숏 비율
            long_short_ratio = await self.bybit_client.get_long_short_ratio(symbol)

            return {
                'price_data': {
                    'symbol': symbol,
                    'last_price': float(ticker.get('last', 0)),
                    'price_change_24h': round(price_change_24h, 2),
                    'volume': float(ticker.get('baseVolume', 0))
                },
                'market_metrics': {
                    'funding_rate': funding_info.get('funding_rate', 0),
                    'next_funding_time': funding_info.get('next_funding_time'),
                    'open_interest': open_interest,
                    'long_short_ratio': long_short_ratio
                },
                'order_book': await self.get_order_book(symbol)
            }
            
        except Exception as e:
            logger.error(f"시장 데이터 조회 실패: {str(e)}")
            return None

    async def get_funding_rate(self, symbol: str) -> float:
        """자금 조달 비율 조회"""
        try:
            response = await self.bybit_client.get_funding_rate(symbol)
            return float(response.get('funding_rate', 0))
        except Exception as e:
            logger.error(f"자금 조달 비율 조회 실패: {str(e)}")
            return 0.0

    async def get_order_book(self, symbol: str, limit: int = 25) -> Dict:
        """호가창 데이터 조회"""
        try:
            order_book = await self.exchange.fetch_order_book(symbol, limit)
            return {
                'bids': order_book['bids'][:limit],
                'asks': order_book['asks'][:limit],
                'bid_volume': sum(bid[1] for bid in order_book['bids'][:limit]),
                'ask_volume': sum(ask[1] for ask in order_book['asks'][:limit])
            }
        except Exception as e:
            logger.error(f"호가창 조회 실패: {str(e)}")
            return {}

    async def get_open_interest(self, symbol: str) -> Dict:
        """미체결 약정 조회"""
        try:
            response = await self.bybit_client.get_open_interest(symbol)
            return {
                'value': float(response.get('open_interest', 0)),
                'change_24h': float(response.get('change_24h', 0))
            }
        except Exception as e:
            logger.error(f"미체결 약정 조회 실패: {str(e)}")
            return {'value': 0, 'change_24h': 0}

    async def get_current_price(self) -> Optional[Dict]:
        """현재가 조회 (1분봉 사용)"""
        try:
            # 1분봉 최신 데이터 가져오기
            ohlcv = await self.get_ohlcv(self.symbol, '1m')
            if not ohlcv:
                return None
                
            latest = ohlcv[-1]  # 최신 데이터
            
            return {
                'symbol': self.symbol,
                'last_price': float(latest['close']),
                'timestamp': latest['timestamp']
            }
            
        except Exception as e:
            logger.error(f"현재가 조회 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None
