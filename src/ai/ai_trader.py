import logging
import json
import time
from typing import Dict, List, Optional
from collections import Counter
import traceback
import asyncio
import os
from datetime import datetime

from exchange.bybit_client import BybitClient
from services.position_service import PositionService
from services.order_service import OrderService
from services.market_data_service import MarketDataService
from trade.trade_manager import TradeManager
from .gpt_analyzer import GPTAnalyzer
from indicators.technical import TechnicalIndicators
from telegram_bot.formatters.storage_formatter import StorageFormatter
from config.trading_config import trading_config

logger = logging.getLogger(__name__)

class AITrader:
    def __init__(self, bybit_client: BybitClient, telegram_bot, order_service: OrderService, 
                 position_service: PositionService, trade_manager: TradeManager):
        self.bybit_client = bybit_client
        self.telegram_bot = telegram_bot
        self.order_service = order_service
        self.position_service = position_service
        self.trade_manager = trade_manager
        self.market_data_service = telegram_bot.market_data_service
        
        # GPT 분석기 초기화 - market_data_service 전달
        self.gpt_analyzer = GPTAnalyzer(
            bybit_client=bybit_client,
            market_data_service=self.market_data_service
        )
        
        # StorageFormatter 초기화 수정
        self.storage_formatter = StorageFormatter()  # 인자 제거
        
        self.analyses = {}
        self.last_analysis_time = {}
        self.symbol = trading_config.symbol
        self.technical_indicators = TechnicalIndicators()
        self.MIN_CONFIDENCE = trading_config.auto_trading['confidence']['min']
        self.last_trade_time = 0
        self.trade_cooldown = 300
        self.last_analysis_times = {}
        self.last_analysis_results = {}

    async def initialize(self):
        """초기화 메서드"""
        try:
            # GPT Analyzer 초기화
            self.gpt_analyzer = GPTAnalyzer(self.bybit_client)
            logger.info("GPT Analyzer 초기화 완료")
            
            if not self.telegram_bot:
                self.telegram_bot = None
            logger.info("AI Trader 초기화 완료")
            return True
        except Exception as e:
            logger.error(f"AI Trader 초기화 실패: {str(e)}")
            return False

    async def create_final_analysis(self, analyses: Dict) -> Dict:
        """최종 분석 생성"""
        try:
            # current_price 제거하고 analyses만 전달
            final_analysis = await self.gpt_analyzer.analyze_final(analyses)
            if not final_analysis:
                logger.error("최종 분석 생성 실패")
                return None
            
            return final_analysis
            
        except Exception as e:
            logger.error(f"최종 분석 생성 중 오류: {str(e)}")
            return None

    def _validate_final_analysis(self, analysis: Dict) -> bool:
        """최종 분석 결과 유효성 검사"""
        try:
            required_sections = [
                'market_summary', 'technical_analysis', 
                'trading_strategy', 'market_conditions',
                'trading_signals'
            ]
            
            if not all(key in analysis for key in required_sections):
                logger.error(f"필수 섹션 누락: {[key for key in required_sections if key not in analysis]}")
                return False

            market_conditions = analysis.get('market_conditions', {})
            required_condition_fields = {
                'trend', 'volume_trend', 'short_term_sentiment',
                'risk_level', 'volatility', 'key_levels'
            }
            
            if not all(key in market_conditions for key in required_condition_fields):
                logger.error(f"market_conditions 필드 누락: {required_condition_fields - market_conditions.keys()}")
                return False

            return True

        except Exception as e:
            logger.error(f"최종 분석 결과 검증 중 오류: {str(e)}")
            return False

    async def analyze_market(self, timeframe: str, klines: List) -> Dict:
        """시장 분석 실행"""
        try:
            # 전달받은 데이터로 분석 실행
            analysis = await self.gpt_analyzer.analyze(klines, timeframe)
            if analysis:
                self.storage_formatter.save_analysis(analysis, timeframe)
            return analysis
            
        except Exception as e:
            logger.error(f"시장 분석 중 오류: {str(e)}")
            return None

    def _calculate_risk_level(self, analysis: Dict) -> str:
        """위험도 계산"""
        try:
            if not analysis or 'technical_analysis' not in analysis:
                return "중간"
                
            tech_analysis = analysis['technical_analysis']
            
            if tech_analysis.get('volatility', 'NORMAL') == 'HIGH':
                return "높음"
                
            if tech_analysis.get('rsi_signal') in ['OVERBOUGHT', 'OVERSOLD']:
                return "높음"
                
            if tech_analysis.get('trend_strength', 0) > 70:
                return "높음"
                
            return "중간"
            
        except Exception as e:
            logger.error(f"위험도 계산 중 오류: {str(e)}")
            return "중간"

    def _identify_key_risks(self, analyses: dict) -> list:
        """주 리스크 요인 식별"""
        try:
            risks = set()
            
            for timeframe, analysis in analyses.items():
                if analysis:
                    if 'market_summary' in analysis:
                        market_phase = analysis['market_summary'].get('market_phase', '')
                        if '분배구간 진입 위험' in market_phase:
                            risks.add('분배구간 진입 위험')
                        if '높은 변동성' in analysis['market_summary'].get('volume_analysis', ''):
                            risks.add('높은 변동성')
                    
                    if 'technical_analysis' in analysis:
                        if 'divergence_impact' in analysis['technical_analysis'].get('indicators', {}):
                            risks.add('다이버전스 발생')
                        
                        strength = analysis['technical_analysis'].get('strength', 5)
                        if strength < 3:
                            risks.add('약한 추세 강도')
            
            return list(risks) if risks else ['특별한 리스크 없음']
            
        except Exception as e:
            logger.error(f"리스크 식별 중 오류: {str(e)}")
            return ['리스크 식별 실패']

    def _get_majority_market_phase(self, analyses: Dict) -> str:
        """가장 많이 나타난 시장 단계 반환"""
        phases = []
        for analysis in analyses.values():
            if 'market_summary' in analysis:
                phase = analysis['market_summary'].get('market_phase')
                if phase:
                    phases.append(phase)
        
        if not phases:
            return "불명확"
        
        return Counter(phases).most_common(1)[0][0]

    def _get_overall_sentiment(self, analyses: Dict) -> str:
        """전체적인 시장 심리 분석"""
        sentiments = []
        for analysis in analyses.values():
            if 'market_summary' in analysis:
                sentiment = analysis['market_summary'].get('short_term_sentiment')
                if sentiment:
                    sentiments.append(sentiment)
        
        if not sentiments:
            return "중립"
        
        return Counter(sentiments).most_common(1)[0][0]

    def _get_majority_trend(self, analyses: Dict) -> str:
        """가장 많이 나타난 추세 반환"""
        trends = []
        for analysis in analyses.values():
            if 'technical_analysis' in analysis:
                trend = analysis['technical_analysis'].get('trend')
                if trend:
                    trends.append(trend)
        
        if not trends:
            return "횡보"
        
        return Counter(trends).most_common(1)[0][0]

    def _check_analysis_interval(self, timeframe: str) -> bool:
        """분석 간격 체크"""
        try:
            with open('config/gpt_config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            analysis_interval = config['trading_rules']['trade_limits']['analysis_interval']
            
            current_time = time.time()
            last_analysis_time = self.last_analysis_times.get(timeframe, 0)
            
            min_interval = analysis_interval[timeframe] * 60  # 초로 변환
            if current_time - last_analysis_time < min_interval:
                return False
            
            self.last_analysis_times[timeframe] = current_time
            return True
            
        except Exception as e:
            logger.error(f"분석 간격 체크 중 오류: {str(e)}")
            return True

    def set_trade_manager(self, trade_manager):
        """TradeManager 설정"""
        self.trade_manager = trade_manager
        logger.info("TradeManager가 설정되었습니다")

    def _calculate_confidence(self, analysis: Dict) -> int:
        """분석 결과의 신뢰도 계산"""
        try:
            if not analysis:
                return 50

            confidence = 0
            weight_sum = 0
            
            # 시장 요약의 신뢰도
            if 'market_summary' in analysis:
                market_conf = analysis['market_summary'].get('confidence', 50)
                confidence += market_conf * 0.4  # 40% 가중치
                weight_sum += 0.4
                
            # 기술적 분석의 강도
            if 'technical_analysis' in analysis:
                tech_strength = analysis['technical_analysis'].get('strength', 50)
                confidence += tech_strength * 0.4  # 40% 가중치
                weight_sum += 0.4
                
            # 거래 전략의 신뢰도
            if 'trading_strategy' in analysis:
                if 'auto_trading' in analysis['trading_strategy']:
                    trade_conf = analysis['trading_strategy']['auto_trading'].get('confidence', 50)
                    confidence += trade_conf * 0.2  # 20% 가중치
                    weight_sum += 0.2
            
            # 가중 평균 계산
            if weight_sum > 0:
                final_confidence = int(confidence / weight_sum)
            else:
                final_confidence = 50
                
            return min(100, max(0, final_confidence))  # 0-100 범위로 제한
            
        except Exception as e:
            logger.error(f"신뢰도 계산 중 오류: {str(e)}")
            return 50

    async def execute_trade(self, analysis: Dict, skip_validation: bool = False) -> bool:
        """분석 결과에 따른 거래 실행
        Args:
            analysis: 거래 분석 결과
            skip_validation: True면 자동매매 조건 검증 스킵 (/trade 명령어용)
        """
        try:
            if not skip_validation:
                # 자동매매 조건 검증
                auto_trading = analysis.get('trading_strategy', {}).get('auto_trading', {})
                if not auto_trading.get('enabled'):
                    logger.info(f"자동매매 비활성화됨: {auto_trading.get('reason', '이유 없음')}")
                    return False
            else:
                # /trade 명령어로 실행 시
                if 'trading_strategy' not in analysis:
                    analysis['trading_strategy'] = {}
                if 'auto_trading' not in analysis['trading_strategy']:
                    analysis['trading_strategy']['auto_trading'] = {}
                
                analysis['trading_strategy']['auto_trading'].update({
                    'enabled': True,
                    'confidence': 100,
                    'reason': '수동 실행'
                })

            # 실제 거래 실행
            return await self.trade_manager.execute_trade_signal(analysis)

        except Exception as e:
            logger.error(f"매매 실행 중 오류: {str(e)}")
            return False

    async def run_complete_analysis(self) -> Dict:
        """통합 분석 실행"""
        try:
            # 각 시간대 분석 수집 및 검증
            analyses = {}
            for timeframe in ['15m', '1h', '4h', '1d']:
                analysis = self.storage_formatter.load_analysis(timeframe)
                if not analysis:
                    logger.warning(f"{timeframe} 분석 데이터가 없습니다")
                    continue
                analyses[timeframe] = analysis

            if len(analyses) < 4:
                logger.error("일부 시간대의 분석 데이터가 누락되었습니다")
                return None

            # 현재가 조회
            current_price = await self.market_data_service.get_current_price()
            if not current_price:
                logger.error("현재가 조회 실패")
                return None

            # 최종 분석 실행
            final_analysis = await self.gpt_analyzer.analyze_final(analyses, current_price)
            if not final_analysis:
                logger.error("Final 분석 실패")
                return None

            # 분석 결과 저장
            self.storage_formatter.save_analysis(final_analysis, 'final')
            logger.info("Final 분석 완료 및 저장됨")
            
            return final_analysis
            
        except Exception as e:
            logger.error(f"통합 분석 실행 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    async def execute_auto_trading(self):
        """자동매매 실행"""
        try:
            # final 분석 데이터 로드
            logger.info("=== 자동매매 실행 시도 ===")
            final_analysis = await self._load_analysis_data('final')
            if not final_analysis:
                logger.error("final 분석 데이터가 없습니다")
                return False
            
            # /trade와 동일한 방식으로 실행
            return await self.execute_trade(final_analysis)  # 기존 execute_trade 사용

        except Exception as e:
            logger.error(f"자동매매 실행 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False