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
                
            analysis = await self.auto_analyzer.analyze_market(manual=True)
            
            if not analysis:
                return
            
            # 매매 신호 변환
            if analysis and analysis.get('trading_signals'):
                signals = analysis['trading_signals']
                position_suggestion = signals.get('position_suggestion', 'HOLD')
                
                # HOLD가 아닐 때만 매매 신호 생성
                if position_suggestion != 'HOLD':
                    analysis['trading_signals'] = {
                        'position_suggestion': '매수' if position_suggestion == 'BUY' else '매도',
                        'leverage': signals.get('leverage', 5),
                        'position_size': signals.get('position_size', 10),
                        'entry_price': signals.get('entry_price', 0),
                        'stop_loss': signals.get('stop_loss', 0),
                        'take_profit1': signals.get('take_profit1', 0),
                        'reason': signals.get('reason', '알 수 없음')
                    }
            
            return analysis
            
        except Exception as e:
            logger.error(f"분석 처리 중 오류: {str(e)}")

    async def show_timeframe_help(self, chat_id: int):
        """분석 명령어 도움말"""
        help_message = (
            "1시간봉 분석 명령어:\n"
            "/analyze - 현재 시장 분석 실행"
        )
        await self.send_message(help_message, chat_id)
