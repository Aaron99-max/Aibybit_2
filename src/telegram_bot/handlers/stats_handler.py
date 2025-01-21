import logging
from telegram import Update
from telegram.ext import ContextTypes
from .base_handler import BaseHandler
from datetime import datetime, timedelta
from ai.trade_analyzer import TradeAnalyzer
from telegram_bot.formatters.stats_formatter import StatsFormatter

logger = logging.getLogger(__name__)

class StatsHandler(BaseHandler):
    def __init__(self, bot):
        super().__init__(bot)
        self.trade_analyzer = TradeAnalyzer(self.bot.trade_history_service.trade_store)
        self.stats_formatter = StatsFormatter()

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """거래 통계 및 패턴 분석 표시"""
        if not await self.check_admin(update):
            return
            
        try:
            if not update.effective_chat:
                return
                
            chat_id = update.effective_chat.id
            
            # 기간 파라미터 처리 (기본값 30일)
            period = context.args[0].lower() if context.args else "30"
            
            try:
                days = int(period)
                if not (1 <= days <= 90):
                    await self.send_message("❌ 1~90일 사이의 숫자를 입력해주세요.", chat_id)
                    return
            except ValueError:
                await self.send_message("❌ 올바른 숫자를 입력해주세요. (예: /stats 30)", chat_id)
                return

            # 거래 분석 실행
            analysis_result = await self.trade_analyzer.analyze_trades()
            if not analysis_result:
                await self.send_message("📊 분석할 거래 데이터가 없습니다.", chat_id)
                return

            # 포맷팅된 메시지 전송
            formatted_stats = self.stats_formatter.format_stats(analysis_result)
            await self.send_message(formatted_stats, chat_id)

        except Exception as e:
            logger.error(f"통계 처리 중 오류: {str(e)}")
            await self.send_message("❌ 통계 조회 중 오류가 발생했습니다", chat_id) 