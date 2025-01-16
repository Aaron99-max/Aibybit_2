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
        '15m': 192,  # 2일 (8 * 24)
        '1h': 168,   # 7일 (24 * 7)
        '4h': 180,   # 30일 (6 * 30)
        '1d': 90     # 3개월 (30 * 3)
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
