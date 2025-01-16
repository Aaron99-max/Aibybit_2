import logging
from .base_handler import BaseHandler
import traceback
from telegram import Update
from telegram.ext import ContextTypes, CallbackContext
from functools import wraps
from trade.trade_manager import TradeManager
from config.trading_config import TradingConfig
from ..formatters.order_formatter import OrderFormatter
from ..formatters.message_formatter import MessageFormatter
import os
from typing import Dict, List
from services.balance_service import BalanceService
from ..formatters.position_formatter import PositionFormatter
import asyncio

# 로거 설정 수정
logger = logging.getLogger('trading_handler')

# 핸들러가 이미 있으면 추가하지 않음
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

def command_handler(func):
    """명령어 핸들러 데코레이터"""
    @wraps(func)
    async def wrapper(self, update: Update, context: CallbackContext, *args, **kwargs):
        try:
            return await func(self, update, context, *args, **kwargs)
        except Exception as e:
            logger.error(f"명령어 처리 중 오류: {str(e)}")
            if update.effective_chat:
                await self.send_message("❌ 명령어 처리 중 오류가 발생했습니다", update.effective_chat.id)
    return wrapper

class TradingHandler(BaseHandler):
    def __init__(self, bot, ai_trader, position_service, trade_manager):
        super().__init__(bot)
        self.ai_trader = ai_trader
        self.position_service = position_service
        self.trade_manager = trade_manager
        self.market_data_service = bot.market_data_service
        self.balance_service = BalanceService(bot.bybit_client)
        self.message_formatter = MessageFormatter()

    def _is_admin_chat(self, chat_id: int) -> bool:
        """관리자 채팅방 여부 확인"""
        return chat_id == self.bot.admin_chat_id

    async def handle_position(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """포지션 조회 명령어 처리"""
        if not await self.check_admin(update):
            return
        try:
            if not update.effective_chat:
                return
            
            chat_id = update.effective_chat.id
            # 관리자만 명령어 실행 가능
            if not self.can_execute_command(chat_id):
                return
                
            logger.info(f"[Position] 포지션 조회 시작 (chat_id: {chat_id})")

            positions = await self.position_service.get_positions('BTCUSDT')
            logger.info(f"[Position] 포지션 조회 결과: {positions}")

            if positions:
                position = positions[0]
                # PositionFormatter 사용하여 메시지 포맷팅
                message = PositionFormatter.format_position(position)
                await self.send_message(message, chat_id)
            else:
                await self.send_message("�� 활성화된 포지션이 없습니다", chat_id)

        except Exception as e:
            logger.error(f"[Position] 포지션 조회 중 오류: {str(e)}")
            await self.send_message("❌ 포지션 조회 중 오류가 발생했습니다", chat_id)

    async def _format_and_send_position(self, position: dict, chat_id: int):
        """포지션 정보 포맷팅 및 전송"""
        try:
            message = f"""
🔍 현재 포지션 정보:

• 심볼: {position.get('symbol', 'N/A')}
• 방향: {position.get('side', 'N/A')}
• 크기: {position.get('size', position.get('contracts', 'N/A'))}
• 레버리지: {position.get('leverage', 'N/A')}x
• 진입가: ${float(position.get('entryPrice', 0)):,.2f}
• 마크가격: ${float(position.get('markPrice', 0)):,.2f}
• 미현 손익: ${float(position.get('unrealizedPnl', 0)):,.2f}
"""
            logger.info(f"포맷팅된 메시지:\n{message}")
            await self.send_message(message, chat_id)
            return True
        except Exception as e:
            logger.error(f"포지션 정보 포맷팅/전송 중 오류: {str(e)}")
            return False

    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """현재 상태 조회"""
        try:
            if not update.effective_chat:
                return
            
            chat_id = update.effective_chat.id
            # 관리자 채팅방이 아니면 조용히 시
            if chat_id != self.bot.admin_chat_id:
                return

            logger.info(f"[Status] 상태 조회 시작 (chat_id: {chat_id})")
            
            # 시장 데이터 조회
            market_data = await self.market_data_service.get_market_data('BTCUSDT')
            
            # 봇 상태 정보
            bot_status = {
                'auto_analyzer': self.bot.auto_analyzer.is_running(),
                'profit_monitor': self.bot.profit_monitor.is_running()
            }
            
            # 시지 포맷팅
            message = self.bot.message_formatter.format_status(
                market_data=market_data,
                bot_status=bot_status
            )
            
            # 한 번만 전송
            await self.send_message(message, chat_id)
            logger.info("[Status] 상태 전송 완료")
            
        except Exception as e:
            logger.error(f"[Status] 상태 조회 중 오류: {str(e)}")
            await self.send_message("❌ 상태 조회 중 오류가 발생했습니다", chat_id)

    async def handle_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """잔고 조회 명령어 처리"""
        try:
            chat_id = update.effective_chat.id
            logger.info(f"[Balance] 잔고 조회 시작 (chat_id: {chat_id})")
            
            balance = await self.balance_service.get_balance()
            if balance:
                message = self.message_formatter.format_balance(balance)
                # 모든 알림방에 전송
                await self.bot.send_message_to_all(message)
            else:
                await self.bot.send_message("❌ 잔고 조회 실패", chat_id)
                
        except Exception as e:
            logger.error(f"잔고 조회 중 오류: {str(e)}")
            if update.effective_chat:
                await self.bot.send_message("❌ 잔고 조회 중 오류가 발생했습니다", update.effective_chat.id)

    @command_handler
    async def handle_trade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """수동 거래 명령 처리"""
        try:
            trade_params = self._parse_trade_params(context.args)
            result = await self.trade_manager.execute_trade(trade_params)
            
            if result:
                await self.send_message("✅ 주문이 성공적으로 실행되었습니다", chat_id)
            else:
                await self.send_message("❌ 거래 신호 실행 실패", chat_id)
                
        except Exception as e:
            logger.error(f"거래 처리 중 오류: {str(e)}")

    def set_market_data_service(self, market_data_service):
        """MarketDataService 설정"""
        self.market_data_service = market_data_service

    async def _process_trade_signal(self, trade_params: Dict, chat_id: int) -> None:
        """거래 신호 처리 공통 로직"""
        try:
            # OrderService의 검증 로직 호출
            validation_result = self.position_service.order_service._validate_sl_tp(
                price=trade_params['trading_strategy']['entry_points'][0],
                stop_loss=trade_params['trading_strategy']['stop_loss'],
                take_profit=trade_params['trading_strategy']['take_profit'][0],
                side='buy' if trade_params['trading_strategy']['position_suggestion'] == '매수' else 'sell'
            )
            
            if not validation_result:
                await self.send_message("❌ TP/SL 검증 실패", chat_id)
                return

            # 거래 신호 포맷팅 및 전송
            order_params = {
                'direction': trade_params['trading_strategy']['position_suggestion'],
                'leverage': trade_params['trading_strategy']['leverage'],
                'size': trade_params['trading_strategy']['position_size'],
                'entry_price': float(trade_params['trading_strategy']['entry_points'][0]),
                'stop_loss': float(trade_params['trading_strategy']['stop_loss']),
                'take_profit': float(trade_params['trading_strategy']['take_profit'][0])
            }
            
            message = await self.bot.order_formatter.format_order_info(
                order_params,
                self.bot.bybit_client
            )
            await self.send_message(message, chat_id)
            
            # 거래 실행
            result = await self.trade_manager.execute_trade_signal(trade_params)
            
            if result:
                await self.send_message("✅ 거래 신호 실행 완료", chat_id)
            else:
                await self.send_message("❌ 거래 신호 실행 실패", chat_id)
                
        except Exception as e:
            logger.error(f"거래 처리 중 오류: {str(e)}")
            await self.send_message("❌ 오류 발생", chat_id)

    def _parse_trade_params(self, args: List[str]) -> Dict:
        """거래 파라미터 파싱"""
        try:
            if len(args) < 6:
                raise ValueError("필수 파라미터 부족")
            
            direction, leverage, size, entry, stop, target = args
            
            if direction.lower() in ['long', 'buy', '매수', 'l', 'b']:
                side = 'Buy'
            elif direction.lower() in ['short', 'sell', '매도', 's']:
                side = 'Sell'
            else:
                raise ValueError("포지션은 'LONG/SHORT/매수/매도'여야 합니다")

            return {
                'side': side,
                'leverage': int(leverage),
                'size': float(size),
                'entry_price': float(entry),
                'stopLoss': float(stop),
                'takeProfit': float(target),
                'symbol': 'BTCUSDT'
            }
            
        except (ValueError, IndexError) as e:
            logger.error(f"거래 파라미터 파싱 오류: {str(e)}")
            raise ValueError(
                "올바른 형식: /trade <LONG|SHORT> <레버리지> <포지션크기> <진입가> <손절가> <익절가>\n"
                "예: /trade LONG 10 5 50000 49000 51000"
            )