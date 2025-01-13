import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, Optional, List
import json
import time
import re
import traceback
from .gpt_client import GPTClient
from datetime import datetime
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
    # 시간대별 가중치
    TIMEFRAME_WEIGHTS = {
        '15m': 0.25,  # 25%
        '1h': 0.35,   # 35%
        '4h': 0.25,   # 25%
        '1d': 0.15    # 15%
    }
    
    def __init__(self, bybit_client=None, market_data_service=None):
        """초기화 메서드"""
        self.support_levels = []
        self.resistance_levels = []
        self.last_analysis = {}
        self.analysis_timeout = 60
        self.gpt_client = GPTClient()
        self.bybit_client = bybit_client
        self.market_data_service = market_data_service
        self.technical_indicators = TechnicalIndicators()
        self.storage_formatter = StorageFormatter()
        
        # 새로운 저장소 추가
        self.analysis_store = GPTAnalysisStore()
        self.trade_store = TradeStore()
        
        if bybit_client:
            self.market_data_service = MarketDataService(bybit_client)

    async def analyze_market(self, timeframe: str, data: pd.DataFrame) -> Dict:
        """시장 분석 수행"""
        try:
            # 1. 기존 분석 코드 유지
            df_with_indicators = self.technical_indicators.calculate_indicators(data)
            if df_with_indicators is None:
                logger.error("기술적 지표 계산 실패")
                return None
            
            # 2. 기술적 분석
            technical_analysis = {
                'trend': self._determine_trend(df_with_indicators),
                'strength': round(self._calculate_trend_strength(df_with_indicators), 2),
                'indicators': {
                    'rsi': round(float(df_with_indicators['rsi'].iloc[-1]), 2),
                    'macd': '상승' if df_with_indicators['macd'].iloc[-1] > 0 else '하락',
                    'bollinger': self._get_bollinger_position(df_with_indicators)
                }
            }
            
            # 3. GPT 분석 요청 및 응답 처리
            gpt_response = await self._request_gpt_analysis(technical_analysis)
            if not gpt_response:
                return None
            
            # 4. 최종 분석 결과 구성
            final_analysis = {
                **json.loads(gpt_response),
                'technical_analysis': technical_analysis,
                'timeframe': timeframe,
                'timestamp': int(time.time() * 1000),
                'saved_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S KST')
            }
            
            # 5. 분석 결과 저장
            self.analysis_store.save_analysis(final_analysis)
            
            return final_analysis
            
        except Exception as e:
            logger.error(f"시장 분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
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

    async def _request_gpt_analysis(self, technical_analysis: Dict) -> Optional[str]:
        """GPT API를 통한 시장 분석 요청"""
        try:
            # 분석 프롬프트 구성
            prompt = f"""
            다음 기술적 분석 데이터를 바탕으로 현재 시장 상황을 분석해주세요:
            
            추세: {technical_analysis['trend']}
            추세 강도: {technical_analysis['strength']}
            
            기술적 지표:
            - RSI: {technical_analysis['indicators']['rsi']}
            - MACD: {technical_analysis['indicators']['macd']}
            - 볼린저 밴드: {technical_analysis['indicators']['bollinger']}
            
            분석 결과를 다음 JSON 형식으로 반환해주세요:
            {{
                "market_condition": "강세/약세/중립",
                "trend_analysis": "상세 추세 분석",
                "risk_level": "상/중/하",
                "trading_suggestion": "매수/매도/관망 제안"
            }}
            """
            
            # GPT 응답 요청
            response = await self.gpt_client.get_analysis(prompt)
            if not response:
                return None
            
            return response
            
        except Exception as e:
            logger.error(f"GPT 분석 요청 중 오류: {str(e)}")
            return None

    async def analyze_final(self, analyses: Dict[str, Dict]) -> Optional[Dict]:
        """최종 분석 수행"""
        try:
            if not analyses:
                logger.error("분석할 데이터가 없습니다")
                return None
            
            # 각 시간대별 가중치 적용
            weighted_analysis = {
                'market_summary': self._combine_market_summaries(analyses),
                'technical_analysis': self._combine_technical_analyses(analyses),
                'trading_strategy': self._create_final_strategy(analyses),
                'timestamp': int(time.time() * 1000),
                'saved_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S KST')
            }
            
            return weighted_analysis
            
        except Exception as e:
            logger.error(f"최종 분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def _combine_market_summaries(self, analyses: Dict[str, Dict]) -> Dict:
        """시장 요약 통합"""
        try:
            combined = {
                'market_phase': self._get_weighted_market_phase(analyses),
                'overall_sentiment': self._get_weighted_sentiment(analyses),
                'short_term_sentiment': analyses.get('15m', {}).get('market_summary', {}).get('short_term_sentiment', '중립'),
                'volume_trend': self._get_weighted_volume_trend(analyses),
                'risk_level': self._calculate_risk_level(analyses),
                'confidence': self._calculate_confidence(analyses)
            }
            return combined
        except Exception as e:
            logger.error(f"시장 요약 통합 중 오류: {str(e)}")
            return {}

    def _combine_technical_analyses(self, analyses: Dict[str, Dict]) -> Dict:
        """기술적 분석 통합"""
        try:
            # 각 시간대별 기술적 지표 통합
            indicators = {}
            for timeframe, analysis in analyses.items():
                weight = self.TIMEFRAME_WEIGHTS.get(timeframe, 0)
                tech = analysis.get('technical_analysis', {})
                
                for key, value in tech.get('indicators', {}).items():
                    if key not in indicators:
                        indicators[key] = 0
                    indicators[key] += float(value) * weight if isinstance(value, (int, float)) else 0
            
            return {
                'trend': self._get_weighted_trend(analyses),
                'strength': self._calculate_trend_strength(analyses),
                'indicators': indicators
            }
        except Exception as e:
            logger.error(f"기술적 분석 통합 중 오류: {str(e)}")
            return {}

    def _create_final_strategy(self, analyses: Dict[str, Dict]) -> Dict:
        """최종 거래 전략 생성"""
        try:
            return {
                'position_suggestion': self._determine_final_position(analyses),
                'entry_points': self._calculate_entry_points(analyses),
                'stopLoss': self._calculate_stop_loss(analyses),
                'takeProfit': self._calculate_take_profits(analyses),
                'leverage': self._determine_leverage(analyses),
                'position_size': self._determine_position_size(analyses),
                'auto_trading': {
                    'enabled': self._should_enable_auto_trading(analyses),
                    'reason': self._get_auto_trading_reason(analyses)
                }
            }
        except Exception as e:
            logger.error(f"거래 전략 생성 중 오류: {str(e)}")
            return {}

    def _get_weighted_market_phase(self, analyses: Dict[str, Dict]) -> str:
        """가중치가 적용된 시장 단계 결정"""
        try:
            phases = {'상승': 0, '하락': 0, '횡보': 0}
            for timeframe, analysis in analyses.items():
                weight = self.TIMEFRAME_WEIGHTS.get(timeframe, 0)
                phase = analysis.get('market_summary', {}).get('market_phase', '횡보')
                phases[phase] = phases.get(phase, 0) + weight
            
            return max(phases.items(), key=lambda x: x[1])[0]
        except Exception as e:
            logger.error(f"시장 단계 결정 중 오류: {str(e)}")
            return '횡보'

    def _get_weighted_sentiment(self, analyses: Dict[str, Dict]) -> str:
        """가중치가 적용된 시장 심리 결정"""
        try:
            sentiments = {'긍정': 0, '부정': 0, '중립': 0}
            for timeframe, analysis in analyses.items():
                weight = self.TIMEFRAME_WEIGHTS.get(timeframe, 0)
                sentiment = analysis.get('market_summary', {}).get('overall_sentiment', '중립')
                sentiments[sentiment] = sentiments.get(sentiment, 0) + weight
            
            return max(sentiments.items(), key=lambda x: x[1])[0]
        except Exception as e:
            logger.error(f"시장 심리 결정 중 오류: {str(e)}")
            return '중립'

    def _get_weighted_volume_trend(self, analyses: Dict[str, Dict]) -> str:
        """가중치가 적용된 거래량 추세 결정"""
        try:
            trends = {'증가': 0, '감소': 0, '보통': 0}
            for timeframe, analysis in analyses.items():
                weight = self.TIMEFRAME_WEIGHTS.get(timeframe, 0)
                trend = analysis.get('market_summary', {}).get('volume_trend', '보통')
                trends[trend] = trends.get(trend, 0) + weight
            
            return max(trends.items(), key=lambda x: x[1])[0]
        except Exception as e:
            logger.error(f"거래량 추세 결정 중 오류: {str(e)}")
            return '보통'

    def _calculate_risk_level(self, analyses: Dict[str, Dict]) -> str:
        """리스크 레벨 계산"""
        try:
            # 각 시간대별 리스크 점수 계산
            risk_score = 0
            total_weight = 0
            
            for timeframe, analysis in analyses.items():
                weight = self.TIMEFRAME_WEIGHTS.get(timeframe, 0)
                market = analysis.get('market_summary', {})
                tech = analysis.get('technical_analysis', {})
                
                # 변동성이 높거나 추세가 강할 때 리스크 증가
                if tech.get('strength', 0) > 70:
                    risk_score += weight * 1
                
                # 거래량이 급증할 때 리스크 증가
                if market.get('volume_trend', '') == '증가':
                    risk_score += weight * 0.5
                    
                total_weight += weight
            
            risk_ratio = risk_score / total_weight if total_weight > 0 else 0
            
            if risk_ratio > 0.7:
                return "높음"
            elif risk_ratio > 0.3:
                return "중간"
            else:
                return "낮음"
            
        except Exception as e:
            logger.error(f"리스크 레벨 계산 중 오류: {str(e)}")
            return "중간"

    def _calculate_confidence(self, analyses: Dict[str, Dict]) -> float:
        """신뢰도 계산"""
        try:
            total_confidence = 0
            total_weight = 0
            
            for timeframe, analysis in analyses.items():
                weight = self.TIMEFRAME_WEIGHTS.get(timeframe, 0)
                confidence = analysis.get('market_summary', {}).get('confidence', 50)
                
                total_confidence += confidence * weight
                total_weight += weight
                
            return round(total_confidence / total_weight if total_weight > 0 else 50)
            
        except Exception as e:
            logger.error(f"신뢰도 계산 중 오류: {str(e)}")
            return 50

    def _get_weighted_trend(self, analyses: Dict[str, Dict]) -> str:
        """가중치가 적용된 추세 결정"""
        try:
            trends = {'상승': 0, '하락': 0, '횡보': 0}
            for timeframe, analysis in analyses.items():
                weight = self.TIMEFRAME_WEIGHTS.get(timeframe, 0)
                trend = analysis.get('technical_analysis', {}).get('trend', '횡보')
                trends[trend] = trends.get(trend, 0) + weight
                
            return max(trends.items(), key=lambda x: x[1])[0]
            
        except Exception as e:
            logger.error(f"추세 결정 중 오류: {str(e)}")
            return '횡보'