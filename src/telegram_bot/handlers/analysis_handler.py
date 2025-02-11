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
        """1시간봉 분석 명령어 처리"""
        if not await self.check_admin(update):
            return
            
        try:
            if not update.effective_chat:
                return
                
            chat_id = update.effective_chat.id
            
            # 1시간봉 분석 실행
            await self.auto_analyzer.run_market_analysis(is_auto=False, chat_id=chat_id)
                
        except Exception as e:
            logger.error(f"분석 명령어 처리 중 오류: {str(e)}")
            if update.effective_chat:
                await self.send_command_response("❌ 분석 중 오류가 발생했습니다", update.effective_chat.id)

    async def show_timeframe_help(self, chat_id: int):
        """분석 명령어 도움말"""
        help_message = (
            "1시간봉 분석 명령어:\n"
            "/analyze - 현재 시장 분석 실행"
        )
        await self.send_message(help_message, chat_id)
