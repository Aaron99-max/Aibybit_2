import logging
import json
import time
from typing import Dict, List, Optional
from collections import Counter
import traceback
import asyncio
import os
from datetime import datetime

from exchange.bybit_client import BybitClient
from services.position_service import PositionService
from services.order_service import OrderService
from services.market_data_service import MarketDataService
from trade.trade_manager import TradeManager
from .gpt_analyzer import GPTAnalyzer
from indicators.technical import TechnicalIndicators
from telegram_bot.formatters.storage_formatter import StorageFormatter
from config.trading_config import trading_config

logger = logging.getLogger(__name__)

class AITrader:
    def __init__(self, bybit_client: BybitClient, 
                 market_data_service: MarketDataService, 
                 gpt_analyzer: GPTAnalyzer,
                 trade_manager: TradeManager = None):
        self.bybit_client = bybit_client
        self.market_data_service = market_data_service
        self.gpt_analyzer = gpt_analyzer
        self.trade_manager = trade_manager
        self.storage_formatter = StorageFormatter()

    async def analyze_market(self, timeframe: str, klines: List) -> Dict:
        """시장 분석 실행"""
        analysis = await self.gpt_analyzer.analyze_market(timeframe, klines)
        if analysis:
            self.storage_formatter.save_analysis(analysis, timeframe)
        return analysis

    def validate_auto_trading(self, analysis: Dict) -> bool:
        """자동매매 조건 검증"""
        # 1시간 분석 기준으로 수정
        confidence = analysis.get('confidence', 0)
        
        return confidence >= trading_config.auto_trading['confidence']['min']

    async def execute_auto_trade(self, analysis: Dict) -> bool:
        """자동매매 실행"""
        if not self.trade_manager:
            logger.warning("trade_manager가 설정되지 않아 자동매매를 실행할 수 없습니다")
            return False
            
        return await self.trade_manager.execute_auto_trade(analysis)