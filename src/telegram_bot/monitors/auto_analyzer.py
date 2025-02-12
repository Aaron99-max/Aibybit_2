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
        
        # timeframe 파라미터는 이제 필요 없음 (항상 1h 사용)
        self.timeframe = '1h'  # 고정값으로 설정

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

    async def run_market_analysis(self, is_auto: bool = False, chat_id: Optional[int] = None):
        """1시간봉 시장 분석 실행"""
        try:
            # 분석 시작 알림 (모든 알림방에 전송)
            await self.bot.send_message_to_all(
                f"🔄 1시간봉 {'자동' if is_auto else '수동'} 분석 시작 ...",
                self.bot.MSG_TYPE_ANALYSIS
            )
            
            logger.info(f"🔄' 1시간봉 분석 시작 ({'자동' if is_auto else '수동'}) ...")
            
            # OHLCV 데이터 조회 및 검증
            klines = await self._get_validated_market_data('1h')
            if not klines:
                await self._handle_error("시장 데이터 조회 실패", chat_id)
                return None
            
            # 분석 실행
            analysis = await self.ai_trader.analyze_market('1h', klines)
            if not analysis:
                await self._handle_error("분석 실패", chat_id)
                return None

            # 메시지 전송 (항상 모든 알림방에 전송)
            message = self.analysis_formatter.format_analysis_result(analysis, '1h')
            if message:
                await self.bot.send_message_to_all(message, self.bot.MSG_TYPE_ANALYSIS)
            else:
                logger.error("분석 결과 포맷팅 실패")
            
            # 매매 신호가 있으면 자동 매매 실행
            logger.info(f"분석 결과 trading_signals: {analysis.get('trading_signals', {})}")
            if analysis.get('trading_signals', {}).get('position_suggestion'):
                logger.info("매매 신호 감지, 자동 매매 실행")
                trade_result = await self.ai_trader.trade_manager.execute_auto_trade(analysis)
                if trade_result:
                    await self.bot.send_message_to_all("🤖 자동 매매 실행 완료", self.bot.MSG_TYPE_TRADE)
                else:
                    await self.bot.send_message_to_all("⚠️ 자동 매매 실행 실패", self.bot.MSG_TYPE_TRADE)
            else:
                logger.info("매매 신호 없음")
            
            return analysis

        except Exception as e:
            logger.error(f"분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            await self._handle_error("분석 중 오류가 발생했습니다", chat_id)
            return None

    async def _get_validated_market_data(self, timeframe: str):
        """시장 데이터 조회 및 검증"""
        klines = await self.market_data_service.get_ohlcv('BTCUSDT', timeframe)
        if not isinstance(klines, list) or not klines:
            return None
        return klines

    async def _handle_error(self, message: str, chat_id: Optional[int]):
        """에러 처리"""
        logger.error(message)
        if chat_id:
            await self.bot.send_message(f"❌ {message}", chat_id)

    async def _run(self):
        """자동 분석 실행 루프"""
        try:
            while self._running:
                current_time = datetime.now(self.time_utils.kst_tz)
                
                # 1시간마다 분석 실행
                if self._should_run_analysis(current_time):
                    await self.run_market_analysis(is_auto=True)
                    self.last_run['1h'] = current_time
                
                await asyncio.sleep(60)  # 1분마다 체크
                
        except asyncio.CancelledError:
            logger.info("자동 분석 태스크가 취소되었습니다")
        except Exception as e:
            logger.error(f"자동 분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())

    def _should_run_analysis(self, current_time: datetime) -> bool:
        """1시간봉 분석 실행 조건 확인"""
        try:
            # 마지막 실행 시간 체크
            last_run = self.last_run.get('1h')
            if last_run:
                if last_run.tzinfo is None:
                    last_run = self.time_utils.kst_tz.localize(last_run)
                
                time_diff = (current_time - last_run).total_seconds()
                if time_diff < 59 * 60:  # 59분
                    return False

            # 정시에 실행
            return current_time.minute == 0
            
        except Exception as e:
            logger.error(f"실행 시간 확인 중 오류: {str(e)}")
            return False