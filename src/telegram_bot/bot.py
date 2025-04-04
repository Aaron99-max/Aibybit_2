import os
import json
import logging
import asyncio
from typing import Dict, Optional
from datetime import datetime
from telegram import Bot, Update
from telegram.constants import ParseMode
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

from ai.gpt_analyzer import GPTAnalyzer
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
from .monitors.monitor_manager import MonitorManager

class TelegramBot:
    # 메시지 타입 정의
    MSG_TYPE_COMMAND = 'command'  # 명령어 응답
    MSG_TYPE_ANALYSIS = 'analysis'  # 분석 결과
    MSG_TYPE_TRADE = 'trade'  # 거래 알림
    MSG_TYPE_SYSTEM = 'system'  # 시스템 알림
    MSG_TYPE_ORDER = 'order'  # 주문 알림
    MSG_TYPE_POSITION = 'position'  # 포지션 알림
    MSG_TYPE_EXECUTION = 'execution'  # 체결 알림

    def __init__(self, config: TelegramConfig, bybit_client: BybitClient, 
                 trade_manager: TradeManager = None,
                 market_data_service: MarketDataService = None):
        self.config = config
        self.bybit_client = bybit_client
        
        # 서비스 초기화 (순서 중요)
        self.position_service = PositionService(bybit_client)
        self.balance_service = BalanceService(bybit_client)
        self.order_service = OrderService(
            bybit_client=bybit_client,
            position_service=self.position_service,
            balance_service=self.balance_service,
            telegram_bot=self
        )
        self.market_data_service = market_data_service or MarketDataService(bybit_client)
        self.trade_history_service = TradeHistoryService(bybit_client)
        
        # 모니터 매니저 초기화
        self.monitor_manager = MonitorManager(self, bybit_client)
        
        # 종료 이벤트 초기화
        self._stop_event = asyncio.Event()
        
        # 포맷터 초기화
        self.storage_formatter = StorageFormatter()
        self.analysis_formatter = AnalysisFormatter()
        self.message_formatter = MessageFormatter()
        self.order_formatter = OrderFormatter()
        
        # 트레이드 매니저 초기화 (수정)
        self.trade_manager = trade_manager or TradeManager(
            order_service=self.order_service
        )
        
        # AI Trader 초기화
        self.ai_trader = AITrader(
            bybit_client=bybit_client,
            market_data_service=self.market_data_service,
            gpt_analyzer=GPTAnalyzer(
                bybit_client=bybit_client,
                market_data_service=self.market_data_service
            ),
            trade_manager=self.trade_manager
        )
        
        # 텔레그램 설정 로드 (수정)
        self.admin_chat_id = config.admin_chat_id
        self.alert_chat_ids = config.alert_chat_ids  # 알림용 채팅방 ID 리스트
        
        # 설정값 로깅 추가
        logger.info("텔레그램 설정 로드:")
        logger.info(f"- admin_chat_id: {self.admin_chat_id}")
        logger.info(f"- alert_chat_ids: {self.alert_chat_ids}")
        
        # Application 초기화
        self.application = Application.builder().token(config.bot_token).build()

        # 모니터링 초기화
        self.auto_analyzer = AutoAnalyzer(
            market_data_service=self.market_data_service,
            gpt_analyzer=self.ai_trader.gpt_analyzer,
            order_service=self.order_service,
            telegram_bot=self
        )
        
        # 핸들러 초기화 (순서 중요)
        self.analysis_handler = AnalysisHandler(
            bot=self,
            auto_analyzer=self.auto_analyzer
        )
        self.system_handler = SystemHandler(self)
        self.stats_handler = StatsHandler(self)
        self.trading_handler = TradingHandler(
            self,
            self.ai_trader,
            self.position_service,
            self.trade_manager,
            self.trade_history_service
        )

    async def send_message_to_all(self, message: str, msg_type: str = None):
        """모든 채팅방에 메시지 전송"""
        try:
            # 관리자 채팅방에는 모든 메시지 전송
            await self.send_message(message, self.admin_chat_id)
            
            # 알림 채팅방에도 모든 메시지 전송 (명령어 응답 제외)
            if msg_type != self.MSG_TYPE_COMMAND:
                for chat_id in self.alert_chat_ids:
                    await self.send_message(message, chat_id)
                    
        except Exception as e:
            logger.error(f"메시지 전송 중 오류: {str(e)}")

    async def send_admin_message(self, message: str, parse_mode: str = 'HTML'):
        """관리자방에만 메시지 전송"""
        try:
            if self.admin_chat_id:
                await self.application.bot.send_message(
                    chat_id=self.admin_chat_id,
                    text=message,
                    parse_mode=parse_mode
                )
                logger.info(f"관리자방({self.admin_chat_id})에 메시지 전송됨")
        except Exception as e:
            logger.error(f"관리자 메시지 전송 실패: {str(e)}")

    async def send_alert_message(self, message: str, parse_mode: str = 'HTML'):
        """알림방에만 메시지 전송"""
        try:
            for chat_id in self.alert_chat_ids:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode=parse_mode
                )
                logger.info(f"알림방({chat_id})에 메시지 전송됨")
        except Exception as e:
            logger.error(f"알림방 메시지 전송 실패: {str(e)}")

    async def initialize(self):
        """봇 초기화"""
        try:
            logger.info("봇 초기화 시작...")
            
            # 거래 내역 서비스 초기화
            await self.trade_history_service.initialize()
            
            # 봇 초기화
            self.application = (
                Application.builder()
                .token(self.config.bot_token)
                .build()
            )
            
            # 명령어 핸들러 등록
            logger.info("명령어 핸들러 등록 시작...")
            
            # 시스템 명령어
            self.application.add_handler(CommandHandler("help", self.system_handler.handle_help))
            self.application.add_handler(CommandHandler("stop", self.system_handler.handle_stop))
            self.application.add_handler(CommandHandler("monitor_start", self.system_handler.handle_start_monitoring))
            self.application.add_handler(CommandHandler("monitor_stop", self.system_handler.handle_stop_monitoring))
            
            # 분석 명령어
            self.application.add_handler(CommandHandler("analyze", self.analysis_handler.handle_analyze))
            
            # 거래 명령어
            self.application.add_handler(CommandHandler("status", self.trading_handler.handle_status))
            self.application.add_handler(CommandHandler("balance", self.trading_handler.handle_balance))
            self.application.add_handler(CommandHandler("position", self.trading_handler.handle_position))
            self.application.add_handler(CommandHandler("trade", self.trading_handler.handle_trade))
            
            # 통계 명령어
            self.application.add_handler(CommandHandler("daily", self.stats_handler.daily_stats))
            self.application.add_handler(CommandHandler("monthly", self.stats_handler.monthly_stats))
            self.application.add_handler(CommandHandler("stats", self.stats_handler.stats))
            
            # 에러 핸들러 등록
            self.application.add_error_handler(self._error_handler)
            
            logger.info("모든 핸들러 등록 완료")
            
            # 봇 초기화 완료
            logger.info("봇 초기화 완료, 시작 준비 중...")
            
        except Exception as e:
            logger.error(f"봇 초기화 실패: {str(e)}")
            raise

    async def start(self):
        """봇 시작"""
        try:
            logger.info("=== 봇 시작 시도 ===")
            
            # 기존 웹훅 제거
            await self.application.bot.delete_webhook()
            
            # 모니터링 시작
            await self.monitor_manager.start_all_monitors()
            
            # 봇 시작 알람 전송
            await self.send_message_to_all("🤖 바이빗 트레이딩 봇이 시작되었습니다", self.MSG_TYPE_SYSTEM)
            
            # 자동 분석기 시작
            await self.auto_analyzer.start()
            
            # 봇 시작
            await self.application.initialize()
            await self.application.start()
            
            # 업데이터 시작
            await self.application.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query"]
            )
            
            # 봇이 실행 중인 동안 대기
            try:
                await self._stop_event.wait()
                logger.info("봇 종료 이벤트 감지됨")
            except asyncio.CancelledError:
                logger.info("봇 실행이 취소되었습니다")
            
        except Exception as e:
            logger.error(f"봇 시작 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    async def stop(self):
        """봇 종료"""
        try:
            logger.info("봇 종료 시작...")
            
            # 1. 텔레그램 봇 종료
            logger.info("텔레그램 봇 종료 중...")
            await self.application.stop()
            await self.application.shutdown()
            
            # 2. 자동 분석기 중지
            logger.info("자동 분석기 종료 중...")
            await self.auto_analyzer.stop()
            
            # 3. 모니터링 중지 (웹소켓 콜백 제거)
            logger.info("모니터링 종료 중...")
            await self.monitor_manager.stop_all_monitors()
            
            # 4. 웹소켓 연결 종료
            logger.info("웹소켓 연결 종료 중...")
            await self.bybit_client.ws_client.stop()
            
            # 5. Bybit 클라이언트 종료
            logger.info("Bybit 클라이언트 종료 중...")
            await self.bybit_client.close()
            
            logger.info("봇이 성공적으로 종료되었습니다")
            
        except Exception as e:
            logger.error(f"봇 종료 중 오류 발생: {str(e)}")
            logger.error(traceback.format_exc())
            raise

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
        """모든 채팅방에 메시지 전송"""
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

    async def send_order_notification(self, message: str):
        """주문 알림 전송"""
        await self.send_message_to_all(message, self.MSG_TYPE_ORDER)

    async def send_position_notification(self, message: str):
        """포지션 알림 전송"""
        await self.send_message_to_all(message, self.MSG_TYPE_POSITION)

    async def send_execution_notification(self, message: str):
        """체결 알림 전송"""
        await self.send_message_to_all(message, self.MSG_TYPE_EXECUTION)

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """도움말 명령어 처리"""
        help_text = """
🤖 사용 가능한 명령어:

🤖 트레이딩 명령어:
/analyze - 1시간봉 시장 분석
/trade - 거래 실행
/status - 현재 상태 확인
/balance - 계좌 잔고 확인
/position - 포지션 조회
/stats - 거래 통계 확인

⚙️ 시스템 명령어:
/stop - 봇 종료
"""
        try:
            if update.effective_chat:
                await self.send_message(help_text, update.effective_chat.id)
                logger.info(f"도움말 메시지 전송 완료 (chat_id: {update.effective_chat.id})")
        except Exception as e:
            logger.error(f"도움말 처리 중 오류: {str(e)}")
            logger.error(traceback.format_exc())

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

    async def _error_handler(self, update: Update, context: CallbackContext):
        """에러 핸들러"""
        logger.error(f"텔레그램 봇 에러: {context.error}")
        logger.error(traceback.format_exc())
        if update and update.effective_chat:
            await self.send_message("❌ 명령어 처리 중 오류가 발생했습니다.", update.effective_chat.id)

    async def run(self):
        """봇 실행"""
        try:
            # 봇 초기화
            await self.initialize()
            
            # 봇 시작
            logger.info("봇 시작 시도...")
            await self.start()
            
        except Exception as e:
            logger.error(f"봇 실행 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            raise
