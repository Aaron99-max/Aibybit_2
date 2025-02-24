import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volume import VolumeWeightedAveragePrice, AccDistIndexIndicator
from ta.trend import MACD, ADXIndicator, IchimokuIndicator
from ta.volatility import BollingerBands
import logging
from typing import Optional, Dict
import traceback

logger = logging.getLogger(__name__)

class TechnicalIndicators:
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """기술적 지표 계산"""
        try:
            # data가 list인 경우 DataFrame으로 변환
            if isinstance(data, list):
                data = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                
            if data.empty:
                logger.error("데이터가 비어있습니다")
                return None
                
            # 지표 계산
            df = data.copy()
            
            # RSI 계산
            df['rsi'] = self.calculate_rsi(df['close'])
            
            # MACD 계산
            macd_data = self.calculate_macd(df['close'])
            df['macd'] = macd_data['macd']
            df['macd_signal'] = macd_data['signal']
            df['macd_hist'] = macd_data['histogram']
            
            # 볼린저 밴드 계산
            bb_data = self.calculate_bollinger_bands(df['close'])
            df['bb_upper'] = bb_data['upper']
            df['bb_middle'] = bb_data['middle'] 
            df['bb_lower'] = bb_data['lower']
            
            # 이동평균선
            df['sma_10'] = df['close'].rolling(window=10).mean()
            df['sma_30'] = df['close'].rolling(window=30).mean()
            
            # 추세 강도 계산 추가
            df['trend_strength'] = df.apply(lambda x: min(100, (
                (abs(x['sma_10'] - x['sma_30']) / x['close'] * 2000 * 0.4) +  # 이평선 차이
                (abs(x['macd']) / x['close'] * 5000 * 0.3) +                   # MACD 강도
                (abs(50 - x['rsi']) * 2 * 0.3)                                 # RSI 편차
            )), axis=1)
            
            # 결측값 처리
            df = df.fillna(method='ffill').fillna(method='bfill')
            
            return df
            
        except Exception as e:
            logger.error(f"지표 계산 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
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
            # (가격이 신고점이지만 RSI는 이전 고점보다 낮을 때)
            if (current_price >= price_high * 0.998 and  # 가격이 신고점 근처
                current_rsi < rsi_high * 0.95 and        # RSI는 이전 고점보다 낮음
                current_rsi < prev_rsi):                 # RSI 하락 중
                return {
                    "type": "베어리시",
                    "description": f"가격은 신고점({current_price:.0f}) 도달, RSI({current_rsi:.1f})는 이전 고점({rsi_high:.1f})보다 낮음"
                }
                
            # 불리시 다이버전스
            # (가격이 신저점이지만 RSI는 이전 저점보다 높을 때)
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

    def calculate_bollinger_bands(self, prices: pd.Series, period: int = 20, std: float = 2.0) -> Dict:
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