import logging
from typing import Dict, Optional, List, Tuple
import pandas as pd
from datetime import datetime, timedelta
from decimal import Decimal
import traceback
import ccxt.async_support as ccxt
import asyncio
from exchange.bybit_client import BybitClient
from config import config

logger = logging.getLogger(__name__)

class MarketDataService:
    """시장 데이터 관리 서비스"""
    
    VALID_TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d']
    CACHE_DURATION = {
        '1m': timedelta(minutes=1),
        '3m': timedelta(minutes=3),
        '5m': timedelta(minutes=5),
        '15m': timedelta(minutes=15),
        '30m': timedelta(minutes=30),
        '1h': timedelta(hours=1),
        '2h': timedelta(hours=2),
        '4h': timedelta(hours=4),
        '6h': timedelta(hours=6),
        '12h': timedelta(hours=12),
        '1d': timedelta(days=1)
    }
    
    # 시간대 매핑 추가
    TIMEFRAME_MAP = {
        '15m': '15',
        '1h': '60',
        '4h': '240',
        '1d': 'D'
    }
    
    # 시간대별 필요한 데이터 개수 정의
    TIMEFRAME_LIMITS = {
        '15m': 64,   # 16시간
        '1h': 48,    # 2일
        '4h': 90,    # 15일
        '1d': 45     # 1.5개월
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
            
            # 설정된 limit 사용
            limit = self.timeframe_limits.get(timeframe, 100)
            
            # fetch_ohlcv 사용
            response = await self.exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit
            )
            
            if response:
                return [{
                    'timestamp': item[0],
                    'open': item[1],
                    'high': item[2],
                    'low': item[3],
                    'close': item[4],
                    'volume': item[5]
                } for item in response]
                
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
        """시장 데이터 조회"""
        try:
            ticker = await self.get_ticker(symbol)
            if not ticker:
                logger.error("티커 데이터를 가져올 수 없습니다")
                return None
            
            return {
                'symbol': symbol,
                'last_price': float(ticker.get('last', 0)),
                'bid': float(ticker.get('bid', 0)),
                'ask': float(ticker.get('ask', 0)),
                'volume': float(ticker.get('baseVolume', 0)),
                'timestamp': ticker.get('timestamp', 0)
            }
            
        except Exception as e:
            logger.error(f"시장 데이터 조회 실패: {str(e)}")
            return None

    async def get_current_price(self) -> Optional[Dict]:
        """현재가 조회"""
        try:
            params = {
                'category': 'linear',
                'symbol': 'BTCUSDT'
            }
            
            ticker = await self.bybit_client.exchange.fetch_ticker('BTCUSDT', params=params)
            if ticker:
                return {
                    'symbol': ticker['symbol'],
                    'last_price': float(ticker['last']),
                    'mark_price': float(ticker.get('mark', ticker['last'])),
                    'index_price': float(ticker.get('index', ticker['last'])),
                    'timestamp': ticker['timestamp']
                }
            
            logger.error("티커 데이터를 가져올 수 없습니다")
            return None
            
        except Exception as e:
            logger.error(f"현재가 조회 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None
