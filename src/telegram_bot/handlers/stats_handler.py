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
            
            # 기간 파라미터 처리 (기본값 30일)
            period = context.args[0].lower() if context.args else "30"
            
            # 숫자로 통계 조회
            try:
                days = int(period)
                if 1 <= days <= 90:
                    stats = await self.bot.trade_history_service.calculate_stats(days=days)
                    period_text = f"최근 {days}일"
                else:
                    await self.send_message("❌ 1~90일 사이의 숫자를 입력해주세요.", chat_id)
                    return
            except ValueError:
                await self.send_message("❌ 올바른 숫자를 입력해주세요. (예: /stats 30)", chat_id)
                return
            
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