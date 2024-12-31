import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volume import VolumeWeightedAveragePrice, AccDistIndexIndicator
from ta.trend import MACD, ADXIndicator, IchimokuIndicator
from ta.volatility import BollingerBands
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class TechnicalIndicators:
    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """기술적 지표 계산"""
        try:
            if df is None or df.empty:
                logger.error("입력 데이터가 비어있습니다")
                return None
                
            # 볼린저 밴드 추가
            bb = BollingerBands(df['close'])
            df['bb_upper'] = bb.bollinger_hband()
            df['bb_middle'] = bb.bollinger_mavg()
            df['bb_lower'] = bb.bollinger_lband()
            
            # ADX 추가 (추세 강도)
            adx = ADXIndicator(df['high'], df['low'], df['close'])
            df['adx'] = adx.adx()
            df['di_plus'] = adx.adx_pos()
            df['di_minus'] = adx.adx_neg()
            
            # 이동평균선 추가
            df['sma_20'] = df['close'].rolling(window=20).mean()
            df['sma_50'] = df['close'].rolling(window=50).mean()
            df['ema_9'] = df['close'].ewm(span=9).mean()
            
            # RSI 계산
            rsi = RSIIndicator(close=df['close'], window=14)
            df['rsi'] = rsi.rsi()
            
            # MACD 계산
            exp1 = df['close'].ewm(span=12, adjust=False).mean()
            exp2 = df['close'].ewm(span=26, adjust=False).mean()
            df['macd'] = exp1 - exp2
            df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
            df['macd_diff'] = df['macd'] - df['macd_signal']  # MACD 히스토แกรม
            
            # VWAP 계산
            df['vwap'] = (df['volume'] * (df['high'] + df['low'] + df['close']) / 3).cumsum() / df['volume'].cumsum()
            
            # 결측값 처리
            df = df.fillna(0)
            
            # 거래량 지표 추가
            df['volume_sma'] = df['volume'].rolling(window=20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_sma']
            
            return df
            
        except Exception as e:
            logger.error(f"지표 계산 중 에러: {str(e)}")
            return None

    @staticmethod
    def check_rsi_divergence(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
        """RSI 다이버전스 확인"""
        try:
            if 'rsi' not in df.columns:
                logger.error("RSI가 계산되지 않았습니다")
                return None
                
            df['price_high'] = df['close'].rolling(window=window).apply(
                lambda x: 1 if x.iloc[-1] == max(x) else 0
            )
            df['price_low'] = df['close'].rolling(window=window).apply(
                lambda x: 1 if x.iloc[-1] == min(x) else 0
            )
            
            df['rsi_high'] = df['rsi'].rolling(window=window).apply(
                lambda x: 1 if x.iloc[-1] == max(x) else 0
            )
            df['rsi_low'] = df['rsi'].rolling(window=window).apply(
                lambda x: 1 if x.iloc[-1] == min(x) else 0
            )
            
            # 베어리시 다이버전스 (가격은 고점, RSI는 저점)
            df['bearish_divergence'] = (df['price_high'] == 1) & (df['rsi_low'] == 1)
            
            # 불리시 다이버전스 (가격은 저점, RSI는 고점)
            df['bullish_divergence'] = (df['price_low'] == 1) & (df['rsi_high'] == 1)
            
            # NaN 값을 False로 채우기
            df['bearish_divergence'] = df['bearish_divergence'].fillna(False)
            df['bullish_divergence'] = df['bullish_divergence'].fillna(False)
            
            return df
            
        except Exception as e:
            logger.error(f"다이버전스 확인 중 에러 발생: {str(e)}")
            return None

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