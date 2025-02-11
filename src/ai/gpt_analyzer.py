import numpy as np
import pandas as pd
import logging
from typing import Dict, Any, Optional, List, Tuple
import json
import time
from datetime import datetime
import traceback
from .gpt_client import GPTClient
from collections import Counter
from services.market_data_service import MarketDataService
from indicators.technical import TechnicalIndicators
from telegram_bot.formatters.storage_formatter import StorageFormatter
from config.trading_config import trading_config
from pathlib import Path
from services.trade_store import TradeStore
from .gpt_analysis_store import GPTAnalysisStore

# numpy 경고 무시 설정
np.seterr(divide='ignore', invalid='ignore')

logger = logging.getLogger(__name__)

class GPTAnalyzer:
    def __init__(self, bybit_client=None, market_data_service=None):
        """초기화 메서드"""
        self.support_levels = []
        self.resistance_levels = []
        self.analysis_timeout = 60
        self.gpt_client = GPTClient()
        self.bybit_client = bybit_client
        self.market_data_service = market_data_service
        self.technical_indicators = TechnicalIndicators()
        self.storage_formatter = StorageFormatter()
        
        # 새로운 저장소 추가
        self.analysis_store = GPTAnalysisStore()

        if bybit_client:
            self.market_data_service = MarketDataService(bybit_client)

    async def analyze_market(self, timeframe: str, data: pd.DataFrame) -> Dict:
        """시장 분석 수행"""
        try:
            # 기술적 지표 계산
            df_with_indicators = self.technical_indicators.calculate_indicators(data)
            if df_with_indicators is None:
                logger.error("기술적 지표 계산 실패")
                return None
            
            # 시장 데이터 조회
            market_data = await self.market_data_service.get_market_data('BTCUSDT')
            if not market_data:
                logger.error("시장 데이터 조회 실패")
                return None
            
            # 디버깅을 위한 로그 추가
            logger.info(f"계산된 지표: {df_with_indicators.columns.tolist()}")
            logger.info(f"시장 데이터: {market_data}")
            
            # 기술적 지표 분석
            latest = df_with_indicators.iloc[-1]
            trend = self._determine_trend(df_with_indicators)
            trend_strength = self._calculate_trend_strength(df_with_indicators)
            bb_position = self._get_bollinger_position(df_with_indicators)
            
            # RSI 다이버전스 체크
            divergence = self.technical_indicators.check_rsi_divergence(df_with_indicators)
            
            # GPT에 전달할 데이터 구성
            analysis_data = {
                'market_data': market_data,
                'indicators': {
                    'rsi': float(latest['rsi']),
                    'macd': float(latest['macd']),
                    'macd_signal': float(latest['macd_signal']),
                    'bb_position': bb_position,
                    'trend': trend,
                    'trend_strength': trend_strength
                }
            }
            
            # GPT 프롬프트 생성 후 분석 요청
            prompt = self._create_analysis_prompt(df_with_indicators, analysis_data['indicators'], timeframe)
            trading_signal = await self._request_gpt_analysis(prompt)
            
            # trading_signal이 문자열인 경우 파싱
            if isinstance(trading_signal, str):
                try:
                    trading_signal = json.loads(trading_signal)
                except:
                    logger.error("GPT 응답 파싱 실패")
                    return None
            
            # 필수 필드 검증 및 안전한 형변환
            try:
                analysis_dict = {
                    'market_summary': {
                        'current_price': market_data.get('last_price', 0),
                        'market_phase': trend,
                        'sentiment': self._get_market_sentiment(df_with_indicators),
                        'short_term': self._get_short_term_sentiment(df_with_indicators),
                        'volume': self._get_volume_trend(df_with_indicators),
                        'risk': self._get_risk_level(df_with_indicators),
                        'confidence': trading_signal.get('confidence', 70)
                    },
                    'technical_analysis': {
                        'trend': trend,
                        'strength': trend_strength,
                        'indicators': {
                            'rsi': float(latest['rsi']),
                            'macd': 'BULLISH' if latest['macd'] > latest['macd_signal'] else 'BEARISH',
                            'bollinger': bb_position,
                            'divergence_type': latest['divergence_type'],
                            'divergence_desc': latest['divergence_desc']
                        }
                    },
                    'trading_strategy': {
                        'position': trading_signal.get('position', 'HOLD'),
                        'entry_price': float(str(trading_signal.get('entry_price') or 0).replace('$', '').replace(',', '')),
                        'stop_loss': float(str(trading_signal.get('stop_loss') or 0).replace('$', '').replace(',', '')),
                        'take_profit1': float(str(trading_signal.get('take_profit1') or 0).replace('$', '').replace(',', '')),
                        'take_profit2': float(str(trading_signal.get('take_profit2') or 0).replace('$', '').replace(',', '')),
                        'leverage': int(trading_signal.get('leverage', 1)),
                        'size': int(trading_signal.get('size', 10)),
                        'reason': trading_signal.get('reason', '분석 중')
                    },
                    'auto_trading': {
                        'enabled': timeframe == '1h',
                        'status': 'active' if timeframe == '1h' else 'disabled'
                    },
                    'timestamp': int(datetime.now().timestamp() * 1000)
                }
            except (ValueError, TypeError) as e:
                logger.error(f"데이터 변환 중 오류: {str(e)}")
                return None
            
            # 분석 결과 저장
            self.analysis_store.save_analysis(analysis_dict)
            return analysis_dict
            
        except Exception as e:
            logger.error(f"시장 분석 중 오류: {str(e)}")
            return None

    def _determine_trend(self, df: pd.DataFrame) -> str:
        """가격 추세 판단"""
        try:
            # TechnicalIndicators의 결과 사용
            indicators = self.technical_indicators.calculate_indicators(df)
            if indicators is None:
                return "알 수 없음"
            
            # 이미 계산된 지표 활용
            trend = "상승" if (
                indicators['sma_10'].iloc[-1] > indicators['sma_30'].iloc[-1] and 
                indicators['rsi'].iloc[-1] > 50 and 
                indicators['macd'].iloc[-1] > 0
            ) else "하락" if (
                indicators['sma_10'].iloc[-1] < indicators['sma_30'].iloc[-1] and 
                indicators['rsi'].iloc[-1] < 50 and 
                indicators['macd'].iloc[-1] < 0
            ) else "횡보"
            
            return trend
            
        except Exception as e:
            logger.error(f"추세 판단 중 오류: {str(e)}")
            return "알 수 없음"

    def _calculate_trend_strength(self, df: pd.DataFrame) -> float:
        """추세 강도 계산"""
        try:
            # TechnicalIndicators의 결과 사용
            indicators = self.technical_indicators.calculate_indicators(df)
            if indicators is None:
                return 50.0
            
            return float(indicators['trend_strength'].iloc[-1])
            
        except Exception as e:
            logger.error(f"추세 강도 계산 중 오류: {str(e)}")
            return 50.0

    def _get_bollinger_position(self, df: pd.DataFrame) -> str:
        """볼린저 밴드 기준 포지션"""
        try:
            # TechnicalIndicators의 결과 사용
            indicators = self.technical_indicators.calculate_indicators(df)
            if indicators is None:
                return "알 수 없음"
            
            current_price = indicators['close'].iloc[-1]
            upper = indicators['bb_upper'].iloc[-1]
            lower = indicators['bb_lower'].iloc[-1]
            
            if current_price > upper:
                return "과매수"
            elif current_price < lower:
                return "과매도"
            else:
                return "중립"
            
        except Exception as e:
            logger.error(f"볼린저 밴드 위치 확인 중 오류: {str(e)}")
            return "알 수 없음"

    async def _request_gpt_analysis(self, prompt: str) -> Optional[Dict]:
        """GPT API를 통한 시장 분석 요청"""
        try:
            return await self.gpt_client.get_analysis(prompt)
            
        except Exception as e:
            logger.error(f"GPT 분석 요청 중 오류: {str(e)}")
            return None

    def _validate_analysis_result(self, result: Dict) -> Dict:
        """분석 결과 검증 및 정규화"""
        try:
            required_fields = {
                'position': ['position'],
                'entry_price': ['entry_price'],
                'stop_loss': ['stop_loss'],
                'take_profit': ['take_profit'],
                'leverage': ['leverage'],
                'confidence': ['confidence'],
                'reason': ['reason']
            }
            
            for section, fields in required_fields.items():
                if section not in result:
                    raise ValueError(f"필수 섹션 누락: {section}")
                    
                for field in fields:
                    if field not in result[section]:
                        raise ValueError(f"필수 필드 누락: {section}.{field}")
                    
            return result
            
        except Exception as e:
            logger.error(f"분석 결과 검증 중 오류: {str(e)}")
            return {}

    def _get_macd_signal(self, df: pd.DataFrame) -> str:
        """MACD 신호 판단"""
        try:
            if df is None or 'macd' not in df.columns:
                return "알 수 없음"
            
            macd = df['macd'].iloc[-1]
            signal = df['macd_signal'].iloc[-1]
            
            if macd > signal:
                return "상승"
            elif macd < signal:
                return "하락"
            else:
                return "중립"
            
        except Exception as e:
            logger.error(f"MACD 신호 판단 중 오류: {str(e)}")
            return "알 수 없음"

    def _calculate_volatility(self, df: pd.DataFrame) -> float:
        """변동성 계산"""
        try:
            if df is None or len(df) < 2:
                return 0.0
            
            # 20일 기준 변동성 계산
            returns = np.log(df['close'] / df['close'].shift(1))
            volatility = returns.std() * np.sqrt(365) * 100  # 연간 변동성으로 변환
            
            return round(float(volatility), 2)
            
        except Exception as e:
            logger.error(f"변동성 계산 중 오류: {str(e)}")
            return 0.0

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

    def _create_analysis_prompt(self, df: pd.DataFrame, indicators: Dict, timeframe: str) -> str:
        """분석 프롬프트 생성"""
        try:
            # 템플릿에 데이터 적용
            prompt = self.gpt_client.ANALYSIS_PROMPT_TEMPLATE.format(
                current_price=df['close'].iloc[-1],
                rsi=indicators['rsi'],
                macd=indicators['macd'],
                macd_signal=indicators['macd_signal'],
                bollinger=indicators['bb_position'],
                trend=indicators['trend'],
                trend_strength=indicators['trend_strength'],
                price_change=df['price_change_24h'].iloc[-1],
                volume=df['volume'].iloc[-1],
                volume_change=df['volume_change_24h'].iloc[-1],
                funding_rate=0.01  # 기본값 설정
            )
            return prompt
        except Exception as e:
            logger.error(f"프롬프트 생성 중 오류: {str(e)}")
            return None