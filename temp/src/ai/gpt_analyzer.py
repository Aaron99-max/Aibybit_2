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
            
            # 기술적 분석 수행
            technical_analysis = {
                'trend': self._determine_trend(df_with_indicators),
                'strength': round(self._calculate_trend_strength(df_with_indicators), 2),
                'indicators': {
                    'rsi': round(float(df_with_indicators['rsi'].iloc[-1]), 2),
                    'macd': self._get_macd_signal(df_with_indicators),
                    'bollinger': self._get_bollinger_position(df_with_indicators),
                    'volatility': self._calculate_volatility(df_with_indicators)
                }
            }
            
            # GPT 분석 요청
            gpt_response = await self._request_gpt_analysis(market_data, technical_analysis)
            if not gpt_response:
                return None
            
            # 응답 검증 및 정규화
            try:
                analysis_result = json.loads(gpt_response)
                validated_result = self._validate_analysis_result(analysis_result)
            except json.JSONDecodeError:
                logger.error("GPT 응답을 JSON으로 파싱할 수 없습니다")
                return None
            
            # 최종 분석 결과 구성
            final_analysis = {
                **validated_result,
                'technical_analysis': technical_analysis,
                'market_data': market_data,
                'timeframe': timeframe,
                'timestamp': int(time.time() * 1000),
                'saved_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S KST')
            }
            
            # 분석 결과 저장
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

    async def _request_gpt_analysis(self, market_data: Dict, technical_analysis: Dict) -> Optional[str]:
        """GPT API를 통한 시장 분석 요청"""
        try:
            # 프롬프트 템플릿 개선
            prompt = f"""
            다음 비트코인 시장 데이터를 바탕으로 명확한 매매 전략을 제시해주세요.
            응답은 반드시 아래 JSON 형식을 정확히 따라야 합니다.

            [시장 현황]
            • 현재가: ${market_data.get('price_data', {}).get('last_price', 0):,.2f}
            • 24시간 변동: {market_data.get('price_data', {}).get('price_change_24h', 0):+.2f}%
            • 거래량(24h): {market_data.get('price_data', {}).get('volume', 0):,.0f}
            • 자금조달비율: {market_data.get('market_metrics', {}).get('funding_rate', 0):.4f}%
            
            [시장 지표]
            • 미체결약정: {market_data.get('market_metrics', {}).get('open_interest', {}).get('value', 0):,.0f} 
            • 24h 변화: {market_data.get('market_metrics', {}).get('open_interest', {}).get('change_24h', 0):+.2f}%
            • 매수/매도 비율: {market_data.get('order_book', {}).get('bid_volume', 0) / market_data.get('order_book', {}).get('ask_volume', 1):.2f}
            
            [기술적 분석]
            • 주요 추세: {technical_analysis.get('trend', '알 수 없음')} (강도: {technical_analysis.get('strength', 0)}/100)
            • RSI: {technical_analysis.get('indicators', {}).get('rsi', 0):.1f}
            • MACD: {technical_analysis.get('indicators', {}).get('macd', '알 수 없음')}
            • 볼린저밴드: {technical_analysis.get('indicators', {}).get('bollinger', '알 수 없음')}

            반드시 다음 JSON 형식으로만 응답하세요:
            {{
                "market_summary": {{
                    "market_phase": "상승" 또는 "하락" 또는 "횡보",
                    "overall_sentiment": "긍정" 또는 "부정" 또는 "중립",
                    "short_term_sentiment": "강한매수" 또는 "매수" 또는 "중립" 또는 "매도" 또는 "강한매도",
                    "volume_trend": "증가" 또는 "감소" 또는 "보통",
                    "key_levels": {{
                        "support": [숫자1, 숫자2],
                        "resistance": [숫자1, 숫자2]
                    }},
                    "confidence": 0에서 100 사이의 숫자
                }},
                "trading_strategy": {{
                    "position": "매수" 또는 "매도" 또는 "관망",
                    "entry_points": [숫자1, 숫자2],
                    "stop_loss": 숫자,
                    "take_profits": [숫자1, 숫자2],
                    "risk_reward_ratio": 숫자,
                    "recommended_leverage": 1에서 10 사이의 숫자,
                    "position_size": "전체자금의 숫자%",
                    "key_risks": ["위험요소1", "위험요소2"]
                }},
                "analysis_details": {{
                    "technical_signals": ["신호1", "신호2"],
                    "market_drivers": ["요인1", "요인2"],
                    "key_events": ["이벤트1", "이벤트2"]
                }}
            }}
            """
            
            response = await self.gpt_client.get_analysis(prompt)
            if not response:
                logger.error("GPT 응답이 비어있습니다")
                return None
            
            # JSON 파싱 검증
            try:
                parsed_response = json.loads(response)
                # 필수 필드 검증
                required_fields = {
                    'market_summary': ['market_phase', 'overall_sentiment', 'short_term_sentiment'],
                    'trading_strategy': ['position', 'entry_points', 'stop_loss', 'take_profits'],
                    'analysis_details': ['technical_signals', 'market_drivers']
                }
                
                for section, fields in required_fields.items():
                    if section not in parsed_response:
                        raise ValueError(f"필수 섹션 누락: {section}")
                    for field in fields:
                        if field not in parsed_response[section]:
                            raise ValueError(f"필수 필드 누락: {section}.{field}")
                            
                return response
                
            except json.JSONDecodeError:
                logger.error("GPT 응답이 올바른 JSON 형식이 아닙니다")
                return None
            except ValueError as e:
                logger.error(f"GPT 응답 검증 실패: {str(e)}")
                return None
                
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

    def _validate_analysis_result(self, result: Dict) -> Dict:
        """분석 결과 검증 및 정규화"""
        try:
            required_fields = {
                'market_summary': ['market_phase', 'overall_sentiment', 'short_term_sentiment'],
                'trading_strategy': ['position', 'entry_points', 'stop_loss', 'take_profits']
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