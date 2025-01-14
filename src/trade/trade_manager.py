import logging
import traceback
from typing import Dict, TYPE_CHECKING
from config.trading_config import trading_config

if TYPE_CHECKING:
    from services.order_service import OrderService

logger = logging.getLogger('trade_manager')

class TradeManager:
    def __init__(self, order_service: 'OrderService'):
        self.order_service = order_service
        self.symbol = trading_config.symbol

    async def execute_trade(self, params: Dict) -> bool:
        """일반 거래 실행 (수동 거래)"""
        return await self.order_service.handle_trade_signal(params)

    async def execute_auto_trade(self, analysis: Dict) -> bool:
        """자동매매 실행"""
        strategy = analysis.get('trading_strategy', {})
        
        signal = {
            'side': 'Buy' if strategy['position_suggestion'] == '매수' else 'Sell',
            'leverage': strategy['leverage'],
            'size': strategy['position_size'],
            'entry_price': strategy['entry_points'][0],
            'stopLoss': strategy.get('stopLoss'),
            'takeProfit': strategy.get('takeProfit'),
            'symbol': self.symbol
        }
        
        return await self.order_service.handle_trade_signal(signal)