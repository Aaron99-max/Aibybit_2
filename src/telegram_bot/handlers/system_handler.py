import logging
import asyncio
import os
from .base_handler import BaseHandler
from telegram import Update
from telegram.ext import ContextTypes
import traceback
import sys
import signal

logger = logging.getLogger(__name__)

class SystemHandler(BaseHandler):
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """도움말 표시"""
        if not update.effective_chat:
            return
            
        chat_id = update.effective_chat.id
        logger.info(f"도움말 표시 요청 (chat_id: {chat_id})")
        await self.send_message(
            "🤖 바이빗 트레이딩 봇 명령어 안내\n\n"
            "📊 분석 명령어:\n"
            "/analyze [timeframe] - 시장 분석 실행\n"
            "  - 15m, 1h, 4h, 1d, all\n"
            "/last [timeframe] - 마지막 분석 결과 확인\n"
            "  - timeframe 생략시 전체 결과 표시\n\n"
            "💰 거래 정보:\n"
            "/status - 현재 시장 상태\n"
            "/balance - 계정 잔고\n"
            "/position - 현재 포지션\n"
            "/stats [period] - 거래 통계 확인\n"
            "  - daily: 일간 통계\n"
            "  - weekly: 주간 통계\n"
            "  - monthly: 월간 통계\n"
            "  - 생략시 이번 달 전체 통계\n\n"
            "⚙️ 기타 명령어:\n"
            "/help - 도움말\n"
            "/stop - 봇 종료\n"
            "/monitor_start - 모니터링 시작\n"
            "/monitor_stop - 모니터링 중지\n"
            "/cancel - 활성 주문 취소\n\n"
            "📈 거래 통계 예시:\n"
            "/stats daily - 오늘의 거래 통계\n"
            "/stats weekly - 이번 주 거래 통계\n"
            "/stats monthly - 이번 달 거래 통계\n\n"
            "⚙️ 주문 관리:\n"
            "/cancel - 모든 활성 주문 취소\n\n",
            chat_id
        )

    async def handle_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """봇 종료 명령어 처리"""
        try:
            if not update.effective_chat:
                return
            
            chat_id = update.effective_chat.id
            if not self._is_admin_chat(chat_id):
                await self.send_message("⚠️ 관리자만 사용 가능한 명령어입니다", chat_id)
                return

            # 모든 채팅방에 중지 메시지 전송
            await self.bot.send_message_to_all("🔴 바이빗 트레이딩 봇이 중지되었습니다")
            
            # 강제 종료
            os._exit(0)
            
        except Exception as e:
            logger.error(f"봇 종료 중 오류: {str(e)}")
            os._exit(1)

    async def handle_start_monitoring(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """모니터링 시작"""
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