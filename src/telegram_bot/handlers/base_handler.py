import logging
from typing import Dict, Optional, Any
import traceback
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

class BaseHandler:
    def __init__(self, bot):
        self.bot = bot

    def _is_admin_chat(self, chat_id: int) -> bool:
        """관리자 채팅방 여부 확인"""
        return chat_id == self.bot.admin_chat_id

    async def send_message(self, message: str, chat_id: int, parse_mode: str = None):
        """모든 채팅방에 메시지 전송"""
        await self.bot.send_message_to_all(message, parse_mode)

    def can_execute_command(self, chat_id: int) -> bool:
        """명령어 실행 권한 확인"""
        return chat_id == self.bot.admin_chat_id

    async def handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """명령어 처리 기본 로직"""
        if not update.effective_chat:
            return
            
        chat_id = update.effective_chat.id
        
        # 관리자 채팅방이 아닌 경우 명령어 무시
        if chat_id != self.bot.admin_chat_id:
            return
        
        try:
            response = await self._process_command(update, context)
            if response:
                await self.send_message(response, chat_id)
        except Exception as e:
            error_msg = f"명령어 처리 중 오류 발생: {str(e)}"
            logger.error(error_msg)
            await self.send_message(error_msg, chat_id)

    def log_error(self, error: Exception, context: str = ""):
        """에러 로깅"""
        error_message = f"{context} 중 오류 발생: {str(error)}"
        logger.error(error_message)
        logger.debug(traceback.format_exc())
        return error_message

    async def handle_error(self, error: Exception, chat_id: int, context: str = ""):
        """에러 처리 및 사용자 알림"""
        error_message = self.log_error(error, context)
        await self.send_message(f"❌ {error_message}", chat_id)

    def validate_timeframe(self, timeframe: Optional[str]) -> bool:
        """시간프레임 유효성 검사"""
        valid_timeframes = ['15m', '1h', '4h', '1d', 'all']
        return timeframe in valid_timeframes

    async def show_timeframe_help(self, chat_id: int):
        """시간프레임 도움말 표시"""
        help_message = (
            "시간프레임을 지정해주세요:\n"
            "/analyze 15m - 15분봉 분석\n"
            "/analyze 1h - 1시간봉 분석\n"
            "/analyze 4h - 4시간봉 분석\n"
            "/analyze 1d - 일봉 분석\n"
            "/analyze all - 전체 분석"
        )
        await self.send_message(help_message, chat_id) 

    async def check_permission(self, update: Update) -> bool:
        """명령어 실행 권한 체크"""
        if not update.effective_chat:
            return False
        
        # 관리자 채팅방에서만 명령어 허용
        return update.effective_chat.id == self.bot.admin_chat_id 