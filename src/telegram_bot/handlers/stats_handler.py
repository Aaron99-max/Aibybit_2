import logging
from telegram import Update
from telegram.ext import ContextTypes
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)

class StatsHandler(BaseHandler):
    async def handle_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """통계 정보 표시"""
        try:
            if not update.effective_chat:
                return
                
            chat_id = update.effective_chat.id
            
            # 기간 파라미터 처리
            period = None
            if context.args:
                period = context.args[0].lower()
                
            # 통계 데이터 조회
            if period == 'daily':
                stats = await self.bot.trade_history_service.get_daily_stats()
            elif period == 'weekly':
                stats = await self.bot.trade_history_service.get_weekly_stats()
            elif period == 'monthly':
                stats = await self.bot.trade_history_service.get_monthly_stats()
            else:
                stats = await self.bot.trade_history_service.get_current_month_stats()
                
            # 포맷팅 및 메시지 전송
            message = self.bot.stats_formatter.format_stats(stats)
            await self.send_message(message, chat_id)
            
        except Exception as e:
            logger.error(f"통계 처리 중 오류: {str(e)}")
            await self.handle_error(e, chat_id, "통계 조회") 