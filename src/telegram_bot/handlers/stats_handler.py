import logging
from telegram import Update
from telegram.ext import ContextTypes
from .base_handler import BaseHandler
from datetime import datetime
from ai.trade_analyzer import TradeAnalyzer

logger = logging.getLogger(__name__)

class StatsHandler(BaseHandler):
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """거래 통계 및 패턴 분석 표시"""
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
            analyzer = TradeAnalyzer(self.bot.trade_history_service)
            patterns = await analyzer.analyze_patterns(days=days)
            
            if not patterns:
                await self.send_message("📊 분석할 거래 데이터가 없습니다.", chat_id)
                return

            # 메시지 구성
            message = (
                f"📊 거래 패턴 분석 (최근 {days}일)\n"
                f"──────────────\n\n"
                
                f"💰 수익성 분석\n"
                f"• 총 거래: {patterns['profitable_trades']['count']}건\n"
                f"• 평균 수익: ${patterns['profitable_trades']['avg_profit']:.2f}\n"
                f"• 최고 수익: ${patterns['profitable_trades']['best_profit']:.2f}\n\n"
                
                f"⏰ 시간대별 패턴\n"
                f"• 최적 거래 시간: {', '.join(patterns['time_patterns']['summary']['best_hours'])}\n"
                f"• 해당 시간대 승률: {patterns['time_patterns']['summary']['best_win_rate']:.1f}%\n\n"
                
                f"📏 포지션 크기 분석\n"
                f"• 최적 크기: {patterns['size_patterns']['summary']['size_ranges'][patterns['size_patterns']['summary']['best_size']]}\n"
                f"• ROI: {patterns['size_patterns']['summary']['best_roi']:.2f}%\n\n"
                
                f"📈 가격대별 분석\n"
                f"• 거래 가격대: {patterns['price_patterns']['summary']['price_range']}\n"
                f"• 최적 구간: {patterns['price_patterns']['summary']['best_range']}\n"
                f"• 승률: {patterns['price_patterns']['summary']['best_win_rate']:.1f}%\n\n"
                
                f"⏰ 분석 시간: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
            
            await self.send_message(message, chat_id)
            
        except Exception as e:
            logger.error(f"통계 처리 중 오류: {str(e)}")
            await self.send_message("❌ 통계 조회 중 오류가 발생했습니다", chat_id) 