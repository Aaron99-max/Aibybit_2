import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volume import VolumeWeightedAveragePrice, AccDistIndexIndicator
from ta.trend import MACD, ADXIndicator, IchimokuIndicator
from ta.volatility import BollingerBands
import logging
from typing import Optional, Dict, Any
import traceback

logger = logging.getLogger(__name__)

class TechnicalIndicators:
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """모든 기술적 지표 계산"""
        try:
            # 입력이 리스트인 경우 DataFrame으로 변환
            if isinstance(df, list):
                df = pd.DataFrame(df, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
            
            if df.empty:
                logger.error("데이터가 비어있습니다")
                return None
            
            df = df.copy()
            
            # 24시간 가격 변화율 계산
            df['price_change_24h'] = df['close'].pct_change(periods=24) * 100
            
            # 거래량 증감률 계산
            df['volume_change_24h'] = (
                (df['volume'] - df['volume'].rolling(window=24).mean()) / 
                df['volume'].rolling(window=24).mean() * 100
            )
            
            # RSI 계산
            df['rsi'] = self.calculate_rsi(df['close'])
            
            # MACD 계산
            macd_data = self.calculate_macd(df['close'])
            df['macd'] = macd_data['macd']
            df['macd_signal'] = macd_data['signal']
            
            # 볼린저 밴드 계산
            bb_data = self.calculate_bollinger_bands(df['close'])
            df['bb_upper'] = bb_data['upper']
            df['bb_middle'] = bb_data['middle']
            df['bb_lower'] = bb_data['lower']
            
            # 이동평균선 계산
            df['sma_10'] = df['close'].rolling(window=10).mean()
            df['sma_30'] = df['close'].rolling(window=30).mean()
            
            # ADX 계산
            adx_indicator = ADXIndicator(df['high'], df['low'], df['close'])
            df['adx'] = adx_indicator.adx()
            df['di_plus'] = adx_indicator.adx_pos()
            df['di_minus'] = adx_indicator.adx_neg()
            
            # 추세 판단
            df['trend'] = self._get_trend_direction(df)
            df['trend_strength'] = self._get_trend_strength(df)
            
            # RSI 다이버전스 계산
            divergence = self.check_rsi_divergence(df)
            df['divergence_type'] = divergence['type']
            df['divergence_desc'] = divergence['description']
            
            # NaN 값 처리
            df = df.fillna(method='ffill').fillna(0)
            
            return df
            
        except Exception as e:
            logger.error(f"지표 계산 중 오류: {str(e)}")
            return None

    @staticmethod
    def check_rsi_divergence(df: pd.DataFrame, window: int = 14) -> Dict:
        """RSI 다이버전스 확인"""
        try:
            if 'rsi' not in df.columns:
                return {"type": "없음", "description": "RSI 데이터 없음"}
                
            # 최근 N개 봉에서 고점/저점 찾기
            last_n = df.tail(window)
            
            # 가격과 RSI의 고점/저점 찾기
            price_high = last_n['close'].max()
            price_low = last_n['close'].min()
            rsi_high = last_n['rsi'].max()
            rsi_low = last_n['rsi'].min()
            
            current_price = df['close'].iloc[-1]
            current_rsi = df['rsi'].iloc[-1]
            prev_rsi = df['rsi'].iloc[-2]
            
            # 베어리시 다이버전스
            if (current_price >= price_high * 0.998 and  # 가격이 신고점 근처
                current_rsi < rsi_high * 0.95 and        # RSI는 이전 고점보다 낮음
                current_rsi < prev_rsi):                 # RSI 하락 중
                return {
                    "type": "베어리시",
                    "description": f"가격은 신고점({current_price:.0f}) 도달, RSI({current_rsi:.1f})는 이전 고점({rsi_high:.1f})보다 낮음"
                }
                
            # 불리시 다이버전스
            if (current_price <= price_low * 1.002 and   # 가격이 신저점 근처
                current_rsi > rsi_low * 1.05 and         # RSI는 이전 저점보다 높음
                current_rsi > prev_rsi):                 # RSI 상승 중
                return {
                    "type": "불리시",
                    "description": f"가격은 신저점({current_price:.0f}) 도달, RSI({current_rsi:.1f})는 이전 저점({rsi_low:.1f})보다 높음"
                }
                
            return {"type": "없음", "description": "현재 다이버전스 없음"}
            
        except Exception as e:
            logger.error(f"다이버전스 확인 중 오류: {str(e)}")
            return {"type": "오류", "description": str(e)}

    @staticmethod
    def get_trend_strength(df: pd.DataFrame) -> dict:
        """추세 강도 분석"""
        latest = df.iloc[-1]
        
        trend_strength = {
            'adx_trend': 'strong' if latest['adx'] > 25 else 'weak',
            'price_trend': 'up' if latest['di_plus'] > latest['di_minus'] else 'down',
            'ma_trend': 'up' if latest['sma_20'] > latest['sma_50'] else 'down',
            'ichimoku_trend': 'up' if latest['ichimoku_base'] > latest['ichimoku_conv'] else 'down'
        }
        
        return trend_strength

    @staticmethod
    def analyze_market_condition(df: pd.DataFrame) -> Dict:
        """시장 상태 분석"""
        try:
            latest = df.iloc[-1]
            
            # 과매수/과매도 상태 확인
            rsi_state = "과매수" if latest['rsi'] > 70 else "과매도" if latest['rsi'] < 30 else "중립"
            
            # 볼린저 밴드 기준 가격 위치
            bb_position = "상단" if latest['close'] > latest['bb_upper'] else \
                         "하단" if latest['close'] < latest['bb_lower'] else "중간"
            
            # 거래량 트렌드
            volume_trend = "증가" if latest['volume_ratio'] > 1.5 else \
                          "감소" if latest['volume_ratio'] < 0.5 else "보통"
            
            return {
                'rsi_state': rsi_state,
                'bb_position': bb_position,
                'volume_trend': volume_trend,
                'adx_strength': "강함" if latest['adx'] > 25 else "약함",
                'trend_direction': "상승" if latest['di_plus'] > latest['di_minus'] else "하락"
            }
            
        except Exception as e:
            logger.error(f"시장 상태 분석 중 에러: {str(e)}")
            return {}

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """RSI(Relative Strength Index) 계산"""
        try:
            # 가격 변화 계산
            delta = prices.diff()
            
            # 상승/하락 구분
            gain = (delta.where(delta > 0, 0)).fillna(0)
            loss = (-delta.where(delta < 0, 0)).fillna(0)
            
            # 평균 계산
            avg_gain = gain.rolling(window=period).mean()
            avg_loss = loss.rolling(window=period).mean()
            
            # 0으로 나누기 방지
            avg_loss = avg_loss.replace(0, 0.00001)
            
            # RSI 계산
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi
            
        except Exception as e:
            logger.warning(f"RSI 계산 중 오류: {str(e)}")
            return pd.Series([50] * len(prices))  # 오류 시 중립값 반환

    def calculate_macd(self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
        """MACD(Moving Average Convergence Divergence) 계산"""
        try:
            # EMA 계산
            exp1 = prices.ewm(span=fast, adjust=False).mean()
            exp2 = prices.ewm(span=slow, adjust=False).mean()
            
            # MACD 라인
            macd = exp1 - exp2
            
            # 시그널 라인
            signal = macd.ewm(span=signal, adjust=False).mean()
            
            # 히스토그램
            hist = macd - signal
            
            return {
                'macd': macd,
                'signal': signal,
                'histogram': hist
            }
            
        except Exception as e:
            logger.error(f"MACD 계산 중 오류: {str(e)}")
            return {
                'macd': pd.Series([0] * len(prices)),
                'signal': pd.Series([0] * len(prices)),
                'histogram': pd.Series([0] * len(prices))
            }

    def calculate_bollinger_bands(self, prices: pd.Series, period: int = 20, std: float = 2.5) -> Dict:
        """볼린저 밴드 계산"""
        try:
            # 중심선 (SMA)
            middle = prices.rolling(window=period).mean()
            
            # 표준편차
            std_dev = prices.rolling(window=period).std()
            
            # 상단/하단 밴드
            upper = middle + (std_dev * std)
            lower = middle - (std_dev * std)
            
            return {
                'upper': upper,
                'middle': middle,
                'lower': lower
            }
            
        except Exception as e:
            logger.error(f"볼린저 밴드 계산 중 오류: {str(e)}")
            return {
                'upper': pd.Series([0] * len(prices)),
                'middle': pd.Series([0] * len(prices)),
                'lower': pd.Series([0] * len(prices))
            }

    def get_bb_position(self, df: pd.DataFrame) -> str:
        """볼린저 밴드 상의 현재 가격 위치 반환"""
        try:
            latest = df.iloc[-1]
            if latest['close'] > latest['bb_upper']:
                return '상단'
            elif latest['close'] < latest['bb_lower']:
                return '하단'
            return '중단'
        except Exception as e:
            logger.error(f"볼린저 밴드 위치 계산 중 오류: {str(e)}")
            return '중단'

    def _get_trend_direction(self, df: pd.DataFrame) -> str:
        """추세 방향 판단"""
        latest = df.iloc[-1]
        if (latest['sma_10'] > latest['sma_30'] and 
            latest['rsi'] > 50 and 
            latest['macd'] > 0):
            return "UPTREND"
        elif (latest['sma_10'] < latest['sma_30'] and 
              latest['rsi'] < 50 and 
              latest['macd'] < 0):
            return "DOWNTREND"
        return "SIDEWAYS"

    def _get_trend_strength(self, df: pd.DataFrame) -> int:
        """추세 강도 계산 (0-100)"""
        latest = df.iloc[-1]
        strength = 0
        
        # RSI 반영
        strength += abs(latest['rsi'] - 50) * 2
        
        # MACD 반영
        if abs(latest['macd']) > abs(latest['macd_signal']):
            strength += 20
            
        # ADX 반영 (있는 경우)
        if 'adx' in df.columns:
            strength += min(latest['adx'], 30)
            
        return min(int(strength), 100)

    def _analyze_rsi(self, rsi: float) -> str:
        """RSI 분석"""
        if rsi > 70:
            return "OVERBOUGHT"
        elif rsi < 30:
            return "OVERSOLD"
        elif rsi > 50:
            return "BULLISH"
        else:
            return "BEARISH"

    def _analyze_macd(self, macd: float, signal: float) -> str:
        """MACD 분석"""
        if macd > signal:
            if macd > 0:
                return "STRONG_BULLISH"
            return "BULLISH"
        elif macd < signal:
            if macd < 0:
                return "STRONG_BEARISH"
            return "BEARISH"
        return "NEUTRAL"

    def _analyze_bollinger(self, df: pd.DataFrame) -> str:
        """볼린저 밴드 분석"""
        try:
            latest = df.iloc[-1]
            current_price = latest['close']
            upper = latest['bb_upper']
            lower = latest['bb_lower']
            middle = latest['bb_middle']
            
            if current_price > upper:
                return "UPPER_BREAK"
            elif current_price < lower:
                return "LOWER_BREAK"
            elif current_price > middle:
                return "ABOVE_MIDDLE"
            else:
                return "BELOW_MIDDLE"
                
        except Exception as e:
            logger.error(f"볼린저 밴드 분석 중 오류: {str(e)}")
            return "NEUTRAL"

    def analyze_signals(self, df: pd.DataFrame) -> Dict[str, Any]:
        """모든 기술적 지표를 종합 분석"""
        try:
            latest = df.iloc[-1]
            
            # 1. 추세 분석
            trend = {
                "direction": self._get_trend_direction(df),
                "strength": self._get_trend_strength(df)
            }
            
            # 2. 주요 지표 신호
            signals = {
                "rsi": self._analyze_rsi(latest['rsi']),
                "macd": self._analyze_macd(latest['macd'], latest['macd_signal']),
                "bollinger": self._analyze_bollinger(df)
            }
            
            # 3. 시장 심리 분석
            sentiment = {
                "market": self._get_market_sentiment(df),
                "short_term": self._get_short_term_sentiment(df),
                "volume": self._get_volume_trend(df),
                "risk": self._get_risk_level(df)
            }
            
            return {
                "trend": trend["direction"],
                "strength": trend["strength"],
                "signals": signals,
                "sentiment": sentiment,
                "timestamp": pd.Timestamp.now()
            }
            
        except Exception as e:
            logger.error(f"기술적 분석 중 오류: {str(e)}")
            return None

    def _get_market_sentiment(self, df: pd.DataFrame) -> str:
        """전반적 시장 심리 판단"""
        latest = df.iloc[-1]
        if latest['rsi'] > 60 and latest['macd'] > 0:
            return "POSITIVE"
        elif latest['rsi'] < 40 and latest['macd'] < 0:
            return "NEGATIVE"
        return "NEUTRAL"

    def _get_short_term_sentiment(self, df: pd.DataFrame) -> str:
        """단기 시장 심리 판단"""
        latest = df.iloc[-1]
        if latest['macd'] > latest['macd_signal']:
            return "POSITIVE"
        elif latest['macd'] < latest['macd_signal']:
            return "NEGATIVE"
        return "NEUTRAL"

    def _get_volume_trend(self, df: pd.DataFrame) -> str:
        """거래량 추세 판단"""
        vol_ma = df['volume'].rolling(20).mean()
        if df['volume'].iloc[-1] > vol_ma.iloc[-1] * 1.5:
            return "VOLUME_INCREASE"
        elif df['volume'].iloc[-1] < vol_ma.iloc[-1] * 0.5:
            return "VOLUME_DECREASE"
        return "VOLUME_NEUTRAL"

    def _get_risk_level(self, df: pd.DataFrame) -> str:
        """리스크 레벨 판단"""
        latest = df.iloc[-1]
        if latest['rsi'] > 70 or latest['rsi'] < 30:
            return "HIGH"
        elif 40 <= latest['rsi'] <= 60:
            return "LOW"
        return "MEDIUM"