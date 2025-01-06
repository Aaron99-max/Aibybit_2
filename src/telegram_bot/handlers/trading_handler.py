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
        """잔고 조회"""
        try:
            if not update.effective_chat:
                return
                
            chat_id = update.effective_chat.id
            logger.info(f"[Balance] 잔고 조회 시작 (chat_id: {chat_id})")
            
            balance = await self.balance_service.get_balance()
            if balance:
                message = self.message_formatter.format_balance(balance)
                await self.send_message(message, chat_id)
            else:
                await self.send_message("❌ 잔고 조회 실패", chat_id)
                
        except Exception as e:
            logger.error(f"잔고 조회 중 오류: {str(e)}")
            await self.send_message("❌ 잔고 조회 중 오류가 발했습니다.", chat_id)

    @command_handler
    async def handle_trade(self, update: Update, context: CallbackContext) -> None:
        try:
            if not update.effective_chat:
                return
            
            chat_id = update.effective_chat.id

            # 파라미터 파싱 및 분석 형식으로 변환
            trade_params = self._parse_trade_params(context.args)
            
            # 거래 실행 (GPT final 분석과 동일한 경로 사용)
            result = await self.trade_manager.execute_trade_signal(trade_params)
            
            if result:
                # 성공 메시지만 전송 (주문 알림은 order_service에서 처리)
                await self.send_message("✅ 주문이 성공적으로 실행되었습니다", chat_id)
            else:
                await self.send_message("❌ 거래 신호 실행 실패", chat_id)

        except Exception as e:
            logger.error(f"거래 처리 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            await self.send_message("❌ 오류 발생", chat_id)

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
            
            # 방향 변환 (모든 가능한 입력 처리)
            if direction.lower() in ['long', 'buy', '매수', 'l', 'b']:
                position = '매수'  # trade_manager에서 'Buy'로 변환
            elif direction.lower() in ['short', 'sell', '매도', 's']:
                position = '매도'  # trade_manager에서 'Sell'로 변환
            else:
                raise ValueError("포지션은 'LONG/SHORT/매수/매도'여야 합니다")

            return {
                'trading_strategy': {
                    'position_suggestion': position,
                    'entry_points': [float(entry)],
                    'stop_loss': float(stop),
                    'take_profit': [float(target)],  # 첫 번째 TP만 사용
                    'leverage': int(leverage),
                    'position_size': float(size),
                    'auto_trading': {
                        'enabled': True,
                        'confidence': 85,
                        'reason': '수동 매매 신호'
                    }
                }
            }
            
        except (ValueError, IndexError) as e:
            logger.error(f"거래 파라미터 파싱 오류: {str(e)}")
            raise ValueError(
                "올바른 형식: /trade <LONG|SHORT|매수|매도> <레버리지> <포지션크기> <진입가> <손절가> <익절가>\n"
                "예: /trade LONG 10 5 50000 49000 51000"
            )

    async def handle_trade_command(self, update: Update, context: CallbackContext) -> None:
        """거래 명령어 처리"""
        try:
            # 봇 방(관리자 방)에서만 실행되도록 체크
            chat_id = update.effective_chat.id
            if chat_id != self.bot.admin_chat_id:
                logger.info(f"관리자 방이 아닌 곳에서의 /trade 명령 무시 (chat_id: {chat_id})")
                return
            
            # 기존 코드는 그대로 유지
            message = update.message.text.strip()
            timeframe = self._extract_timeframe(message) or '4h'
            
            result = await self.bot.analysis_handler.handle_analyze_final(chat_id)
            
            # 포지션 크기가 같을 때는 다른 메시지 표시
            if result and not result.get('order_created', True):  # order_created가 False면 포지션 크기가 같은 경우
                await self.bot.send_message(chat_id, "📊 포지션 확인 완료: 현재 포지션이 목표 크기와 동일하여 조정이 필요하지 않습니다.")
        except Exception as e:
            logger.error(f"거래 명령어 처리 중 오류: {str(e)}")
            await self.bot.send_message(chat_id, f"❌ 거래 명령어 처리 중 오류가 발생했습니다: {str(e)}")