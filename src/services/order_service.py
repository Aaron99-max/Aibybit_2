import logging
import traceback
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
import json
from exchange.bybit_client import BybitClient
import asyncio
from config.trading_config import trading_config
from telegram_bot.formatters.order_formatter import OrderFormatter
from services.position_service import PositionService
from services.balance_service import BalanceService

logger = logging.getLogger('order_service')

class OrderService:
    def __init__(self, bybit_client: BybitClient, position_service: PositionService, 
                 balance_service: BalanceService, telegram_bot=None):
        self.bybit_client = bybit_client
        self.position_service = position_service
        self.balance_service = balance_service
        self.telegram_bot = telegram_bot
        self.order_formatter = OrderFormatter()
        self.symbol = 'BTCUSDT'

    async def handle_trade_signal(self, signal: Dict) -> bool:
        """거래 신호 처리"""
        try:
            # 1. 현재 포지션 확인
            current_position = await self.position_service.get_position(signal['symbol'])
            
            # 2. 포지션 없는 경우 신규 진입
            if not current_position:
                return await self.create_new_position(signal)
                
            # 3. 포지션 있는 경우 관리
            return await self.manage_existing_position(current_position, signal)
            
        except Exception as e:
            logger.error(f"거래 신호 처리 중 오류: {str(e)}")
            return False

    async def create_new_position(self, signal: Dict) -> bool:
        """신규 포지션 생성"""
        try:
            # 레버리지 설정
            await self.set_leverage(signal['leverage'])
            
            # 주문 생성
            order_result = await self.create_order(
                symbol=signal['symbol'],
                side=signal['side'],
                position_size=signal['size'],
                entry_price=signal['entry_price'],
                stopLoss=signal['stopLoss'],
                takeProfit=signal['takeProfit']
            )
            
            return order_result is not None
            
        except Exception as e:
            logger.error(f"신규 포지션 생성 중 오류: {str(e)}")
            return False

    async def manage_existing_position(self, current_position: Dict, signal: Dict) -> bool:
        """기존 포지션 관리"""
        try:
            current_side = current_position['side']
            signal_side = signal['side']
            
            # 같은 방향인 경우 크기 조정
            if current_side == signal_side:
                return await self._adjust_position_size(current_position, signal)
            
            # 반대 방향인 경우 청산 후 재진입
            return await self._reverse_position(current_position, signal)
            
        except Exception as e:
            logger.error(f"포지션 관리 중 오류: {str(e)}")
            return False

    async def create_order(self, **params) -> Optional[Dict]:
        """주문 생성"""
        try:
            order_params = {
                "category": "linear",
                "symbol": params['symbol'],
                "side": params['side'],
                "orderType": "Limit",
                "qty": str(params['position_size']),
                "price": str(params['entry_price']),
                "timeInForce": "GTC",
                "positionIdx": 0,
                "stopLoss": str(params['stopLoss']) if params.get('stopLoss') else None,
                "takeProfit": str(params['takeProfit']) if params.get('takeProfit') else None
            }
            
            result = await self.bybit_client.v5_post("/order/create", order_params)
            
            if result and result.get('retCode') == 0:
                return result.get('result')
            return None
            
        except Exception as e:
            logger.error(f"주문 생성 중 오류: {str(e)}")
            return None

    async def set_leverage(self, leverage: int) -> bool:
        """레버리지 설정"""
        try:
            response = await self.bybit_client.v5_post("/position/set-leverage", {
                "category": "linear",
                "symbol": self.symbol,
                "buyLeverage": str(leverage),
                "sellLeverage": str(leverage)
            })
            return response and response.get('retCode') in [0, 110043]
        except Exception as e:
            logger.error(f"레버리지 설정 중 오류: {str(e)}")
            return False

    async def _adjust_position_size(self, current_position: Dict, signal: Dict) -> bool:
        """포지션 크기 조정"""
        try:
            current_size = float(current_position['size'])
            
            # 잔고 조회로 목표 크기 계산
            balance = await self.balance_service.get_balance()
            if not balance:
                logger.error("잔고 조회 실패")
                return False
                
            available_balance = float(balance['currencies']['USDT']['available_balance'])
            target_value = available_balance * (signal['size'] / 100) * signal['leverage']
            target_size = target_value / float(signal['entry_price'])
            
            # 크기 차이 계산
            size_diff = target_size - current_size
            
            if abs(size_diff) < trading_config.MIN_POSITION_SIZE:
                logger.info(f"크기 차이가 최소 주문 단위보다 작음: {abs(size_diff)}")
                return True

            # 크기 조정 주문
            side = 'Buy' if size_diff > 0 else 'Sell'
            return await self.create_order(
                symbol=signal['symbol'],
                side=side,
                position_size=abs(size_diff),
                entry_price=signal['entry_price'],
                stopLoss=signal.get('stopLoss'),
                takeProfit=signal.get('takeProfit')
            ) is not None

        except Exception as e:
            logger.error(f"포지션 크기 조정 중 오류: {str(e)}")
            return False

    async def _reverse_position(self, current_position: Dict, signal: Dict) -> bool:
        """반대 방향 포지션으로 전환"""
        try:
            # 1. 현재 포지션 청산
            close_side = 'Sell' if current_position['side'] == 'Buy' else 'Buy'
            close_result = await self.create_order(
                symbol=signal['symbol'],
                side=close_side,
                position_size=current_position['size'],
                entry_price=signal['entry_price'],
                reduceOnly=True
            )
            
            if not close_result:
                return False

            # 2. 새로운 포지션 진입
            return await self.create_new_position(signal)

        except Exception as e:
            logger.error(f"포지션 전환 중 오류: {str(e)}")
            return False
