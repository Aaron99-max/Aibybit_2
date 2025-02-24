import asyncio
import logging
import traceback
from typing import Dict, Optional
from datetime import datetime
from ..utils.time_utils import TimeUtils

logger = logging.getLogger(__name__)

class AutoAnalyzer:
    def __init__(self, bot, ai_trader, market_data_service, storage_formatter, analysis_formatter):
        self.bot = bot
        self.ai_trader = ai_trader
        self.market_data_service = market_data_service
        self.storage_formatter = storage_formatter
        self.analysis_formatter = analysis_formatter
        self.time_utils = TimeUtils()
        self._running = False
        self._task = None
        self.last_run = {}

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

    def is_running(self) -> bool:
        return self._running and self._task and not self._task.done()

    async def run_market_analysis(self, timeframe: str, is_auto: bool = False, chat_id: Optional[int] = None):
        """시장 분석 실행 - 자동/수동 분석의 중심 로직"""
        try:
            logger.info(f"=== {timeframe} 분석 시작 ({'자동' if is_auto else '수동'}) ===")
            
            # OHLCV 데이터 조회 및 검증
            klines = await self._get_validated_market_data(timeframe)
            if not klines:
                await self._handle_error(f"{timeframe} 시장 데이터 조회 실패", chat_id)
                return None
            
            # 분석 실행
            analysis = await self._perform_analysis(timeframe, klines)
            if not analysis:
                await self._handle_error(f"{timeframe} 분석 실패", chat_id)
                return None

            # 결과 처리
            await self._handle_analysis_result(analysis, timeframe, chat_id)
            
            return analysis

        except Exception as e:
            logger.error(f"{timeframe} 분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            await self._handle_error(f"{timeframe} 분석 중 오류가 발생했습니다", chat_id)
            return None

    async def _get_validated_market_data(self, timeframe: str):
        """시장 데이터 조회 및 검증"""
        klines = await self.market_data_service.get_ohlcv('BTCUSDT', timeframe)
        if not isinstance(klines, list) or not klines:
            return None
        return klines

    async def _perform_analysis(self, timeframe: str, klines: list):
        """분석 실행"""
        return await self.ai_trader.analyze_market(timeframe, klines)

    async def _handle_analysis_result(self, analysis: dict, timeframe: str, chat_id: Optional[int]):
        """분석 결과 처리"""
        try:
            # 분석 결과 저장
            self.storage_formatter.save_analysis(analysis, timeframe)
            
            # 메시지 전송
            if chat_id:
                message = self.analysis_formatter.format_analysis_result(
                    analysis, timeframe, datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
                )
                await self.bot.send_message(message, chat_id)
            
            # 4시간봉 분석 후 Final 분석 실행
            if timeframe == '4h':
                await asyncio.sleep(1)
                await self.run_final_analysis(chat_id)
            
        except Exception as e:
            logger.error(f"분석 결과 처리 중 오류: {str(e)}")

    async def _handle_error(self, message: str, chat_id: Optional[int]):
        """에러 처리"""
        logger.error(message)
        if chat_id:
            await self.bot.send_message(f"❌ {message}", chat_id)

    async def run_final_analysis(self, chat_id: Optional[int] = None):
        """Final 분석 실행"""
        try:
            logger.info("=== Final 분석 시작 ===")
            
            # 각 시간대 분석 결과 로드
            analyses = {}
            for timeframe in ['15m', '1h', '4h', '1d']:
                analysis = self.storage_formatter.load_analysis(timeframe)
                if analysis:
                    analyses[timeframe] = analysis

            # Final 분석 실행
            final_analysis = await self.ai_trader.analyze_final(analyses)
            if not final_analysis:
                error_msg = "Final 분석 생성 실패"
                logger.error(error_msg)
                if chat_id:
                    await self.bot.send_message(f"❌ {error_msg}", chat_id)
                return None

            # 분석 결과 저장
            self.storage_formatter.save_analysis(final_analysis, 'final')
            
            # 분석 결과 메시지 전송
            if chat_id:
                message = self.analysis_formatter.format_analysis_result(
                    final_analysis, 'final', datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
                )
                await self.bot.send_message(message, chat_id)
            
            # 자동매매 체크
            auto_trading = final_analysis.get('trading_strategy', {}).get('auto_trading', {})
            if auto_trading.get('enabled'):
                await self.ai_trader.execute_auto_trading(final_analysis)
                logger.info("자동매매 신호 처리 완료")
            
            return final_analysis

        except Exception as e:
            logger.error(f"Final 분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            if chat_id:
                await self.bot.send_message("❌ Final 분석 중 오류가 발생했습니다", chat_id)
            return None

    async def run_all_timeframes(self, chat_id: Optional[int] = None):
        """모든 시간대 분석 실행"""
        try:
            for timeframe in ['15m', '1h', '4h', '1d']:
                await self.run_market_analysis(timeframe, chat_id=chat_id)
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"전체 분석 중 오류: {str(e)}")
            if chat_id:
                await self.bot.send_message("❌ 전체 분석 중 오류가 발생했습니다", chat_id)

    async def show_last_analysis(self, timeframe: str, chat_id: int):
        """마지막 분석 결과 조회"""
        try:
            if timeframe == 'all':
                for tf in ['15m', '1h', '4h', '1d', 'final']:
                    await self._show_single_analysis(tf, chat_id)
                    await asyncio.sleep(0.5)
            else:
                await self._show_single_analysis(timeframe, chat_id)
        except Exception as e:
            logger.error(f"분석 결과 조회 중 오류: {str(e)}")
            await self.bot.send_message("❌ 분석 결과 조회 중 오류가 발생했습니다", chat_id)

    async def _show_single_analysis(self, timeframe: str, chat_id: int):
        """단일 시간대 분석 결과 조회"""
        analysis = self.storage_formatter.load_analysis(timeframe)
        if not analysis:
            await self.bot.send_message(f"❌ {timeframe} 분석 결과가 없습니다", chat_id)
            return

        saved_time = self.storage_formatter.get_analysis_time(timeframe)
        message = self.analysis_formatter.format_analysis_result(
            analysis, timeframe, saved_time
        )
        await self.bot.send_message(message, chat_id)

    async def _run(self):
        """자동 분석 실행 루프"""
        try:
            while self._running:
                current_time = datetime.now(self.time_utils.kst_tz)
                
                for timeframe in ['15m', '1h', '4h', '1d']:
                    if self._should_run_timeframe(timeframe, current_time):
                        await self.run_market_analysis(timeframe, is_auto=True)
                        self.last_run[timeframe] = current_time
                
                await asyncio.sleep(60)  # 1분마다 체크
                
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
                    '15m': 14 * 60,  # 14분
                    '1h': 59 * 60,   # 59분
                    '4h': 239 * 60,  # 3시간 59분
                    '1d': 23 * 3600  # 23시간
                }.get(timeframe, 60)
                
                if time_diff < min_interval:
                    return False

            # 실행 시간 확인
            if timeframe == '15m':
                return current_time.minute % 15 == 0
            elif timeframe == '1h':
                return current_time.minute == 0
            elif timeframe == '4h':
                target_hours = [1, 5, 9, 13, 17, 21]  # KST 기준
                should_run = current_time.hour in target_hours and current_time.minute == 0
                if should_run:
                    logger.info(f"4시간봉 분석 실행 예정 - 현재시간(KST): {current_time.strftime('%H:%M')}")
                return should_run
            elif timeframe == '1d':
                return current_time.hour == 1 and current_time.minute == 0  # KST 기준 매일 01:00
            
            return False

        except Exception as e:
            logger.error(f"실행 시간 확인 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False