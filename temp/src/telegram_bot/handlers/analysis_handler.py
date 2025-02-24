import logging
from .base_handler import BaseHandler
from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional

logger = logging.getLogger(__name__)

class AnalysisHandler(BaseHandler):
    def __init__(self, bot, auto_analyzer):
        super().__init__(bot)
        self.auto_analyzer = auto_analyzer

    async def handle_analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """수동 분석 명령어 처리 - 자동분석 로직 재사용"""
        if not await self.check_admin(update):
            return
            
        try:
            if not update.effective_chat:
                return
                
            chat_id = update.effective_chat.id
            
            # 파라미터 검증
            if not context.args or len(context.args) < 1:
                await self.show_timeframe_help(chat_id)
                return
            
            timeframe = context.args[0].lower()
            
            # 자동분석 로직 재사용
            await self._execute_analysis(timeframe, chat_id)
                
        except Exception as e:
            logger.error(f"분석 명령어 처리 중 오류: {str(e)}")
            if update.effective_chat:
                await self.send_message("❌ 분석 중 오류가 발생했습니다", update.effective_chat.id)

    async def _execute_analysis(self, timeframe: str, chat_id: int):
        """분석 실행 - 자동분석 로직 호출"""
        try:
            if timeframe == 'all':
                # 전체 시간대 분석
                await self.auto_analyzer.run_all_timeframes(chat_id)
            elif timeframe == 'final':
                # Final 분석
                await self.auto_analyzer.run_final_analysis(chat_id)
            elif timeframe in ['15m', '1h', '4h', '1d']:
                # 단일 시간대 분석
                await self.auto_analyzer.run_market_analysis(timeframe, chat_id=chat_id)
            else:
                await self.show_timeframe_help(chat_id)
                
        except Exception as e:
            logger.error(f"분석 실행 중 오류: {str(e)}")
            raise

    async def handle_last(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """마지막 분석 결과 조회"""
        if not await self.check_admin(update):
            return
            
        try:
            if not update.effective_chat:
                return
                
            chat_id = update.effective_chat.id
            timeframe = context.args[0].lower() if context.args else None
            
            if not timeframe:
                await self.show_timeframe_help(chat_id)
                return

            await self.auto_analyzer.show_last_analysis(timeframe, chat_id)
                
        except Exception as e:
            logger.error(f"마지막 분석 결과 조회 중 오류: {str(e)}")
            if update.effective_chat:
                await self.send_message("❌ 분석 결과 조회 중 오류가 발생했습니다", update.effective_chat.id)

    async def show_timeframe_help(self, chat_id: int):
        """시간프레임 도움말 표시"""
        help_message = (
            "시간프레임을 지정해주세요:\n"
            "/analyze 15m - 15분 분석\n"
            "/analyze 1h - 1시간봉 분석\n" 
            "/analyze 4h - 4시간봉 분석\n"
            "/analyze 1d - 일봉 분석\n"
            "/analyze final - 최종 분석\n"
            "/analyze all - 전체 분석"
        )
        await self.send_message(help_message, chat_id)
