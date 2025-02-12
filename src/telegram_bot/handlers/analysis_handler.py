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
        """분석 명령어 처리"""
        try:
            if not update.effective_chat:
                return
                
            analysis = await self.auto_analyzer.run_market_analysis(
                is_auto=False, 
                chat_id=update.effective_chat.id
            )
            
            # 매매 신호 변환
            if analysis and analysis.get('trading_signals'):
                signals = analysis['trading_signals']
                position_suggestion = signals.get('position_suggestion', 'HOLD')
                
                # HOLD가 아닐 때만 매매 신호 생성
                if position_suggestion != 'HOLD':
                    analysis['trading_signals'] = {
                        'position_suggestion': '매수' if position_suggestion == 'BUY' else '매도',
                        'leverage': signals.get('leverage', 5),
                        'position_size': signals.get('size', 10),
                        'entry_points': [signals.get('entry_price', 0)],
                        'stopLoss': signals.get('stop_loss', 0),
                        'takeProfit': signals.get('take_profit1', 0),
                        'reason': signals.get('reason', '알 수 없음')  # 사유 추가
                    }
            
            # 알람이 있으면 먼저 보내기
            if analysis and analysis.get('alerts'):
                alert_message = "\n".join(analysis['alerts'])
                await self.bot.send_message(f"⚠️ 알림:\n{alert_message}", update.effective_chat.id)
            
            return analysis
            
        except Exception as e:
            logger.error(f"분석 처리 중 오류: {str(e)}")
            await self.bot.send_message("❌ 분석 중 오류가 발생했습니다.", update.effective_chat.id)

    async def show_timeframe_help(self, chat_id: int):
        """분석 명령어 도움말"""
        help_message = (
            "1시간봉 분석 명령어:\n"
            "/analyze - 현재 시장 분석 실행"
        )
        await self.send_message(help_message, chat_id)
