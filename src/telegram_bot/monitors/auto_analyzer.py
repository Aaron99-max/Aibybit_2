import asyncio
import logging
import time
import traceback
from typing import Dict
from datetime import datetime, timedelta
import pandas as pd
from telegram_bot.utils.time_utils import TimeUtils

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
            # 마지막 실행 시간 확인
            last_run = self.last_run.get(timeframe)
            if last_run:
                # last_run이 naive datetime인 경우 KST로 변환
                if last_run.tzinfo is None:
                    last_run = self.time_utils.kst_tz.localize(last_run)
                
                time_diff = (current_time - last_run).total_seconds()
                min_interval = {
                    '15m': 14 * 60,  # 14분
                    '1h': 59 * 60,   # 59분
                    '4h': 239 * 60,  # 3시간 59분
                    '1d': 23 * 3600  # 23시간
                }.get(timeframe, 60)
                
                if time_diff < min_interval:
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
            logger.info(f"{timeframe} 자동 분석 시작")
            
            # OHLCV 데이터 조회
            klines = await self.bot.market_data_service.get_ohlcv('BTCUSDT', timeframe)
            if not klines:
                logger.error(f"{timeframe} 시장 데이터 조회 실패")
                return
            
            # DataFrame 변환
            df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # GPTAnalyzer를 통한 분석 실행
            analysis = await self.bot.ai_trader.gpt_analyzer.analyze_market(timeframe, df)
            if not analysis:
                logger.error(f"{timeframe} 분석 실패")
                return
            
            # 분석 결과 저장 및 처리
            self.bot.storage_formatter.save_analysis(analysis, timeframe)
            await self.bot.analysis_handler.handle_analysis_result(
                analysis=analysis,
                timeframe=timeframe,
                chat_id=None  # 모든 채팅방에 전송
            )
            
            # 4시간봉 분석인 경우 Final 분석 실행
            if timeframe == '4h':
                await self._run_final_analysis(analysis)
            
        except Exception as e:
            logger.error(f"{timeframe} 분석 중 오류: {str(e)}")

    async def _run_final_analysis(self, h4_analysis):
        """Final 분석 실행"""
        try:
            if hasattr(self, '_final_analysis_running') and self._final_analysis_running:
                logger.debug("Final 분석이 이미 실행 중입니다")
                return
            
            self._final_analysis_running = True
            try:
                # 각 시간대 분석 결과 검증
                analyses = {}
                for timeframe in ['15m', '1h', '4h', '1d']:
                    analysis = self.bot.storage_formatter.load_analysis(timeframe)
                    if not analysis:
                        logger.warning(f"{timeframe} 분석 데이터가 없습니다")
                        continue
                    analyses[timeframe] = analysis

                if len(analyses) < 4:
                    logger.error("일부 시간대의 분석 데이터가 누락되었습니다")
                    return

                # 통합 분석 실행
                final_analysis = await self.bot.ai_trader.run_complete_analysis()
                if not final_analysis:
                    logger.error("Final 분석 실패")
                    return

                # 분석 결과 저장 및 전송
                self.bot.storage_formatter.save_analysis(final_analysis, 'final')
                await self.bot.analysis_handler.handle_analysis_result(
                    analysis=final_analysis,
                    timeframe='final',
                    chat_id=None
                )
                
            finally:
                self._final_analysis_running = False
            
        except Exception as e:
            logger.error(f"Final 분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())

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