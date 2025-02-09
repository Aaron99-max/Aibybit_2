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
            
            # GPT 분석 요청
            gpt_response = await self._request_gpt_analysis(market_data, df_with_indicators)
            if not gpt_response:
                return None
            
            # 분석 결과 저장
            self.analysis_store.save_analysis(gpt_response)
            
            return gpt_response
            
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

    async def _request_gpt_analysis(self, market_data: Dict, technical_analysis: Dict) -> Optional[str]:
        """GPT API를 통한 시장 분석 요청"""
        try:
            # 프롬프트 템플릿에 데이터 적용
            prompt = self.gpt_client.ANALYSIS_PROMPT_TEMPLATE.format(
                current_price=market_data.get('price_data', {}).get('last_price', 0),
                rsi=technical_analysis.get('indicators', {}).get('rsi', 0),
                macd=technical_analysis.get('indicators', {}).get('macd', '알 수 없음'),
                bollinger=technical_analysis.get('indicators', {}).get('bollinger', '알 수 없음'),
                trend=technical_analysis.get('trend', '알 수 없음'),
                trend_strength=technical_analysis.get('strength', 0),
                price_change=market_data.get('price_data', {}).get('price_change_24h', 0),
                volume=market_data.get('price_data', {}).get('volume', 0),
                funding_rate=market_data.get('market_metrics', {}).get('funding_rate', 0)
            )
            
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