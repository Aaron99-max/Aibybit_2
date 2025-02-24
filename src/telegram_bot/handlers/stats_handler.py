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
import asyncio

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
            positions = self.trade_history_service.trade_store.get_positions(today)
            
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
            positions = []
            
            # 이번 달의 모든 일자 데이터 조회
            start_date = datetime.now().replace(day=1)
            end_date = datetime.now()
            current_date = start_date
            
            while current_date <= end_date:
                date_str = current_date.strftime('%Y%m%d')
                daily_positions = self.trade_history_service.trade_store.get_positions(date_str)
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
        """최근 거래 통계 조회"""
        try:
            # CCXT로 간단하게 시도
            trades = await self.bot.bybit_client.exchange.fetch_my_trades(
                symbol="BTCUSDT",
                limit=50
            )
            
            # 로깅 추가
            logger.info(f"CCXT 응답: {trades[0] if trades else None}")
            
            # 실패하면 직접 API 호출
            if not trades:
                params = {
                    "category": "linear",
                    "symbol": "BTCUSDT",
                    "limit": "50",
                    "orderFilter": "Order"  # 이 파라미터 추가
                }
                
                response = await self.bot.bybit_client._request('GET', '/execution/list', params)
                
                if response and response.get('retCode') == 0:
                    trades = response.get('result', {}).get('list', [])

            if not trades:
                await update.message.reply_text("최근 거래 내역이 없습니다.")
                return

            # 통계 계산
            total_pnl = sum(float(t.get('closedPnl', 0)) for t in trades)
            winning_trades = len([t for t in trades if float(t.get('closedPnl', 0)) > 0])
            total_trades = len(trades)
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            message = f"""
📊 최근 거래 통계

💰 수익 현황:
• 총 수익: ${total_pnl:.2f}
• 총 거래: {total_trades}회
• 성공: {winning_trades}회
• 승률: {win_rate:.1f}%
"""
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"통계 조회 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            await update.message.reply_text("통계 조회 중 오류가 발생했습니다.")

    def _format_period_stats(self, positions: List[Dict], period: str) -> str:
        """기간별 통계 포맷팅"""
        total_pnl = sum(float(p['pnl']) for p in positions)
        winning_trades = len([p for p in positions if float(p['pnl']) > 0])
        losing_trades = len([p for p in positions if float(p['pnl']) < 0])
        total_trades = len(positions)
        
        # 롱/숏 구분 (position_side가 없으면 side로 계산)
        long_positions = [p for p in positions if p['side'] == 'Sell']  # Sell = Long
        short_positions = [p for p in positions if p['side'] == 'Buy']  # Buy = Short
        
        long_pnl = sum(float(p['pnl']) for p in long_positions)
        short_pnl = sum(float(p['pnl']) for p in short_positions)
        
        # 승률 계산
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # 평균 수익/손실
        winning_pnls = [float(p['pnl']) for p in positions if float(p['pnl']) > 0]
        losing_pnls = [float(p['pnl']) for p in positions if float(p['pnl']) < 0]
        
        avg_profit = sum(winning_pnls) / len(winning_pnls) if winning_pnls else 0
        avg_loss = sum(losing_pnls) / len(losing_pnls) if losing_pnls else 0
        
        # 최대 수익/손실
        max_profit = max([float(p['pnl']) for p in positions]) if positions else 0
        max_loss = min([float(p['pnl']) for p in positions]) if positions else 0
        
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

    async def analyze_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """거래 통계 분석"""
        try:
            # 데이터 로드
            positions = self.trade_history_service.trade_store.load_positions()
            logger.info(f"=== 포지션 분석 시작 ===")
            logger.info(f"원본 데이터 수: {len(positions)}")
            
            # 롱/숏 구분
            long_positions = [p for p in positions if p['side'] == 'Sell']  # Sell = Long
            short_positions = [p for p in positions if p['side'] == 'Buy']  # Buy = Short
            
            logger.info(f"롱 포지션: {len(long_positions)}")
            logger.info(f"숏 포지션: {len(short_positions)}")
            
            # 통계 메시지 생성
            message = self.formatter.format_stats(positions)
            
            # 메시지 전송
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"통계 분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            await update.message.reply_text("통계 분석 중 오류가 발생했습니다.") 