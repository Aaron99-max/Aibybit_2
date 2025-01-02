import os
import json
import logging
import asyncio
from typing import Dict, Optional
from datetime import datetime
from telegram import Bot, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackContext
)
import traceback
import time

# 로거 설정
logger = logging.getLogger(__name__)

from .handlers.analysis_handler import AnalysisHandler
from .handlers.trading_handler import TradingHandler
from .handlers.system_handler import SystemHandler
from .monitors.auto_analyzer import AutoAnalyzer
from .monitors.profit_monitor import ProfitMonitor
from .utils.time_utils import TimeUtils
from .formatters.analysis_formatter import AnalysisFormatter
from .formatters.message_formatter import MessageFormatter
from services.position_service import PositionService
from services.market_data_service import MarketDataService
from services.order_service import OrderService
from config import config
from .handlers.base_handler import BaseHandler
from exchange.bybit_client import BybitClient
from ai.ai_trader import AITrader
from trade.trade_manager import TradeManager
from config.telegram_config import TelegramConfig
from .formatters.storage_formatter import StorageFormatter
from .formatters.order_formatter import OrderFormatter
from services.balance_service import BalanceService
from services.trade_history_service import TradeHistoryService
from .handlers.stats_handler import StatsHandler

class TelegramBot:
    def __init__(self, config, bybit_client):
        self.config = config
        self.bybit_client = bybit_client
        
        # 텔레그램 설정 로드 (한 번만 실행)
        telegram_config = TelegramConfig()
        self.admin_chat_id = telegram_config.admin_chat_id
        self.group_chat_id = telegram_config.group_chat_id
        self.alert_chat_ids = telegram_config.alert_chat_ids
        
        # 서비스 초기화 (순서 중요)
        self.position_service = PositionService(bybit_client)
        self.order_service = OrderService(bybit_client, self)
        self.market_data_service = MarketDataService(bybit_client)
        self.balance_service = BalanceService(bybit_client)
        self.trade_history_service = TradeHistoryService(bybit_client)
        
        # 포맷터 초기화
        self.storage_formatter = StorageFormatter()
        self.analysis_formatter = AnalysisFormatter()
        self.message_formatter = MessageFormatter()
        self.order_formatter = OrderFormatter()
        
        # 트레이드 매니저 초기화
        self.trade_manager = TradeManager(
            bybit_client,
            self.order_service,
            self.position_service,
            self.balance_service,
            self
        )
        
        # AI Trader 초기화
        self.ai_trader = AITrader(
            bybit_client=bybit_client,
            telegram_bot=self,
            order_service=self.order_service,
            position_service=self.position_service,
            trade_manager=self.trade_manager
        )
        
        # Application 초기화
        self.application = Application.builder().token(config.bot_token).build()

    async def send_message_to_all(self, message: str, parse_mode: str = None):
        """알림 채팅방에 메시지 전송"""
        try:
            # 관리자에게만 전송
            if self.admin_chat_id:
                await self.application.bot.send_message(
                    chat_id=self.admin_chat_id,
                    text=message,
                    parse_mode=parse_mode
                )
                        
        except Exception as e:
            logger.error(f"메시지 전송 실패: {str(e)}")
            logger.error(traceback.format_exc())

    async def initialize(self) -> bool:
        """봇 초기화"""
        try:
            logger.info("Application 빌드 시작...")
            await self.application.initialize()
            
            # 거래 내역 초기화
            logger.info("거래 내역 초기화 시작...")
            await self.trade_history_service.initialize()
            
            # 시작 메시지 전송 (모든 채팅방에)
            await self.send_message_to_all("🤖 바이빗 트레이딩 봇이 시작되었습니다!")
            
            # 핸들러 초기화
            logger.info("핸들러 초기화 시작...")
            self._setup_handlers()
            
            # 모니터링 초기화
            logger.info("모니터링 초기화 시작...")
            self.auto_analyzer = AutoAnalyzer(self)
            self.profit_monitor = ProfitMonitor(self)
            
            # 자동 분석 시작
            await self.auto_analyzer.start()
            
            return True
            
        except Exception as e:
            logger.error(f"봇 초기화 중 오류: {str(e)}")
            return False

    def _setup_handlers(self):
        """핸들러 설정"""
        try:
            # 핸들러 초기화
            self.analysis_handler = AnalysisHandler(
                self,
                self.ai_trader,
                self.market_data_service,
                self.storage_formatter,
                self.analysis_formatter
            )
            
            # BaseHandler를 상속받는 핸들러들
            self.system_handler = SystemHandler(self)
            self.stats_handler = StatsHandler(self)  # stats_handler 추가
            self.trading_handler = TradingHandler(
                self,
                self.ai_trader,
                self.position_service,
                self.trade_manager
            )
            
            # 명령어 핸들러 등록
            handlers = [
                CommandHandler("help", self.system_handler.handle_help),
                CommandHandler("stop", self.system_handler.handle_stop),
                CommandHandler("monitor_start", self.system_handler.handle_start_monitoring),
                CommandHandler("monitor_stop", self.system_handler.handle_stop_monitoring),
                CommandHandler("analyze", self.analysis_handler.handle_analyze),
                CommandHandler("last", self.analysis_handler.handle_last),
                CommandHandler("status", self.trading_handler.handle_status),
                CommandHandler("balance", self.trading_handler.handle_balance),
                CommandHandler("position", self.trading_handler.handle_position),
                CommandHandler("stats", self.stats_handler.handle),  # stats 명령어 추가
                CommandHandler("trade", self.trading_handler.handle_trade)
            ]
            
            for handler in handlers:
                self.application.add_handler(handler)
                
            logger.info("핸들러 초기화 완료")
            return True
            
        except Exception as e:
            logger.error(f"핸들러 초기화 중 오류: {str(e)}")
            logger.error(f"오류 상세: {traceback.format_exc()}")
            return False

    async def run(self):
        """봇 실행"""
        try:
            logger.info("봇 초기화 시작...")
            # 봇 초기화
            init_success = await self.initialize()
            if not init_success:
                logger.error("봇 초기화 실패")
                return
            
            logger.info("봇 초기화 완료, 시작 준비 중...")
            
            # 봇 시작
            logger.info("봇 시작 시도...")
            await self.start()
            logger.info("봇 시작 완료")
            
        except Exception as e:
            logger.error(f"봇 실행 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """도움말 명령어 처리"""
        help_text = """
🤖 사 가능한 명령어:

💰 분석 명령어:
/analyze - 현 시장 분석
/last - 마지막 분석 결과 확인

💰 거래 명령어:
/trade - 거래 실행
/status - 현재 상태 확인
/balance - 계좌 잔고 확인
/position - 포지션 조회
/stats - 거래 통계 확인

⚙️ 시스템 명령어:
/monitor_start - 자동 모니터링 시작
/monitor_stop - 자동 모니터링 중지
/stop - 봇 종료
"""
        try:
            if update.effective_chat:
                await self.send_message(help_text, update.effective_chat.id)
                logger.info(f"도움말 메시지 전송 완료 (chat_id: {update.effective_chat.id})")
        except Exception as e:
            logger.error(f"도움말 처리 중 오류: {str(e)}")
            logger.error(traceback.format_exc())

    async def _handle_last(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """마지막 분석 결과 조회"""
        timeframe = context.args[0] if context.args else None
        if timeframe in self.last_analysis_results:
            await self.send_analysis(self.last_analysis_results[timeframe], timeframe)
        else:
            await self.send_message("❌ 저장된 분석 결과가 없습니다.", update.effective_chat.id)

    async def _handle_status(self, update: Update, context: CallbackContext):
        """현재 상태 조회"""
        if not update.effective_chat:
            return
        await self.trading_handler.handle_status(update.effective_chat.id, context)

    async def _handle_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """잔고 조회"""
        if not update.effective_chat:
            return
        await self.trading_handler.handle_balance(update.effective_chat.id)

    async def _handle_position(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """포지션 조회"""
        if not update.effective_chat:
            return
        await self.trading_handler.handle_position(update.effective_chat.id)

    async def _handle_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """거래 통계 조회"""
        if not update.effective_chat:
            return
        await self.trading_handler.handle_stats(update.effective_chat.id)

    async def start(self):
        """봇 시작"""
        try:
            logger.info("=== 봇 시작 시도 ===")
            # 종료 이벤트 생성
            self._stop_event = asyncio.Event()
            
            # 기존 웹훅 제거
            await self.application.bot.delete_webhook()
            
            # 봇 시작
            await self.application.start()
            
            # 모니터링 시작
            await self.application.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query"]
            )
            
            logger.info("=== 봇이 성공적으로 시작되었습니다 ===")
            
            # 봇이 실행 중인 동안 대기
            try:
                await self._stop_event.wait()
            except asyncio.CancelledError:
                logger.info("봇 실행이 취소되었습니다")
            
        except Exception as e:
            logger.error(f"봇 시작 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    async def _error_handler(self, update: Update, context: CallbackContext):
        """에러 핸들러"""
        logger.error(f"텔레그램 봇 에러: {context.error}")
        logger.error(traceback.format_exc())
        if update and update.effective_chat:
            await self.send_message("❌ 명령어 처리 중 오류가 발생했습니다.", update.effective_chat.id)

    async def stop(self):
        """봇 종료"""
        try:
            logger.info("봇 종료 시작...")
            
            # 모든 작업 중지
            if hasattr(self, 'auto_analyzer'):
                await self.auto_analyzer.stop()
            if hasattr(self, 'profit_monitor'):
                await self.profit_monitor.stop()
            
            # Application 종료
            if hasattr(self, 'application'):
                await self.application.stop()
                await self.application.shutdown()
            
            # Bybit 클라이언트 종료    
            if self.bybit_client:
                await self.bybit_client.close()
            
            logger.info("봇이 성공적으로 종료되었습니다")
            
        except Exception as e:
            logger.error(f"봇 종료 중 오류: {str(e)}")

    async def send_to_admin(self, message: str):
        """관리자에게 메시지 전송"""
        try:
            if self.admin_chat_id:
                await self.application.bot.send_message(
                    chat_id=self.admin_chat_id,
                    text=message,
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            logger.error(f"관리자 메시지 전송 실패: {str(e)}")

    async def send_to_group(self, message: str):
        """단체방 메시지 전송 메서드 제거 또는 관리자에게 전송"""
        await self.send_message_to_all(message)

    async def send_message(self, message: str, chat_id: int, parse_mode: str = None):
        """특정 채팅방에 메시지 전송"""
        try:
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=parse_mode
            )
        except Exception as e:
            logger.error(f"메시지 전송 실패 (chat_id: {chat_id}): {str(e)}")
