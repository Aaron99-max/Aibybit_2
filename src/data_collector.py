from indicators.technical import TechnicalIndicators
import time

class DataCollector:
    def __init__(self, exchange, symbol, timeframes):
        self.exchange = exchange
        self.symbol = symbol
        self.timeframes = timeframes
        self.last_check = {
            '15m': 0,
            '1h': 0,
            '4h': 0,
            '1d': 0
        }
        
    async def should_analyze(self, timeframe: str) -> bool:
        """해당 시간프레임의 분석이 필요한지 확인"""
        current_time = int(time.time())
        interval_seconds = {
            '15m': 15 * 60,
            '1h': 60 * 60,
            '4h': 4 * 60 * 60,
            '1d': 24 * 60 * 60
        }[timeframe]
        
        # 마지막 체크 시간과 현재 시간의 차이가 interval보다 크면 분석 필요
        if current_time - self.last_check[timeframe] > interval_seconds:
            self.last_check[timeframe] = current_time
            return True
        return False

    async def check_and_analyze(self):
        """각 시간프레임별 분석 필요 여부 확인 및 실행"""
        for timeframe in self.timeframes:
            if await self.should_analyze(timeframe):
                logger.info(f"{timeframe} 분석 시작")
                # 분석 실행
                await self.analyze_timeframe(timeframe)

    async def fetch_data(self):
        data = {}
        for timeframe in self.timeframes:
            ohlcv = await self.exchange.fetch_ohlcv(self.symbol, timeframe)
            df = TechnicalIndicators.calculate_indicators(ohlcv)  # 기술적 지표 계산
            data[timeframe] = {
                "ohlcv": ohlcv,
                "indicators": df  # 계산된 지표 포함
            }
        return data
    
    def calculate_indicators(self, ohlcv):
        # RSI, 거래량, RSI 다이버전스 등 계산
        pass 