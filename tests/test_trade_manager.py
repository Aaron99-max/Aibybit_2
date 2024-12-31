import pytest
import asyncio
import os
from typing import Dict
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

pytestmark = pytest.mark.asyncio

class TestTradeManager:
    @pytest.fixture
    async def setup(self):
        """테스트 환경 설정"""
        # 기존 코드 그대로 사용
        from config import Config
        from exchange.bybit_client import BybitClient
        from trade.trade_manager import TradeManager
        
        config = Config()
        client = BybitClient(config)
        trade_manager = TradeManager(client, config)
        trade_manager.enable_test_mode()
        
        return trade_manager, client

    async def test_simple_trade(self, setup):
        """간단한 거래 테스트"""
        trade_manager, client = await setup
        
        # 단순 매수 테스트
        test_params = {
            'direction': 'long',
            'leverage': 5,
            'size': 10,
            'entry_price': 37000,  # 현재가 근처로 설정
            'stop_loss': 36500,
            'take_profit': 38000
        }
        
        result = await trade_manager.execute_test_trade(test_params)
        assert result is True, "거래 실행 실패" 