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
        self.analysis_timeout = 60  # 1분 타임아웃
        self.gpt_client = GPTClient()
        self.bybit_client = bybit_client
        self.market_data_service = market_data_service  # market_data_service 직접 저장
        self.technical_indicators = TechnicalIndicators()  # 추가
        self.storage_formatter = StorageFormatter()  # 이 한 줄만 추가
        
        if bybit_client:  # bybit_client가 있을 때만 초기화
            self.market_data_service = MarketDataService(bybit_client)

    def _calculate_price_levels(self, df: pd.DataFrame) -> None:
        """지지/저항 레벨 계산"""
        high = df['high'].iloc[-20:].max()  # 최근 20개 봉 기준
        low = df['low'].iloc[-20:].min()
        close = df['close'].iloc[-1]
        
        # 피봇 포인트 계산
        pivot = (high + low + close) / 3
        range_multiplier = 0.02  # 2% 범위
        
        self.resistance_levels = [
            close * (1 + range_multiplier),  # R1
            close * (1 + range_multiplier * 2)  # R2
        ]
        self.support_levels = [
            close * (1 - range_multiplier),  # S1
            close * (1 - range_multiplier * 2)  # S2
        ]

    def _analyze_trend(self, df: pd.DataFrame) -> Dict[str, Any]:
        """추세 분석"""
        try:
            latest = df.iloc[-1]
            prev_day = df.iloc[-24]  # 24시간 전
            
            # 추세 방향과 강도 계산
            price_change = (latest['close'] - prev_day['close']) / prev_day['close'] * 100
            trend_direction = "BULLISH" if price_change > 0 else "BEARISH"
            trend_strength = abs(price_change)
            
            # 거래량 트렌드
            volume_sma = df['volume'].rolling(window=24).mean()
            volume_trend = "VOLUME_INCREASE" if latest['volume'] > volume_sma.iloc[-1] else "VOLUME_DECREASE"
            
            return {
                "trend": trend_direction,
                "strength": round(trend_strength, 1),
                "price_change": price_change,
                "volume_trend": volume_trend
            }
        except Exception as e:
            logger.error(f"추세 분석 중 오류: {str(e)}")
            return {
                "trend": "NEUTRAL",
                "strength": 0.0,
                "price_change": 0.0,
                "volume_trend": "NEUTRAL"
            }

    def _calculate_technical_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """기술적 지표 계산"""
        try:
            # RSI 계산 (14일 기준)
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rs = rs.replace([np.inf, -np.inf], np.nan).fillna(0)  # 0으로 나누기 방지
            rsi = 100 - (100 / (1 + rs))
            rsi = rsi.fillna(50)  # NaN 값을 중립값으로 대체
            
            # MACD 계산 (12, 26, 9)
            exp1 = df['close'].ewm(span=12, adjust=False).mean()
            exp2 = df['close'].ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()
            
            # 볼린저 밴드 (20일, 2표준편차)
            ma20 = df['close'].rolling(window=20).mean()
            std20 = df['close'].rolling(window=20).std()
            upper_band = ma20 + (std20 * 2)
            lower_band = ma20 - (std20 * 2)
            
            latest_close = df['close'].iloc[-1]
            
            return {
                'rsi': round(rsi.iloc[-1], 2),
                'macd': {
                    'macd': round(macd.iloc[-1], 2),
                    'signal': round(signal.iloc[-1], 2),
                    'histogram': round(macd.iloc[-1] - signal.iloc[-1], 2)
                },
                'bollinger_bands': {
                    'upper': round(upper_band.iloc[-1], 2),
                    'middle': round(ma20.iloc[-1], 2),
                    'lower': round(lower_band.iloc[-1], 2),
                    'position': 'upper' if latest_close > upper_band.iloc[-1] else 
                               'lower' if latest_close < lower_band.iloc[-1] else 'middle'
                }
            }
            
        except Exception as e:
            logger.error(f"기술적 지표 계산 중 오류: {str(e)}")
            return {
                'rsi': 50.0,
                'macd': {
                    'macd': 0.0,
                    'signal': 0.0,
                    'histogram': 0.0
                },
                'bollinger_bands': {
                    'upper': 0.0,
                    'middle': 0.0,
                    'lower': 0.0,
                    'position': 'middle'
                }
            }

    async def analyze(self, klines: List, timeframe: str) -> Dict:
        """GPT 분석 실행"""
        try:
            # OHLCV 데이터를 DataFrame으로 변환
            df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # 기술적 지표 계산 (technical.py에서 수행)
            df_with_indicators = self.technical_indicators.calculate_indicators(df)
            if df_with_indicators is None:
                logger.error("기술적 지표 계산 실패")
                return None
            
            # 다이버전스 분석 (이미 있는 _analyze_divergence 메서드 사용)
            divergence = self._analyze_divergence(df_with_indicators)
            
            # 기술적 분석 결과 생성
            technical_analysis = {
                'trend': self._determine_trend(df_with_indicators),
                'strength': round(self._calculate_trend_strength(df_with_indicators), 2),
                'indicators': {
                    'rsi': round(float(df_with_indicators['rsi'].iloc[-1]), 2),
                    'macd': '상승' if df_with_indicators['macd'].iloc[-1] > 0 else '하락',
                    'bollinger': self._get_bollinger_position(df_with_indicators),
                    'divergence': {
                        **self.technical_indicators.check_rsi_divergence(df_with_indicators),
                        'timeframe': timeframe  # 현재 분석 중인 timeframe 추가
                    }
                }
            }
            
            # GPT 프롬프트 생성
            prompt = self._create_analysis_prompt(df_with_indicators, technical_analysis, timeframe)
            
            # GPT API 호출
            response = await self.gpt_client.call_gpt_api(prompt)
            
            if response:
                # 기술적 분석 결과 추가
                if 'technical_analysis' not in response:
                    response['technical_analysis'] = {}
                response['technical_analysis'].update(technical_analysis)
                
            return response
            
        except Exception as e:
            logger.error(f"분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def _analyze_divergence(self, indicators: Dict) -> Dict:
        """다이버전스 분석"""
        try:
            rsi = indicators.get('rsi', 50)
            macd = indicators.get('macd', {}).get('macd', 0)
            signal = indicators.get('macd', {}).get('signal', 0)
            price_trend = 'neutral'
            
            # MACD 기반 추세 판단
            if macd > signal:
                price_trend = '상승'
            elif macd < signal:
                price_trend = '하락'
            
            divergence_type = '없음'
            description = ''
            
            # RSI 다이버전스 분석
            if price_trend == '상승' and rsi < 40:
                divergence_type = '베어리시'
                description = f'가격은 상승하나 RSI({rsi})가 약세를 보이는 베어리시 다이버전스'
            elif price_trend == '하락' and rsi > 60:
                divergence_type = '불리시'
                description = f'가격은 하락하나 RSI({rsi})가 강세를 보이는 불리시 다이버전스'
            
            if divergence_type == '없음':
                description = "현재 유의미한 다이버전스가 관찰되지 않음"
            
            return {
                'type': divergence_type,
                'description': description
            }
            
        except Exception as e:
            logger.error(f"다이버전스 분석 중 오류: {str(e)}")
            return {
                'type': '없음',
                'description': '분석 중 오류 발생'
            }

    def _validate_market_summary(self, market_summary: Dict, template_market_summary: Dict) -> bool:
        """시장 요약 검증"""
        try:
            required_fields = template_market_summary.keys()
            return all(key in market_summary for key in required_fields)
        except Exception as e:
            logger.error(f"시장 요약 검증 중 오류: {str(e)}")
            return False

    def _validate_technical_analysis(self, technical_analysis: Dict, template_technical: Dict) -> bool:
        """기술적 분석 검증"""
        try:
            required_fields = template_technical.keys()
            return all(key in technical_analysis for key in required_fields)
        except Exception as e:
            logger.error(f"기술적 분석 검증 중 오류: {str(e)}")
            return False

    def _validate_trading_strategy(self, trading_strategy: Dict, template_strategy: Dict) -> bool:
        """거래 전략 검증"""
        try:
            required_fields = template_strategy.keys()
            return all(key in trading_strategy for key in required_fields)
        except Exception as e:
            logger.error(f"거래 전략 검증 중 오류: {str(e)}")
            return False

    def validate_response(self, response: Dict) -> bool:
        """GPT 응답이 올바른 형식인지 검증"""
        try:
            # 필수 섹션 검사
            required_sections = ['market_summary', 'technical_analysis', 'trading_strategy']
            if not all(section in response for section in required_sections):
                logger.error(f"필수 섹션 누락: {[s for s in required_sections if s not in response]}")
                return False
            
            # market_summary 검증
            market_summary = response['market_summary']
            valid_market_phases = ["상승", "하락", "횡보", "분석 실패"]  # "분석 실패" 추가
            valid_sentiments = ["긍정적", "부정적", "중립"]
            valid_volume_trends = ["증가", "감소", "중립"]
            valid_risk_levels = ["높음", "중간", "낮음"]
            
            if market_summary['market_phase'] not in valid_market_phases:
                logger.error(f"잘못된 market_phase: {market_summary['market_phase']}")
                return False
            
            if market_summary['overall_sentiment'] not in valid_sentiments:
                logger.error(f"잘못된 overall_sentiment: {market_summary['overall_sentiment']}")
                return False
            
            # technical_analysis 검증
            tech_analysis = response['technical_analysis']
            if tech_analysis['trend'] not in valid_market_phases:  # 동일한 valid_market_phases 사용
                logger.error(f"잘못된 trend: {tech_analysis['trend']}")
                return False
            
            # trading_strategy 검증
            trading_strategy = response['trading_strategy']
            valid_positions = ["매수", "매도", "관망"]
            if trading_strategy['position'] not in valid_positions:
                logger.error(f"잘못된 position: {trading_strategy['position']}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"응답 검증 중 오류: {str(e)}")
            return False

    def _validate_market_values(self, market_summary: Dict, template: Dict) -> bool:
        """market_summary 값 검증"""
        try:
            if market_summary['market_phase'] not in template['market_phase']:
                return False
            if market_summary['overall_sentiment'] not in template['overall_sentiment']:
                return False
            if market_summary['risk_level'] not in template['risk_level']:
                return False
            if market_summary['volume_trend'] not in template['volume_trend']:
                return False
            if not (0 <= market_summary['confidence'] <= 100):
                return False
            return True
        except Exception:
            return False

    def load_gpt_config(self) -> Dict:
        """GPT 설정 파일 로드"""
        try:
            config_path = 'config/gpt_config.json'
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                if not isinstance(config, dict):
                    logger.error("GPT 설정 파일이 올바른 형식이 아닙니다")
                    return {}
                return config
        except Exception as e:
            logger.error(f"GPT 설정 파일 로드 실패: {str(e)}")
            return {}

    async def analyze_4h(self, data: pd.DataFrame) -> Dict:
        """4시간봉 분석"""
        try:
            # 기술적 지표 계산
            indicators = self._calculate_technical_indicators(data)
            
            # 추세 분석
            trend_analysis = self._analyze_trend(data)
            
            analysis = {
                "result": {
                    "market_summary": {
                        "market_phase": "상승" if data['close'].iloc[-1] > data['close'].iloc[-2] else "하락",
                        "overall_sentiment": "긍정적" if data['close'].iloc[-1] > data['open'].iloc[-1] else "부정적",
                        "short_term_sentiment": "긍정적" if data['close'].iloc[-1] > data['open'].iloc[-1] else "부정적",
                        "volume_trend": "거래량 " + ("증가" if data['volume'].iloc[-1] > data['volume'].iloc[-2] else "감소")
                    },
                    "technical_analysis": {
                        "trend": "상승" if data['close'].iloc[-1] > data['close'].iloc[-2] else "하락",
                        "strength": round(float(abs(data['close'].iloc[-1] - data['close'].iloc[-2]) / data['close'].iloc[-2] * 100), 2),
                        "indicators": {
                            "rsi_signal": "과매수" if indicators['rsi'] > 70 else "과매도" if indicators['rsi'] < 30 else "중립",
                            "macd_signal": "매수" if indicators['macd']['macd'] > indicators['macd']['signal'] else "매도",
                            "divergence": {
                                "timeframe": "4h",
                                "type": "상" if indicators['macd']['histogram'] > 0 else "하락",
                                "description": f"MACD: {round(indicators['macd']['macd'], 2)}, Signal: {round(indicators['macd']['signal'], 2)}"
                            }
                        }
                    },
                    "trading_strategy": {
                        "position_suggestion": "매수" if trend_analysis['trend'] == "BULLISH" else "매도",
                        "entry_points": [float(data['close'].iloc[-1])],
                        "stop_loss": float(data['close'].iloc[-1] * 0.98),  # 2% 손절
                        "take_profit": [
                            float(data['close'].iloc[-1] * 1.04),  # 4% 익절
                            float(data['close'].iloc[-1] * 1.08)   # 8% 익절
                        ],
                        "leverage": 5,
                        "position_size": 20
                    }
                },
                "timestamp": int(time.time())
            }
            return analysis
            
        except Exception as e:
            logger.error(f"4시간봉 분석 중 오류: {str(e)}")
            return {
                "result": {
                    "market_summary": {
                        "market_phase": "분석 실패",
                        "overall_sentiment": "중립",
                        "short_term_sentiment": "분석 실패",
                        "volume_trend": "분석 실패"
                    },
                    "technical_analysis": {
                        "trend": "분석 실패",
                        "strength": 0,
                        "indicators": {
                            "rsi_signal": "분석 실패",
                            "macd_signal": "분석 실패",
                            "divergence": {
                                "timeframe": "4h",
                                "type": "분석 실패",
                                "description": "기술적 지표 계산 중 오류 발생"
                            }
                        }
                    },
                    "trading_strategy": {
                        "position_suggestion": "관망",
                        "entry_points": [],
                        "stop_loss": 0,
                        "take_profit": [],
                        "leverage": 1,
                        "position_size": 0
                    }
                },
                "timestamp": int(time.time())
            }

    async def analyze_final(self, analyses: Dict) -> Dict:
        """Final 분석 실행"""
        try:
            # 현재가 검증 및 조회
            current_price = await self._get_current_price()
            if current_price is None:
                logger.error("현재가 조회 실패")
                return None

            # GPT 프롬프트 생성
            prompt = self._create_final_analysis_prompt(analyses, current_price)
            
            # GPT API 호출
            response = await self.gpt_client.call_gpt_api(prompt)
            if not response:
                logger.error("GPT API 응답이 없습니다")
                return None
            
            # 상세 응답 로깅
            logger.debug(f"응답 내용: {response}")
            logger.debug("=== GPT API 응답 끝 ===")
            
            # 응답 파싱 및 검증
            final_analysis = self._parse_final_analysis(response)
            if not final_analysis:
                logger.error("응답 파싱 실패")
                return None

            # 다이버전스 정보 제거
            if 'technical_analysis' in final_analysis and 'indicators' in final_analysis['technical_analysis']:
                if 'divergence' in final_analysis['technical_analysis']['indicators']:
                    del final_analysis['technical_analysis']['indicators']['divergence']

            # 자동매매 검증
            final_analysis['trading_strategy']['auto_trading'] = self._validate_auto_trading({
                "market_summary": {"confidence": final_analysis['market_summary']['confidence']},
                "technical_analysis": {"strength": final_analysis['technical_analysis']['strength']}
            })

            logger.debug(f"Final 분석 결과: {final_analysis}")
            return final_analysis
            
        except Exception as e:
            logger.error(f"Final 분석 중 오류: {str(e)}")
            return None

    def _update_trading_strategy(self, trading_strategy: Dict, current_price: float):
        """거래 전략 업데이트"""
        position = trading_strategy.get('position_suggestion', '').upper()
        
        # 진입가격 설정
        trading_strategy['entry_points'] = [current_price]
        
        # 손절가/익절가 설정
        if position in ['매수', 'BUY', 'LONG']:
            trading_strategy['stop_loss'] = current_price * 0.98
            trading_strategy['take_profit'] = [
                current_price * 1.02,
                current_price * 1.04
            ]
        elif position in ['매도', 'SELL', 'SHORT']:
            trading_strategy['stop_loss'] = current_price * 1.02
            trading_strategy['take_profit'] = [
                current_price * 0.98,
                current_price * 0.96
            ]

    def _update_divergence_info(self, response: Dict, analyses: Dict[str, Dict]):
        """다이버전스 정보 업데이트"""
        try:
            # Final 분석의 technical_analysis가 없으면 생성
            if 'technical_analysis' not in response:
                response['technical_analysis'] = {}
            if 'indicators' not in response['technical_analysis']:
                response['technical_analysis']['indicators'] = {}
            
            # Final 분석에서는 다이버전스 정보를 '없음'으로 설정
            response['technical_analysis']['indicators']['divergence'] = {
                'type': '없음',
                'description': 'Final 분석은 다이버전스를 확인하지 않습니다',
                'timeframe': 'final'
            }
            
        except Exception as e:
            logger.error(f"다이버전스 정보 업데이트 중 오류: {str(e)}")

    def _create_final_analysis_prompt(self, analyses: Dict[str, Dict], current_price: float) -> str:
        """최종 분석을 위한 프롬프트 생성"""
        prompt_parts = [
            f"현재가: ${current_price:,.2f}\n",
            "아래 형식의 JSON으로만 응답해주세요. 다른 텍스트는 포함하지 마세요:\n",
            "{\n",
            '  "market_phase": "상승" 또는 "하락" 또는 "횡보",\n',
            '  "overall_sentiment": "긍정적" 또는 "부정적" 또는 "중립",\n',
            '  "short_term_sentiment": "긍정적" 또는 "부정적" 또는 "중립",\n',
            '  "trend": "상승" 또는 "하락" 또는 "횡보",\n',
            '  "strength": 0-100 사이의 숫자,\n',
            '  "position": "매수" 또는 "매도" 또는 "관망",\n',
            f'  "entry_price": {current_price},\n',
            f'  "stop_loss": {current_price * 0.98},\n',
            f'  "take_profit": [{current_price * 1.02}, {current_price * 1.04}],\n',
            '  "leverage": 1-10 사이의 정수,\n',
            '  "position_size": 1-30 사이의 정수,\n',
            '  "divergence_type": "상승" 또는 "하락" 또는 "없음",\n',
            '  "divergence_description": "상세 설명"\n',
            "}\n\n",
            "위 JSON 형식으로만 응답하세요. 다른 설명이나 텍스트는 포함하지 마세요.\n\n",
            "참고할 시간대 분석:\n"
        ]

        # 각 시간대 분석 정보 추가
        for timeframe, analysis in analyses.items():
            market_summary = analysis.get('market_summary', {})
            tech_analysis = analysis.get('technical_analysis', {})
            
            prompt_parts.append(f"""
{timeframe} 분석:
• 시장 단계: {market_summary.get('market_phase', '불명확')}
• 전반적 심리: {market_summary.get('overall_sentiment', '중립')}
• 추세: {tech_analysis.get('trend', '횡보')}
• 강도: {tech_analysis.get('strength', 0)}
• 다이버전스: {tech_analysis.get('indicators', {}).get('divergence', {}).get('type', '없음')}
""")

        return "".join(prompt_parts)

    def _validate_analysis_data(self, analysis_data: Dict) -> bool:
        """분석 데이터 검증"""
        try:
            # 필수 섹션 검사
            required_sections = ['market_summary', 'technical_analysis', 'trading_strategy']
            if not all(section in analysis_data for section in required_sections):
                missing = [s for s in required_sections if s not in analysis_data]
                logger.error(f"필수 섹션 누락: {missing}")
                return False

            return True

        except Exception as e:
            logger.error(f"분석 데이터 검증 중 오류: {str(e)}")
            return False

    def create_final_analysis(self, analyses: Dict) -> Dict:
        """ 시간대 분석을 종합하여 최종 분석 생성"""
        try:
            if not analyses:
                logger.error("분석 데이터가 없습니다")
                return {}

            # 분석 과 통합
            final_analysis = {
                'market_summary': self._combine_market_summaries(analyses),
                'technical_analysis': self._combine_technical_analyses(analyses),
                'trading_strategy': self._combine_trading_strategies(analyses)
            }

            return final_analysis

        except Exception as e:
            logger.error(f"최치 분석 생성 중 오류: {str(e)}")
            return {}

    def _calculate_weighted_bullish_score(self, analyses: Dict) -> tuple[float, float]:
        """가중치를 적용한 상승 점수 계산"""
        bullish_count = 0
        total_weight = 0
        
        for timeframe, analysis in analyses.items():
            if timeframe not in self.TIMEFRAME_WEIGHTS:
                continue
                
            weight = self.TIMEFRAME_WEIGHTS[timeframe]
            market_summary = analysis.get('market_summary', {})
            
            if market_summary.get('market_phase') == "BULLISH":
                bullish_count += weight
            
            total_weight += weight
            
        return bullish_count, total_weight

    def _combine_market_summaries(self, analyses: Dict) -> Dict:
        """시장 요약 데이터 통합"""
        try:
            bullish_count, total_weight = self._calculate_weighted_bullish_score(analyses)
            
            # 4시봉과 15분봉 데이터를 활용
            four_hour = analyses.get('4h', {}).get('market_summary', {})
            fifteen_min = analyses.get('15m', {}).get('market_summary', {})
            
            # 신뢰도는 각 시간대의 신뢰도 가중 평균으로 산
            total_confidence = 0
            total_weight = 0
            for timeframe, weight in self.TIMEFRAME_WEIGHTS.items():
                if timeframe in analyses:
                    confidence = analyses[timeframe].get('market_summary', {}).get('confidence', 50)
                    total_confidence += confidence * weight
                    total_weight += weight
            
            confidence = round(total_confidence / total_weight if total_weight > 0 else 50)
            
            return {
                "market_phase": "상승" if bullish_count > 0.5 else "하락",
                "overall_sentiment": four_hour.get('overall_sentiment', "중립"),
                "short_term_sentiment": fifteen_min.get('overall_sentiment', "중립"),
                "volume_trend": four_hour.get('volume_trend', "중립"),
                "risk_level": "높음" if abs(bullish_count - 0.5) < 0.2 else "중간",
                "confidence": confidence
            }
        except Exception as e:
            logger.error(f"시장 요약 통합 중 오류: {str(e)}")
            return {
                "market_phase": "횡보",
                "overall_sentiment": "중립",
                "short_term_sentiment": "중립",
                "volume_trend": "중립",
                "risk_level": "중간",
                "confidence": 50.0
            }

    def _combine_technical_analyses(self, analyses: Dict) -> Dict:
        """여러 시간대의 기술적 분석 결과 통합"""
        try:
            # 4시간봉 데이터 기준으로 기술 지표 정보 사용
            four_hour = analyses.get('4h', {}).get('technical_analysis', {})
            indicators = four_hour.get('indicators', {})
            
            # 다이버전스 정보 처리
            divergence = {
                "type": "없음",  # 기본값 설정
                "description": "",  # 실제 다이버전스 설명이 들어가야 함
                "timeframe": "4h"
            }
            
            # 4시간봉의 다이버전스 정보 가져오기
            if 'divergence' in indicators:
                div_info = indicators['divergence']
                if isinstance(div_info, dict):
                    divergence.update(div_info)  # 4시간봉의 다이버전스 정보로 업데이트
            
            # 통합된 기술적 분석 결과
            technical_analysis = {
                "trend": four_hour.get('trend', '불명확'),
                "strength": four_hour.get('strength', 50),
                "indicators": {
                    "rsi": indicators.get('rsi', 0),
                    "macd": indicators.get('macd', '중립'),
                    "bollinger": indicators.get('bollinger', '중단'),
                    "divergence": divergence  # 처리된 다이버전스 정보
                }
            }
            
            return technical_analysis
            
        except Exception as e:
            logger.error(f"기술적 분석 통합 중 오류: {str(e)}")
            return {}

    async def _get_current_price(self) -> float:
        """현재가 조회"""
        try:
            if not self.market_data_service:
                logger.error("market_data_service가 초기화되지 않았습니다")
                return None
                
            price_data = await self.market_data_service.get_current_price()
            if not price_data:
                logger.error("현재가 데이터를 가져올 수 없습니다")
                return None
                
            # last_price 추출
            current_price = float(price_data.get('last_price', 0))
            if current_price <= 0:
                logger.error(f"잘못된 현재가: {current_price}")
                return None
                
            return current_price
            
        except Exception as e:
            logger.error(f"현재가 조회 중 오류: {str(e)}")
            return None

    async def _combine_trading_strategies(self, analyses: Dict) -> Dict:
        """거래 전략 데이터 통합"""
        try:
            # 가중치 기반 매수/매도 점수 계산
            bullish_count, total_weight = self._calculate_weighted_bullish_score(analyses)
            current_price = await self._get_current_price()
            
            # 4시간봉 분석의 신뢰도와 강도 사용
            h4_analysis = analyses.get('4h', {})
            confidence = h4_analysis.get('market_summary', {}).get('confidence', 70)
            strength = h4_analysis.get('technical_analysis', {}).get('strength', 50)
            
            # 기본 신호 생성
            trading_signal = {
                "position": "매수" if bullish_count > 0.6 else "매도" if bullish_count < 0.4 else "관망",
                "entry_points": [current_price],
                "targets": [
                    current_price * (1 + 0.03),
                    current_price * (1 + 0.05)
                ],
                "stop_loss": current_price * (1 - 0.02),
                "leverage": min(10, max(5, int(confidence / 10))),
                "position_size": min(30, max(15, int(confidence / 4)))
            }

            # 자동매매 검증
            trading_signal["auto_trading"] = self._validate_auto_trading({
                "market_summary": {"confidence": confidence},
                "technical_analysis": {"strength": strength}
            })

            return trading_signal

        except Exception as e:
            logger.error(f"거래 전략 통합 중 오류: {str(e)}")
            return None

    async def _create_weighted_analysis(self, analyses: Dict) -> Dict:
        """가중치를 적용한 최종 분석 생성"""
        try:
            # 시장 요약 생성
            market_summary = self._combine_market_summaries(analyses)
            
            # 기술적 분석 생성
            technical_analysis = self._combine_technical_analyses(analyses)
            
            # 거래 전략 생성
            trading_strategy = await self._combine_trading_strategies(analyses)
            
            # 시장 상황 분석 추가
            market_conditions = {
                'trend': self._get_majority_trend(analyses),
                'volume_trend': self._get_majority_volume_trend(analyses),
                'short_term_sentiment': self._get_short_term_sentiment(analyses),
                'risk_level': market_summary.get('risk_level', '중간'),
                'volatility': technical_analysis.get('strength', 50),
                'key_levels': {
                    'support': [],  # 지지선
                    'resistance': []  # 저항선
                }
            }

            # 거래 신호 생성
            trading_signals = {
                'auto_trading_enabled': trading_strategy.get('auto_trading', {}).get('enabled', False),
                'primary_signal': {
                    'direction': 'long' if trading_strategy.get('position') == "매수" else 
                                'short' if trading_strategy.get('position') == "매도" else 'none',
                    'strength': technical_analysis.get('strength', 0),
                    'confidence': trading_strategy.get('auto_trading', {}).get('confidence', 0)
                }
            }

            # 최종 분석 결과 생성
            final_analysis = {
                'market_summary': market_summary,
                'technical_analysis': technical_analysis,
                'trading_strategy': trading_strategy,
                'market_conditions': market_conditions,  # 가중치 적용
                'trading_signals': trading_signals,
                'timestamp': int(time.time())
            }

            return final_analysis

        except Exception as e:
            logger.error(f"중치 분석 생성 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    async def call_gpt_api(self, request_text: str) -> Dict:
        """GPT API 호출"""
        try:
            response = await self.gpt_client.generate(request_text)
            if not response:
                return {}

            try:
                # 현재가 조회
                current_price = await self._get_current_price()
                if not current_price:
                    logger.error("현재가 조회 실패")
                    return {}
                
                # JSON 문열 추출 (괄호 둘인 부분)
                json_match = re.search(r'\{[\s\S]*\}', response)
                if not json_match:
                    logger.error("JSON 형식 응답 찾을 수 없습니다")
                    logger.error(f"원본 응답: {response}")
                    return {}
                
                json_str = json_match.group()
                
                # 현재가 대체 및 수식 계산
                def replace_price_and_calc(match):
                    expr = match.group(1)
                    expr = expr.replace('현재가', str(current_price))
                    try:
                        return str(float(eval(expr)))
                    except:
                        return expr

                # 현재가 관련 패턴 수정
                price_patterns = [
                    (r'"entry_points":\s*\[(현재가[^]]*)\]', lambda m: f'"entry_points": [{current_price}]'),
                    (r'"take_profit":\s*\[(현재가[^]]*)\]', lambda m: f'"take_profit": [{current_price * 1.02}, {current_price * 1.04}]'),
                    (r'"stop_loss":\s*(현재가[^,}]*)', lambda m: f'"stop_loss": {current_price * 0.98}')
                ]

                for pattern, replacement in price_patterns:
                    json_str = re.sub(pattern, replacement, json_str)
                
                # 숫자에서 마 제거
                json_str = re.sub(r'(\d),(\d)', r'\1\2', json_str)
                
                # JSON 파싱
                analysis = json.loads(json_str)
                
                # 응답 형식 맞추기
                if 'trading_strategy' in analysis:
                    strategy = analysis['trading_strategy']
                    
                    # position -> position_suggestion 변환
                    if 'position' in strategy:
                        strategy['position_suggestion'] = strategy.pop('position')
                    
                    # targets -> take_profit 변환
                    if 'targets' in strategy:
                        strategy['take_profit'] = strategy.pop('targets')
                    
                    # 필수 필드 기본값 설정
                    if 'entry_points' not in strategy:
                        strategy['entry_points'] = []
                    if 'take_profit' not in strategy:
                        strategy['take_profit'] = []
                    if 'stop_loss' not in strategy:
                        strategy['stop_loss'] = 0
                    if 'leverage' not in strategy:
                        strategy['leverage'] = 5
                    if 'position_size' not in strategy:
                        strategy['position_size'] = 10
                    
                    # auto_trading 정보 추가
                    confidence = analysis.get('market_summary', {}).get('confidence', 0)
                    strategy['auto_trading'] = {
                        'enabled': confidence >= 75,
                        'reason': '신뢰도가 충분히 높음' if confidence >= 75 else '신뢰도 부족',
                        'confidence': confidence
                    }
                
                # 불요 필드 제거
                for field in ['risk_management', 'support_levels', 'resistance_levels']:
                    if field in analysis:
                        del analysis[field]
                    if field in analysis.get('technical_analysis', {}):
                        del analysis['technical_analysis'][field]
                
                return analysis
                
            except json.JSONDecodeError as e:
                logger.error(f"GPT 응답 JSON 파싱 실패: {str(e)}")
                logger.error(f"파싱 시도한 문자열: {json_str if 'json_str' in locals() else response}")
                return {}
                
        except Exception as e:
            logger.error(f"GPT API 호출 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return {}

    def _create_analysis_prompt(self, data: pd.DataFrame, indicators: Dict, timeframe: str) -> str:
        """분석 프롬프트 생성"""
        try:
            current_price = data['close'].iloc[-1]
            
            prompt_parts = [
                f"현재가: ${current_price:,.2f}\n",
                "아래 형식의 JSON으로만 응답해주세요. 다른 텍스트는 포함하지 마세요:\n",
                "{\n",
                '  "market_phase": "상승" 또는 "하락" 또는 "횡보",\n',
                '  "overall_sentiment": "긍정적" 또는 "부정적" 또는 "중립",\n',
                '  "short_term_sentiment": "긍정적" 또는 "부정적" 또는 "중립",\n',
                '  "trend": "상승" 또는 "하락" 또는 "횡보",\n',
                '  "strength": 0-100 사이의 숫자,\n',
                '  "position": "매수" 또는 "매도" 또는 "관망",\n',
                f'  "entry_price": {current_price},\n',
                f'  "stop_loss": {current_price * 0.98},\n',
                f'  "take_profit": [{current_price * 1.02}, {current_price * 1.04}],\n',
                '  "leverage": 1-10 사이의 정수,\n',
                '  "position_size": 1-30 사이의 정수,\n',
                '  "divergence_type": "상승" 또는 "하락" 또는 "없음",\n',
                '  "divergence_description": "상세 설명"\n',
                "}\n\n",
                f"시간대: {timeframe}\n",
                f"기술적 지표:\n",
                f"• RSI: {indicators.get('rsi', 50)}\n",
                f"• MACD: {indicators.get('macd', {}).get('macd', 0)}\n",
                f"• Signal: {indicators.get('macd', {}).get('signal', 0)}\n",
                f"• Bollinger: {indicators.get('bollinger_bands', {}).get('position', 'middle')}\n"
            ]

            return "".join(prompt_parts)

        except Exception as e:
            logger.error(f"프롬프트 생성 중 오류: {str(e)}")
            return None

    def _format_additional_indicators(self, indicators: dict) -> str:
        """추가 기술적 지표 포팅"""
        additional = []
        
        # 볼린저 밴드 (있는 경우만)
        if 'bollinger_bands' in indicators:
            bb = indicators['bollinger_bands']
            additional.append(f"• 볼린저 밴드: 상단 ${bb['upper']:.2f}, 중간 ${bb['middle']:.2f}, 하단 ${bb['lower']:.2f}")
        
        # 이동평균선 (있는 경우만)
        if 'moving_averages' in indicators:
            ma = indicators['moving_averages']
            if 'ma20' in ma:
                additional.append(f"• MA20: ${ma['ma20']:.2f}")
            if 'ma50' in ma:
                additional.append(f"• MA50: ${ma['ma50']:.2f}")
        
        return "\n".join(additional) if additional else "추가 지표 없음"

    def _get_majority_trend(self, analyses: Dict) -> str:
        """가장 많은 나타난 추세 반환"""
        trends = []
        for analysis in analyses.values():
            if 'result' in analysis:
                trend = analysis['result']['technical_analysis'].get('trend')
                if trend:
                    trends.append(trend)
            elif 'technical_analysis' in analysis:
                trend = analysis['technical_analysis'].get('trend')
                if trend:
                    trends.append(trend)
        
        if not trends:
            return "횡보"
        
        return Counter(trends).most_common(1)[0][0]

    def _get_majority_volume_trend(self, analyses: Dict[str, Dict]) -> str:
        """거래량 추세의 다수결 결"""
        try:
            volume_trends = []
            for timeframe, analysis in analyses.items():
                if 'market_summary' in analysis:
                    trend = analysis['market_summary'].get('volume_trend')
                    if trend:
                        volume_trends.append(trend)
            
            if not volume_trends:
                return "분석 중"
            
            counter = Counter(volume_trends)
            return counter.most_common(1)[0][0]
            
        except Exception as e:
            logger.error(f"거래량 추세 분석 중 오류: {str(e)}")
            return "분석 중"

    def _get_short_term_sentiment(self, analyses: Dict[str, Dict]) -> str:
        """단기 심리 분석"""
        try:
            # 15분과 1시간 분석에 중치를 둠
            sentiments = []
            weights = {'15m': 2, '1h': 2, '4h': 1, '1d': 1}
            
            for timeframe, analysis in analyses.items():
                if 'market_summary' in analysis:
                    sentiment = analysis['market_summary'].get('short_term_sentiment')
                    if sentiment:
                        weight = weights.get(timeframe, 1)
                        sentiments.extend([sentiment] * weight)
            
            if not sentiments:
                return "분석 중"
            
            counter = Counter(sentiments)
            return counter.most_common(1)[0][0]
            
        except Exception as e:
            logger.error(f"단기 심리 분석 중 오류: {str(e)}")
            return "분석 중"

    def _format_divergence(self, divergence: Dict) -> str:
        """다이버전스 정보 포맷팅"""
        try:
            if not divergence or divergence.get('type') == '없음':
                return "없음"
            return f"{divergence.get('type')} ({divergence.get('description', '')})"
        except Exception as e:
            logger.error(f"다이버전스 포맷팅 중 오류: {str(e)}")
            return "없음"

    async def _request_gpt_analysis(self, prompt: str) -> Dict:
        """GPT API 요청  응답 처리"""
        try:
            # GPT API 호출
            response = await self.call_gpt_api(prompt)
            if not response:
                logger.error("GPT API 응답이 없습니다")
                return None
            
            # 응답 검증
            if self.validate_response(response):
                return response
            else:
                logger.error("GPT 응답 검증 실패")
                return None
            
        except Exception as e:
            logger.error(f"GPT 분석 요청 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def _validate_auto_trading(self, analysis: Dict) -> Dict:
        """자동매매 활성화 여부 검증"""
        try:
            # 신뢰도와 추세 강도 확인
            confidence = analysis.get("market_summary", {}).get("confidence", 0)
            strength = analysis.get("technical_analysis", {}).get("strength", 0)
            
            # 조건 체크 (수정된 부분)
            high_confidence = confidence >= 70  # 신뢰도 70% 이상
            strong_trend = strength >= 50      # 추세 강도 50% 이상
            enabled = high_confidence and strong_trend
            
            # 상세 이유 설정
            if enabled:
                reason = f"신뢰도({confidence}%)와 추세 강도({strength}%)가 충분함"
            else:
                reasons = []
                if not high_confidence:
                    reasons.append(f"신뢰도 부족({confidence}%)")
                if not strong_trend:
                    reasons.append(f"추세 강도 부족({strength}%)")
                reason = " / ".join(reasons)
            
            return {
                "enabled": enabled,
                "confidence": confidence,
                "strength": strength,
                "reason": reason,
                "conditions": {
                    "high_confidence": high_confidence,
                    "strong_trend": strong_trend
                }
            }
            
        except Exception as e:
            logger.error(f"자동매매 검증 중 오류: {str(e)}")
            return {
                "enabled": False,
                "confidence": 0,
                "strength": 0,
                "reason": "검증 중 오류 발생",
                "conditions": {
                    "high_confidence": False,
                    "strong_trend": False
                }
            }

    async def get_last_analysis(self, timeframe: str) -> Dict:
        """마지막 분석 결과 조회"""
        try:
            if timeframe not in self.last_analysis:
                # 새로 분석 실행
                return await self.analyze_market(timeframe)
            return self.last_analysis[timeframe]
        except Exception as e:
            logger.error(f"마지막 분석 조회 중 오류: {str(e)}")
            return None

    async def analyze_market(self, timeframe: str, data: pd.DataFrame) -> Dict:
        """단일 시간대 시장 분석"""
        try:
            # 데이터 검증
            if data is None or len(data) == 0:
                logger.error(f"{timeframe} 분석을 위한 데이터가 없습니다")
                return None

            # 기술적 지표 계산 (technical.py 사용)
            df_with_indicators = self.technical_indicators.calculate_indicators(data)
            if df_with_indicators is None:
                logger.error("기술적 지표 계산 실패")
                return None
            
            # 기술적 분석 결과 생성
            technical_analysis = {
                'trend': self._determine_trend(df_with_indicators),
                'strength': round(self._calculate_trend_strength(df_with_indicators), 2),
                'indicators': {
                    'rsi': round(float(df_with_indicators['rsi'].iloc[-1]), 2),
                    'macd': '상승' if df_with_indicators['macd'].iloc[-1] > 0 else '하락',
                    'bollinger': self._get_bollinger_position(df_with_indicators),
                    'divergence': {
                        **self.technical_indicators.check_rsi_divergence(df_with_indicators),
                        'timeframe': timeframe  # 현재 분석 중인 timeframe 추가
                    }
                }
            }
            
            # GPT에는 해석만 요청
            prompt = self._create_analysis_prompt(df_with_indicators, technical_analysis, timeframe)
            interpretation = await self.gpt_client.call_gpt_api(prompt)
            
            if interpretation:
                # 최종 분석 결과 조합
                analysis = {
                    'market_summary': interpretation['market_summary'],
                    'technical_analysis': technical_analysis,  # 직접 계산한 기술적 분석 사용
                    'trading_strategy': interpretation['trading_strategy']
                }
                return analysis
            
        except Exception as e:
            logger.error(f"{timeframe} 분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def _parse_final_analysis(self, response: Dict) -> Dict:
        """최종 분석 응답 파싱"""
        try:
            # JSON 문자열로 온 경우 처리
            if isinstance(response, str):
                try:
                    response = json.loads(response)
                except json.JSONDecodeError:
                    logger.error("JSON 파싱 실패")
                    return None

            # 응답 구조 로깅
            logger.debug(f"GPT 응답 구조: {response.keys()}")
            
            # 이미 구조화된 응답인 경우
            if all(key in response for key in ['market_summary', 'technical_analysis', 'trading_strategy']):
                # 4시간봉의 RSI 값만 업데이트
                h4_analysis = self.storage_formatter.load_analysis('4h')
                if h4_analysis and 'technical_analysis' in h4_analysis:
                    response['technical_analysis']['indicators']['rsi'] = h4_analysis['technical_analysis']['indicators'].get('rsi', 50)
                return response

            # 여기서부터는 기존 코드 그대로 유지
            required_fields = [
                'market_phase', 'overall_sentiment', 'short_term_sentiment',
                'trend', 'strength', 'position', 'entry_price', 'stop_loss',
                'take_profit', 'leverage', 'position_size'
            ]

            missing = [field for field in required_fields if field not in response]
            if missing:
                logger.error(f"GPT 응답에서 필수 필드 누락: {missing}")
                logger.debug(f"전체 응답 내용: {response}")
                return None

            # 나머지 코드도 그대로 유지...
            final_analysis = {
                'market_summary': {
                    'market_phase': response['market_phase'],
                    'overall_sentiment': response['overall_sentiment'],
                    'short_term_sentiment': response['short_term_sentiment'],
                    'confidence': 85
                },
                'technical_analysis': {
                    'trend': response['trend'],
                    'strength': round(float(response['strength']), 2),
                    'indicators': {
                        'rsi': h4_analysis['technical_analysis']['indicators'].get('rsi', 50),  # 4시간봉 RSI 사용
                        'macd': response.get('macd', 'neutral'),
                        'bollinger': response.get('bollinger', '중단')
                    }
                },
                'trading_strategy': {
                    'position_suggestion': response['position'],
                    'entry_points': [float(response['entry_price'])],
                    'stop_loss': float(response['stop_loss']),
                    'take_profit': ([float(tp) for tp in response['take_profit']] 
                                    if isinstance(response['take_profit'], list) 
                                    else [float(response['take_profit'])]),
                    'leverage': int(response['leverage']),
                    'position_size': int(response['position_size'])
                }
            }

            return final_analysis

        except Exception as e:
            logger.error(f"최종 분석 응답 파싱 중 오류: {str(e)}")
            logger.error(f"응답 내용: {response}")
            logger.error(traceback.format_exc())
            return None

    def _determine_trend(self, df: pd.DataFrame) -> str:
        """추세 판단"""
        try:
            latest = df.iloc[-1]
            
            # 이동평균선 기반 추세 판단 (수정)
            sma_trend = "상승" if latest['sma_10'] > latest['sma_30'] else "하락"
            
            # MACD 기반 추세 판단
            macd_trend = "상승" if latest['macd'] > latest['macd_signal'] else "하락"
            
            # ADX 기반 추세 강도 판단
            strong_trend = latest['adx'] > 25
            
            # DI 기반 방향성 판단
            di_trend = "상승" if latest['di_plus'] > latest['di_minus'] else "하락"
            
            # 종합 판단
            trends = [sma_trend, macd_trend, di_trend]
            up_count = sum(1 for t in trends if t == "상승")
            
            if up_count >= 2:
                return "상승" if strong_trend else "약상승"
            elif up_count <= 1:
                return "하락" if strong_trend else "약하락"
            else:
                return "횡보"
            
        except Exception as e:
            logger.error(f"추세 판단 중 오류: {str(e)}")
            return "불명확"

    def _calculate_trend_strength(self, df: pd.DataFrame) -> float:
        """추세 강도 계산"""
        try:
            latest = df.iloc[-1]
            
            # trend_strength 컬럼이 있으면 그대로 사용
            if 'trend_strength' in df.columns:
                return float(latest['trend_strength'])
            
            # 없으면 기존 방식으로 계산
            adx_strength = float(latest['adx'])
            macd_strength = abs(latest['macd'] - latest['macd_signal']) / latest['close'] * 100
            ma_diff = abs(latest['sma_10'] - latest['sma_30']) / latest['close'] * 100
            
            strength = (adx_strength * 0.4) + (macd_strength * 0.35) + (ma_diff * 0.25)
            return round(min(100, max(0, strength)), 2)
            
        except Exception as e:
            logger.error(f"추세 강도 계산 중 오류: {str(e)}")
            return 50.0

    def _get_bollinger_position(self, df: pd.DataFrame) -> str:
        """볼린저 밴드 상의 위치 판단"""
        try:
            latest = df.iloc[-1]
            price = latest['close']
            
            if price > latest['bb_upper']:
                return "상단"
            elif price < latest['bb_lower']:
                return "하단"
            else:
                return "중단"
            
        except Exception as e:
            logger.error(f"볼린저 밴드 위치 판단 중 오류: {str(e)}")
            return "중단"