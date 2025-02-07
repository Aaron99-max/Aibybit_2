import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from datetime import datetime, timedelta
from typing import List, Dict
from services.trade_history_service import TradeHistoryService
from telegram_bot.formatters.stats_formatter import StatsFormatter
from telegram_bot.handlers.base_handler import BaseHandler

logger = logging.getLogger(__name__)

class StatsHandler(BaseHandler):
    def __init__(self, bot):
        super().__init__(bot)
        self.trade_history_service = bot.trade_history_service
        self.formatter = StatsFormatter()

    async def daily_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """일일 거래 통계 조회"""
        try:
            # 오늘 날짜의 포지션 조회
            today = datetime.now().strftime('%Y%m%d')
            positions = self.trade_history_service.get_daily_positions(today)
            
            # 통계 메시지 생성
            message = self.formatter.format_daily_stats(positions)
            
            # 메시지 전송
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"일일 통계 조회 중 오류: {str(e)}")
            await update.message.reply_text("통계 조회 중 오류가 발생했습니다.")

    async def monthly_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """월간 거래 통계 조회"""
        try:
            # 이번 달 포지션 조회
            current_month = datetime.now().strftime('%Y%m')
            positions = self.trade_history_service.get_monthly_positions(current_month)
            
            # 통계 메시지 생성
            message = self.formatter.format_monthly_stats(positions)
            
            # 메시지 전송
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"월간 통계 조회 중 오류: {str(e)}")
            await update.message.reply_text("통계 조회 중 오류가 발생했습니다.")

    def get_handlers(self):
        """핸들러 리스트 반환"""
        return [
            CommandHandler('daily', self.daily_stats),
            CommandHandler('monthly', self.monthly_stats)
        ]

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """통계 명령어 처리"""
        if not await self.check_admin(update):
            return
            
        try:
            # 기본값 90일
            days = 90
            
            # 인자가 있으면 파싱
            if context.args:
                try:
                    days = int(context.args[0])
                    if days <= 0:
                        raise ValueError
                except ValueError:
                    await self.send_message("올바른 일수를 입력해주세요 (예: /stats 90)", update.effective_chat.id)
                    return

            # 통계 조회
            stats = await self.trade_history_service.get_position_stats(days)
            if not stats:
                await self.send_message(f"최근 {days}일간의 거래 통계가 없습니다.", update.effective_chat.id)
                return

            # 응답 메시지 구성
            message = (
                f"📊 최근 {stats['period']} 거래 통계\n\n"
                f"총 거래 수: {stats['total_trades']}건\n"
                f"승률: {stats['win_rate']}%\n"
                f"총 수익: {stats['total_pnl']} USDT\n"
                f"평균 수익: {stats['avg_pnl']} USDT\n"
            )

            await self.send_message(message, update.effective_chat.id)

        except Exception as e:
            logger.error(f"통계 처리 중 오류: {str(e)}")
            await self.send_message("통계 조회 중 오류가 발생했습니다.", update.effective_chat.id) 