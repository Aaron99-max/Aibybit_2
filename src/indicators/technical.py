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
            # 볼린저 밴드 포지션 계산
            df['bb_position'] = np.where(df['close'] > df['bb_upper'], '상단',
                                       np.where(df['close'] < df['bb_lower'], '하단', '중단'))
            
            # 이동평균선 계산
            df['sma_10'] = df['close'].rolling(window=10).mean()
            df['sma_30'] = df['close'].rolling(window=30).mean()
            
            # ADX 계산
            adx_indicator = ADXIndicator(df['high'], df['low'], df['close'])
            df['adx'] = adx_indicator.adx()
            df['di_plus'] = adx_indicator.adx_pos()
            df['di_minus'] = adx_indicator.adx_neg()
            
            # 추세 판단
            df['trend'] = self._determine_trend(df)
            df['trend_strength'] = self._calculate_trend_strength(df)
            
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

    def _determine_trend(self, df: pd.DataFrame) -> str:
        """가격 추세 판단"""
        try:
            latest = df.iloc[-1]
            
            # 이동평균선 기반 추세 판단
            ma_trend = "상승" if latest['sma_10'] > latest['sma_30'] else "하락"
            
            # MACD 기반 추세 판단
            macd_trend = "상승" if latest['macd'] > latest['macd_signal'] else "하락"
            
            # ADX로 추세 강도 확인
            strong_trend = latest['adx'] > 25
            
            # 종합 판단
            if ma_trend == macd_trend:
                return ma_trend if strong_trend else f"약{ma_trend}"
            else:
                return "횡보"
                
        except Exception as e:
            logger.error(f"추세 판단 중 오류: {str(e)}")
            return "불명확"

    def _calculate_trend_strength(self, df: pd.DataFrame) -> float:
        """추세 강도 계산"""
        try:
            latest = df.iloc[-1]
            
            # ADX 기반 추세 강도 (0-100)
            adx_strength = float(latest['adx'])
            
            # MACD 기반 추세 강도 (MACD와 Signal의 차이)
            macd_strength = abs(latest['macd'] - latest['macd_signal']) / latest['close'] * 100
            
            # 이동평균선 기반 추세 강도
            ma_diff = abs(latest['sma_10'] - latest['sma_30']) / latest['close'] * 100
            
            # 가중치 적용
            strength = (
                (adx_strength * 0.4) +      # ADX: 40%
                (macd_strength * 0.35) +    # MACD: 35%
                (ma_diff * 0.25)            # MA: 25%
            )
            
            # 0-100 사이로 정규화
            return min(100, max(0, strength))
            
        except Exception as e:
            logger.error(f"추세 강도 계산 중 오류: {str(e)}")
            return 50.0