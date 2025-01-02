import logging
from telegram import Update
from telegram.ext import ContextTypes
from .base_handler import BaseHandler
from datetime import datetime

logger = logging.getLogger(__name__)

class StatsHandler(BaseHandler):
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                period_text = "일간"
            elif period == 'weekly':
                stats = await self.bot.trade_history_service.get_weekly_stats()
                period_text = "주간"
            elif period == 'monthly':
                stats = await self.bot.trade_history_service.get_monthly_stats()
                period_text = "월간"
            else:
                stats = await self.bot.trade_history_service.get_current_month_stats()
                period_text = "이번 달"
                
            # 메시지 포맷팅
            message = (
                f"📊 거래 통계 (기간: {period_text})\n"
                f"──────────────\n"
                f"💰 수익률 정보:\n"
                f"• 총 수익: ${stats['total_profit']}\n"
                f"• 최대 수익: ${stats['max_profit']}\n"
                f"• 최대 손실: ${stats['max_loss']}\n"
                f"• 평균 수익: ${stats['average_profit']}\n\n"
                f"📈 거래 정보:\n"
                f"• 총 거래: {stats['total_trades']}회\n"
                f"• 성공: {stats['winning_trades']}회\n"
                f"• 실패: {stats['losing_trades']}회\n"
                f"• 승률: {stats['win_rate']}%\n\n"
                f"⏰ 마지막 업데이트: {datetime.fromisoformat(stats['last_updated']).strftime('%Y-%m-%d %H:%M')}"
            )
            
            await self.send_message(message, chat_id)
            
        except Exception as e:
            logger.error(f"통계 처리 중 오류: {str(e)}")
            await self.send_message("❌ 통계 조회 중 오류가 발생했습니다", chat_id) 