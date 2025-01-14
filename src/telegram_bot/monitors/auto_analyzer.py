import asyncio
import logging
import time
import traceback
from typing import Dict, List
from datetime import datetime, timedelta
import pandas as pd
from telegram_bot.utils.time_utils import TimeUtils
from pytz import timezone
import json

logger = logging.getLogger(__name__)

class AutoAnalyzer:
    def __init__(self, telegram_bot):
        self.bot = telegram_bot
        self._running = False
        self._task = None
        self.last_run = {}  # 각 시간대별 마지막 실행 시간 저장
        self.time_utils = TimeUtils()  # TimeUtils 인스턴스 추가
        
    def is_running(self) -> bool:
        """현재 실행 상태 반환"""
        return self._running and self._task and not self._task.done()
        
    async def start(self):
        """자동 분석 시작"""
        if self.is_running():
            logger.info("자동 분석이 이미 실행 중입니다")
            return
            
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("자동 분석 시작됨")
        
    async def stop(self):
        """자동 분석 중지"""
        if not self.is_running():
            return
            
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("자동 분석 중지됨")

    async def _run(self):
        """자동 분석 실행 루프"""
        try:
            while self._running:
                # 현재 시간을 KST로 설정
                current_time = datetime.now(self.time_utils.kst_tz)
                
                # 현재 시간 로깅
                logger.debug(f"현재 시간: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                
                for timeframe in ['15m', '1h', '4h', '1d']:
                    should_run = self._should_run_timeframe(timeframe, current_time)
                    logger.debug(f"{timeframe} 분석 실행 여부: {should_run}")
                    
                    if should_run:
                        await self._run_analysis(timeframe)
                        # last_run도 timezone 정보를 포함하여 저장
                        self.last_run[timeframe] = current_time
                
                # 다음 분까지 대기
                next_minute = (current_time + timedelta(minutes=1)).replace(second=0, microsecond=0)
                wait_seconds = (next_minute - current_time).total_seconds()
                await asyncio.sleep(wait_seconds)
                
        except asyncio.CancelledError:
            logger.info("자동 분석 태스크가 취소되었습니다")
        except Exception as e:
            logger.error(f"자동 분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            
    def _should_run_timeframe(self, timeframe: str, current_time: datetime) -> bool:
        """각 시간대별 실행 조건 확인"""
        try:
            # 마지막 실행 시간 체크
            last_run = self.last_run.get(timeframe)
            if last_run:
                if last_run.tzinfo is None:
                    last_run = self.time_utils.kst_tz.localize(last_run)
                
                time_diff = (current_time - last_run).total_seconds()
                min_interval = {
                    '15m': 14 * 60,
                    '1h': 59 * 60,
                    '4h': 239 * 60,
                    '1d': 23 * 3600
                }.get(timeframe, 60)
                
                if time_diff < min_interval:
                    # logger.info(f"{timeframe} 분석 스킵: 마지막 실행 후 {time_diff:.6f}초 경과")
                    return False

            # 실행 시간 확인
            if timeframe == '15m':
                should_run = current_time.minute % 15 == 0
            elif timeframe == '1h':
                should_run = current_time.minute == 0
            elif timeframe == '4h':
                target_hours = [1, 5, 9, 13, 17, 21]
                should_run = current_time.hour in target_hours and current_time.minute == 0
                logger.info(f"4시간봉 체크 - 현재시간(KST): {current_time.strftime('%H:%M')}, "
                           f"실행여부: {should_run}")
            elif timeframe == '1d':
                should_run = current_time.hour == 1 and current_time.minute == 0
            else:
                should_run = False

            if should_run:
                logger.info(f"[AutoAnalyzer] {timeframe} 분석 실행 예정 "
                           f"(현재시간: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')})")
            
            return should_run

        except Exception as e:
            logger.error(f"실행 시간 확인 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False
        
    async def _run_analysis(self, timeframe: str):
        """시간대별 분석 실행"""
        try:
            logger.info(f"=== {timeframe} 분석 시작 ===")
            
            # OHLCV 데이터 조회
            klines = await self.bot.market_data_service.get_ohlcv('BTCUSDT', timeframe)
            if not klines:
                logger.error(f"{timeframe} 시장 데이터 조회 실패")
                return
            
            # 분석 실행
            analysis = await self.bot.ai_trader.analyze_market(timeframe, klines)
            if analysis:
                # 분석 결과 처리 (저장 + 알림)
                await self.bot.analysis_handler.handle_analysis_result(analysis, timeframe)
                logger.info(f"{timeframe} 분석 결과 처리 완료")
                
                # 4시간봉 분석이 완료되면 final 분석 실행
                if timeframe == '4h':
                    logger.info("=== Final 분석 시작 ===")
                    final_analysis = await self._run_final_analysis(analysis)
                    if final_analysis:
                        # Final 분석 결과도 처리 (저장 + 알림)
                        await self.bot.analysis_handler.handle_analysis_result(final_analysis, 'final')
                        logger.info("Final 분석 결과 처리 완료")
            else:
                logger.error(f"{timeframe} 분석 실패")
                
        except Exception as e:
            logger.error(f"{timeframe} 분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())

    async def _run_final_analysis(self, h4_analysis):
        try:
            # 각 시간대 분석 결과 검증
            analyses = {}
            for timeframe in ['15m', '1h', '4h', '1d']:
                analysis = self.bot.storage_formatter.load_analysis(timeframe)
                if not analysis:
                    logger.warning(f"{timeframe} 분석 데이터가 없습니다")
                    continue
                analyses[timeframe] = analysis

            # Final 분석 실행
            final_analysis = await self.bot.ai_trader.analyze_final(analyses)
            if not final_analysis:
                logger.error("Final 분석 생성 실패")
                return None

            # 저장
            self.bot.storage_formatter.save_analysis(final_analysis, 'final')
            
            # 자동매매 체크 추가
            auto_trading = final_analysis.get('trading_strategy', {}).get('auto_trading', {})
            if auto_trading.get('enabled'):
                await self.bot.ai_trader.execute_auto_trading(final_analysis)
                logger.info("자동매매 신호 처리 완료")
            
            return final_analysis

        except Exception as e:
            logger.error(f"Final 분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def _should_run_analysis(self, timeframe: str) -> bool:
        """분석 실행 여부 확인"""
        try:
            now = datetime.now(self.time_utils.kst_tz)  # KST 시간대 명시적 사용
            logger.info(f"분석 시간 체크 - timeframe: {timeframe}, 현재시간: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            if timeframe == '15m':
                # 15분마다
                return now.minute % 15 == 0
                
            elif timeframe == '1h':
                # 정시마다
                return now.minute == 0
                
            elif timeframe == '4h':
                target_hours = [1, 5, 9, 13, 17, 21]
                should_run = now.hour in target_hours and now.minute == 0
                logger.info(f"4시간봉 체크 - 시간: {now.hour}시 {now.minute}분 (KST), target_hours: {target_hours}, 실행여부: {should_run}, 호출스택: {traceback.extract_stack()[-3:-1]}")
                return should_run
                
            elif timeframe == '1d':
                # 매일 오전 1시
                return now.hour == 1 and now.minute == 0
                
            return False
            
        except Exception as e:
            logger.error(f"분석 실행 시간 확인 중 오류: {str(e)}")
            return False

    async def run(self):
        """자동 분석 실행"""
        try:
            while True:
                now = datetime.now()
                
                # 각 시간대별 분석 실행
                for timeframe in ['15m', '1h', '4h', '1d']:
                    if self._should_run_analysis(timeframe):
                        logger.info(f"{timeframe} 자동 분석 시작")
                        analysis = await self._run_timeframe_analysis(timeframe)
                        
                        # 4시간봉 분석 후 Final 분석 실행
                        if timeframe == '4h' and analysis:
                            await self._run_final_analysis(analysis)
                
                await asyncio.sleep(60)  # 1분마다 체크
                
        except Exception as e:
            logger.error(f"자동 분석 실행 중 오류: {str(e)}")

    async def _run_timeframe_analysis(self, timeframe: str):
        """시간대별 분석 실행"""
        try:
            # 실행 소스 추적을 위한 로깅
            stack = traceback.extract_stack()
            caller = stack[-2]  # 호출한 함수 정보
            logger.info(f"=== {timeframe} 분석 시작 ===")
            logger.info(f"호출 위치: {caller.filename}:{caller.lineno} in {caller.name}")

            # OHLCV 데이터 조회
            klines = await self.market_data_service.get_ohlcv('BTCUSDT', timeframe)
            if not klines:
                logger.error(f"{timeframe} OHLCV 데이터 조회 실패")
                return None

            # 분석 실행
            analysis = await self.bot.ai_trader.analyze_market(timeframe, klines)
            if analysis:
                logger.info(f"{timeframe} 분석 완료")
                return analysis
            else:
                logger.error(f"{timeframe} 분석 실패")
                return None

        except Exception as e:
            logger.error(f"{timeframe} 분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    async def check_and_execute(self):
        """4시간봉 분석 실행 체크"""
        try:
            current_time = datetime.now(timezone('Asia/Seoul'))
            current_hour = current_time.hour
            
            # 정시에만 실행 (분이 0일 때)
            if current_time.minute != 0:
                logger.info(f"4시간봉 체크 - 현재시간(KST): {current_hour:02d}:{current_time.minute:02d}, 실행여부: False")
                return
            
            # 4시간봉 실행 시간 (1, 5, 9, 13, 17, 21시)
            if current_hour not in [1, 5, 9, 13, 17, 21]:
                logger.info(f"4시간봉 체크 - 현재시간(KST): {current_hour:02d}:00, 실행여부: False")
                return
            
            logger.info(f"4시간봉 분석 시작 - 현재시간(KST): {current_hour:02d}:00")
            await self.analyzer.analyze_market('4h')
        except Exception as e:
            logger.error(f"4시간봉 분석 실행 체크 중 오류: {str(e)}")

    async def handle_final_analysis(self, analysis_result):
        try:
            logger.info("\n=== Final 분석 처리 시작 ===")
            logger.info(f"입력 분석 결과: {json.dumps(analysis_result, indent=2)}")
            
            # Final 분석 생성
            final_analysis = await self.ai_trader.create_final_analysis(analysis_result)
            logger.info(f"Final 분석 생성 결과: {json.dumps(final_analysis, indent=2)}")
            
            if final_analysis:
                # 자동매매 조건 확인
                auto_trading = final_analysis.get('trading_strategy', {}).get('auto_trading', {})
                logger.info(f"자동매매 설정: {json.dumps(auto_trading, indent=2)}")
                
                if auto_trading.get('enabled'):
                    logger.info("자동매매 실행 시도")
                    trade_result = await self.ai_trader.execute_auto_trading(final_analysis)
                    logger.info(f"자동매매 실행 결과: {trade_result}")
                else:
                    logger.info(f"자동매매 조건 미충족: {auto_trading.get('reason', '이유 없음')}")
        except Exception as e:
            logger.error(f"Final 분석 처리 중 오류: {str(e)}")
            logger.error(traceback.format_exc())

    def _get_majority_sentiment(self, sentiments: List[str]) -> str:
        """시장 심리 분석 결과 중 다수결 판단"""
        try:
            if not sentiments:
                return '중립'

            sentiment_count = {
                '긍정적': sentiments.count('긍정적'),
                '부정적': sentiments.count('부정적'),
                '중립': sentiments.count('중립')
            }

            return max(sentiment_count.items(), key=lambda x: x[1])[0]

        except Exception as e:
            logger.error(f"시장 심리 분석 중 오류: {str(e)}")
            return '중립'

    async def process_trading_signal(self, analysis_data: Dict):
        try:
            signal = {
                'side': 'Buy' if analysis_data['position_suggestion'] == '매수' else 'Sell',
                'leverage': analysis_data['leverage'],
                'size': analysis_data['position_size'],
                'entry_price': analysis_data['entry_points'][0],
                'stopLoss': analysis_data['stopLoss'],
                'takeProfit': analysis_data['takeProfit'],
                'symbol': 'BTCUSDT'
            }
            
            result = await self.trade_manager.execute_trade(signal)
            return result
            
        except Exception as e:
            logger.error(f"트레이딩 신호 처리 중 오류: {str(e)}")
            return False

    def _get_majority_volume_trend(self, analyses: Dict) -> str:
        """거래량 트렌드의 다수결 판단"""
        try:
            volume_trends = [
                analysis.get('market_summary', {}).get('volume_trend', '보통')
                for analysis in analyses.values()
            ]
            
            trend_count = {
                '증가': volume_trends.count('증가'),
                '감소': volume_trends.count('감소'),
                '보통': volume_trends.count('보통')
            }
            
            return max(trend_count.items(), key=lambda x: x[1])[0]
        except Exception as e:
            logger.error(f"거래량 트렌드 분석 중 오류: {str(e)}")
            return '보통'

    async def _create_trading_signal(self, analysis_result: Dict) -> Dict:
        """매매 신호 생성"""
        try:
            primary_signal = analysis_result.get('trading_signals', {}).get('primary_signal', {})
            
            return {
                'symbol': 'BTCUSDT',
                'side': primary_signal.get('action'),  # 'Buy' or 'Sell'
                'leverage': int(primary_signal.get('recommended_leverage', 5)),
                'size': float(primary_signal.get('position_size', 0)),
                'entry_price': float(primary_signal.get('entry_price', 0)),
                'stopLoss': float(primary_signal.get('stopLoss', 0)),
                'takeProfit': float(primary_signal.get('takeProfit')[0]) if isinstance(primary_signal.get('takeProfit'), list) else float(primary_signal.get('takeProfit', 0)),
                'confidence': float(analysis_result.get('신도', 0)),
                'timeframe': analysis_result.get('timeframe', '4h')
            }
        except Exception as e:
            logger.error(f"매매 신호 생성 중 오류: {str(e)}")
            return None

    def _get_analysis_prompt(self, timeframe: str) -> str:
        """시간대별 분석 프롬프트 생성"""
        return f"""
비트코인 {timeframe} 차트를 분석하여 다음 형식으로 응답해주세요:

{{
  "market_summary": {{
    "market_phase": "상승" 또는 "하락",
    "overall_sentiment": "긍정적" 또는"부정적",
    "short_term_sentiment": "긍정적" 또는 "부정적",
    "risk_level": "높음" 또는 "중간" 또는 "낮음",
    "volume_trend": "증가" 또는 "감소" 또는 "중립",
    "confidence": 0-100 사이의 숫자
  }},
  "technical_analysis": {{
    "trend": "상승" 또는 "하락",
    "strength": 0-100 사이의 숫자,
    "indicators": {{
      "rsi": 0-100 사이의 숫자,
      "macd": "상승" 또는 "하락",
      "bollinger": "상단" 또는 "중단" 또는 "하단"
    }}
  }},
  "trading_strategy": {{
    "entry_points": [진입가격],
    "leverage": 1-5 사이의 정수,
    "position_size": 10-30 사이의 숫자,
    "position_suggestion": "매수" 또는 "매도" 또는 "관망",
    "takeProfit": [목표가1, 목표가2],
    "stopLoss": 손절가
  }}
}}
"""

    async def _analyze_market(self, timeframe: str, data: Dict) -> Dict:
        """시장 분석 수행"""
        try:
            prompt = self._get_analysis_prompt(timeframe)
            response = await self.gpt_client.generate(prompt)
            
            if not response:
                logger.error("GPT 응답 없음")
                return None
                
            analysis = self.gpt_client._parse_json_response(response)
            if not analysis:
                logger.error("분석 결과 파싱 실패")
                return None
                
            return analysis
            
        except Exception as e:
            logger.error(f"시장 분석 중 오류: {str(e)}")
            return None

    def _calculate_confidence(self, analyses: Dict) -> float:
        """각 시간대 분석의 신뢰도 계산"""
        try:
            total_confidence = 0
            total_weight = 0
            
            for timeframe, weight in self.TIMEFRAME_WEIGHTS.items():
                if timeframe in analyses:
                    confidence = analyses[timeframe].get('market_summary', {}).get('confidence', 50)
                    total_confidence += confidence * weight
                    total_weight += weight
            
            return round(total_confidence / total_weight if total_weight > 0 else 50)
            
        except Exception as e:
            logger.error(f"신뢰도 계산 중 오류: {str(e)}")
            return 50

    def _combine_market_summaries(self, analyses: Dict) -> Dict:
        """시장 요약 데이터 통합"""
        try:
            bullish_count, total_weight = self._calculate_weighted_bullish_score(analyses)
            
            # 4시봉과 15분봉 데이터를 활용
            four_hour = analyses.get('4h', {}).get('market_summary', {})
            fifteen_min = analyses.get('15m', {}).get('market_summary', {})
            
            # 신뢰도 계산을 별도 메소드로 분리
            confidence = self._calculate_confidence(analyses)
            
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

    async def analyze_and_trade(self):
        """4시간 자동 분석 및 거래"""
        try:
            # 1. 시장 분석
            analyses = await self.ai_trader.analyze_market(...)
            
            # 2. 최종 분석
            final_analysis = await self.ai_trader.create_final_analysis(analyses)
            
            # 3. 자동매매 조건 검증
            if self.ai_trader.validate_auto_trading(final_analysis):
                # 4. 거래 실행
                await self.trade_manager.execute_auto_trade(final_analysis)
                
        except Exception as e:
            logger.error(f"자동 분석 실행 중 오류: {str(e)}")