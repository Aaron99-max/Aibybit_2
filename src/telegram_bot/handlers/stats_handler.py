import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from datetime import datetime, timedelta
from typing import List, Dict
from services.trade_history_service import TradeHistoryService
from telegram_bot.formatters.stats_formatter import StatsFormatter
from telegram_bot.handlers.base_handler import BaseHandler
import traceback
import time

logger = logging.getLogger(__name__)

class StatsHandler(BaseHandler):
    def __init__(self, bot):
        super().__init__(bot)
        self.trade_history_service = bot.trade_history_service
        self.formatter = StatsFormatter()

    async def update_trade_data(self) -> bool:
        """새로운 거래 데이터가 있는지 확인하고 업데이트"""
        try:
            last_stored_time = self.trade_history_service.trade_store.get_last_update()
            current_time = int(time.time() * 1000)  # milliseconds

            # 새로운 데이터가 있는지 확인 (1분 이상 차이나면 업데이트)
            if not last_stored_time or (current_time - last_stored_time) > 60000:
                logger.info("새로운 거래 데이터 조회 시작...")
                await self.trade_history_service.fetch_and_update_positions(
                    start_time=last_stored_time if last_stored_time else current_time - (90 * 24 * 60 * 60 * 1000),
                    end_time=current_time
                )
                logger.info("거래 데이터 업데이트 완료")
                return True
            return False
            
        except Exception as e:
            logger.error(f"거래 데이터 업데이트 실패: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def daily_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """일일 거래 통계 조회"""
        if not await self.check_permission(update):
            return
            
        try:
            # 새로운 데이터 확인 및 업데이트
            if await self.update_trade_data():
                await update.message.reply_text("거래 데이터가 업데이트되었습니다.")
            
            # 오늘 날짜의 포지션 조회
            today = datetime.now().strftime('%Y%m%d')
            positions = self.trade_history_service.trade_store.get_positions(date_str=today)
            
            # 통계 메시지 생성
            message = self.formatter.format_daily_stats(positions)
            
            # 메시지 전송
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"일일 통계 조회 중 오류: {str(e)}")
            await update.message.reply_text("통계 조회 중 오류가 발생했습니다.")

    async def monthly_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """월간 거래 통계 조회"""
        if not await self.check_permission(update):
            return
            
        try:
            # 새로운 데이터 확인 및 업데이트
            if await self.update_trade_data():
                await update.message.reply_text("거래 데이터가 업데이트되었습니다.")
            
            # 이번 달 포지션 조회
            current_month = datetime.now().strftime('%Y%m')
            positions = []
            
            # 이번 달의 모든 일자 데이터 조회
            start_date = datetime.now().replace(day=1)
            end_date = datetime.now()
            current_date = start_date
            
            while current_date <= end_date:
                date_str = current_date.strftime('%Y%m%d')
                daily_positions = self.trade_history_service.trade_store.get_positions(date_str=date_str)
                positions.extend(daily_positions)
                current_date += timedelta(days=1)
            
            # 통계 메시지 생성
            message = self.formatter.format_monthly_stats(positions)
            
            # 메시지 전송
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"월간 통계 조회 중 오류: {str(e)}")
            await update.message.reply_text("통계 조회 중 오류가 발생했습니다.")

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """기간별 거래 통계 조회
        사용법: 
        /stats : 90일 통계
        /stats 30 : 30일 통계
        /stats 90,30,7,1 : 여러 기간 통계
        """
        if not await self.check_permission(update):
            return
            
        try:
            # 새로운 데이터 확인 및 업데이트
            if await self.update_trade_data():
                await update.message.reply_text("거래 데이터가 업데이트되었습니다.")
            
            # 기본값: 90일
            periods = []
            
            # 파라미터 파싱
            if context.args:
                # 쉼표로 구분된 여러 기간
                if ',' in context.args[0]:
                    periods = [int(x.strip()) for x in context.args[0].split(',')]
                # 단일 기간
                else:
                    periods = [int(context.args[0])]
            
            # 기간이 지정되지 않은 경우 90일로 설정
            if not periods:
                periods = [90]
            
            messages = []
            end_date = datetime.now()
            
            for days in periods:
                start_date = end_date - timedelta(days=days)
                
                # 날짜를 문자열로 변환
                start_str = start_date.strftime('%Y%m%d')
                end_str = end_date.strftime('%Y%m%d')
                
                # 해당 기간의 모든 포지션 수집
                positions = []
                current_date = start_date
                
                while current_date <= end_date:
                    date_str = current_date.strftime('%Y%m%d')
                    daily_positions = self.trade_history_service.trade_store.get_positions(date_str=date_str)
                    positions.extend(daily_positions)
                    current_date += timedelta(days=1)
                
                if positions:
                    period_str = f"{days}일" if days > 0 else "전체"
                    stats_message = self._format_period_stats(positions, period_str)
                    messages.append(stats_message)
                else:
                    messages.append(f"\n📊 {days}일 거래 내역이 없습니다.")
            
            # 전체 메시지 조합
            final_message = "\n---\n".join(messages)
            
            # 메시지 전송
            await update.message.reply_text(final_message)
            
        except Exception as e:
            logger.error(f"통계 조회 중 오류: {str(e)}")
            await update.message.reply_text("통계 조회 중 오류가 발생했습니다.")

    def _format_period_stats(self, positions: List[Dict], period: str) -> str:
        """기간별 통계 포맷팅"""
        total_pnl = sum(float(p.get('pnl', 0)) for p in positions)
        winning_trades = len([p for p in positions if float(p.get('pnl', 0)) > 0])
        losing_trades = len([p for p in positions if float(p.get('pnl', 0)) < 0])
        total_trades = len(positions)
        
        # 롱/숏 구분 - position_side 기준으로 분류
        long_positions = [p for p in positions if p.get('position_side') == 'Long']
        short_positions = [p for p in positions if p.get('position_side') == 'Short']
        
        # 각 포지션별 PnL 계산
        long_pnl = sum(float(p.get('pnl', 0)) for p in long_positions)
        short_pnl = sum(float(p.get('pnl', 0)) for p in short_positions)
        
        # 승률 계산
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # 평균 수익/손실
        winning_pnls = [float(p.get('pnl', 0)) for p in positions if float(p.get('pnl', 0)) > 0]
        losing_pnls = [float(p.get('pnl', 0)) for p in positions if float(p.get('pnl', 0)) < 0]
        
        avg_profit = sum(winning_pnls) / len(winning_pnls) if winning_pnls else 0
        avg_loss = sum(losing_pnls) / len(losing_pnls) if losing_pnls else 0
        
        # 최대 수익/손실
        max_profit = max([float(p.get('pnl', 0)) for p in positions]) if positions else 0
        max_loss = min([float(p.get('pnl', 0)) for p in positions]) if positions else 0
        
        message = f"""
📊 {period} 거래 통계

💰 수익 현황:
• 총 수익: ${self.formatter.format_number(total_pnl)}
• 평균 수익: ${self.formatter.format_number(avg_profit)}
• 평균 손실: ${self.formatter.format_number(avg_loss)}
• 최대 수익: ${self.formatter.format_number(max_profit)}
• 최대 손실: ${self.formatter.format_number(max_loss)}

📈 거래 실적:
• 총 거래: {total_trades}회
• 성공: {winning_trades}회
• 실패: {losing_trades}회
• 승률: {self.formatter.format_number(win_rate)}%

🔄 포지션별 실적:
• 롱: {len(long_positions)}회 (${self.formatter.format_number(long_pnl)})
• 숏: {len(short_positions)}회 (${self.formatter.format_number(short_pnl)})
"""
        return message.strip()

    def get_handlers(self):
        """핸들러 리스트 반환"""
        return [
            CommandHandler('daily', self.daily_stats),
            CommandHandler('monthly', self.monthly_stats),
            CommandHandler('stats', self.stats)
        ]