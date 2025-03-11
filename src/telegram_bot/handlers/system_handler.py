import logging
import asyncio
import os
from .base_handler import BaseHandler
from telegram import Update
from telegram.ext import ContextTypes
import traceback
import signal

logger = logging.getLogger(__name__)

class SystemHandler(BaseHandler):
    def _is_admin_chat(self, chat_id: int) -> bool:
        """관리자 채팅방 여부 확인"""
        return chat_id == self.bot.admin_chat_id

    def is_admin(self, chat_id: int) -> bool:
        """관리자 권한 확인"""
        return chat_id == self.telegram_bot.config.admin_chat_id

    async def check_permission(self, update: Update) -> bool:
        """관리자 권한 체크"""
        logger.info("check_permission 시작")
        if not update.effective_chat:
            logger.error("check_permission: effective_chat이 없음")
            return False
            
        chat_id = update.effective_chat.id
        is_admin = self._is_admin_chat(chat_id)
        logger.info(f"check_permission: chat_id={chat_id}, is_admin={is_admin}")
        
        if not is_admin:
            await self.send_message("⚠️ 관리자만 사용 가능한 명령어입니다", chat_id)
            
        return is_admin

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """도움말 표시"""
        if not await self.check_permission(update):
            return
        help_text = """
🤖 사용 가능한 명령어:

💰 거래 통계:
/stats [period] - 거래 통계 확인
  - daily: 일간 통계
  - weekly: 주간 통계
  - monthly: 월간 통계
  - 생략시 이번 달 전체 통계

💰 거래 명령어:
/trade - 거래 실행
/status - 현재 상태 확인
/balance - 계좌 잔고 확인
/position - 포지션 조회

📊 분석 명령어:
/analyze - 현재 시장 분석
/last - 마지막 분석 결과 확인

⚙️ 시스템 명령어:
/monitor_start - 자동 모니터링 시작
/monitor_stop - 자동 모니터링 중지
/stop - 봇 종료
"""
        await self.send_message(help_text, update.effective_chat.id)

    async def handle_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """봇 종료 명령어 처리"""
        if not await self.check_permission(update):
            return
            
        try:
            if not update.effective_chat:
                return
                
            chat_id = update.effective_chat.id
            logger.info(f"봇 종료 요청 (chat_id: {chat_id})")

            # 모든 채팅방에 중지 메시지 전송
            await self.bot.send_message_to_all("🔴 바이빗 트레이딩 봇이 중지되었습니다")
            
            # 강제 종료
            logger.info("프로세스 종료")
            os._exit(0)
            
        except Exception as e:
            logger.error(f"봇 종료 중 오류: {str(e)}")
            os._exit(1)

    async def handle_start_monitoring(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """모니터링 시작"""
        if not await self.check_permission(update):
            return
            
        try:
            if not update.effective_chat:
                return

            chat_id = update.effective_chat.id
            logger.info(f"모니터링 시작 요청 (chat_id: {chat_id})")

            # 자동 분석기 시작
            if not self.bot.auto_analyzer.is_running():
                await self.bot.auto_analyzer.start()

            # 수익 모니터 시작
            if not self.bot.profit_monitor.is_running():
                await self.bot.profit_monitor.start()

            await self.send_message("✅ 모니터링이 시작되었습니다.", chat_id)

        except Exception as e:
            logger.error(f"모니터링 시작 중 오류: {str(e)}")
            await self.send_message("❌ 모니터링 시작 실패", chat_id)

    async def handle_stop_monitoring(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """모니터링 중지"""
        if not await self.check_permission(update):
            return
            
        try:
            if not update.effective_chat:
                return

            chat_id = update.effective_chat.id
            logger.info(f"모니터링 중지 요청 (chat_id: {chat_id})")

            # 자동 분석기 중지
            if self.bot.auto_analyzer.is_running():
                await self.bot.auto_analyzer.stop()

            # 수익 모니터 중지
            if self.bot.profit_monitor.is_running():
                await self.bot.profit_monitor.stop()

            await self.send_message("✅ 모니터링이 중지되었습니다.", chat_id)

        except Exception as e:
            logger.error(f"모니터링 중지 중 오류: {str(e)}")
            await self.send_message("❌ 모니터링 중지 실패", chat_id)

    async def handle_cancel_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """활성 주문 취소"""
        try:
            if not update.effective_chat:
                return
            
            chat_id = update.effective_chat.id
            logger.info(f"주문 취소 요청 (chat_id: {chat_id})")
            
            # 모든 활성 주문 취소
            result = await self.bot.trade_manager.cancel_all_orders()
            
            if result:
                await self.send_message("✅ 모든 활성 주문이 취소되었습니다.", chat_id)
            else:
                await self.send_message("❌ 주문 취소 실패 또는 취소할 주문이 없습니다.", chat_id)
            
        except Exception as e:
            logger.error(f"주문 취소 중 오류: {str(e)}")
            await self.send_message("❌ 주문 취소 처리 중 오류가 발생했습니다.", chat_id)