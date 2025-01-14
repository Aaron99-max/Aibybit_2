import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
import traceback
from services.trade_store import TradeStore
import time

logger = logging.getLogger(__name__)

class TradeHistoryService:
    def __init__(self, bybit_client):
        self.bybit_client = bybit_client
        self.trade_store = TradeStore()

    async def initialize(self):
        """초기 거래 내역 조회 및 저장"""
        try:
            existing_trades = self.trade_store.get_all_trades()
            if existing_trades:
                logger.info(f"저장된 거래 기록: {len(existing_trades)}건")
                return
            
            trades = await self._fetch_historical_trades()
            await self._save_trades(trades)
            
        except Exception as e:
            logger.error(f"거래 내역 초기화 실패: {str(e)}")

    async def _fetch_historical_trades(self) -> List[Dict]:
        """90일치 거래 내역 조회"""
        trades = []
        for i in range(0, 90, 7):
            end_time = int(time.time() * 1000) - (i * 24 * 60 * 60 * 1000)
            start_time = end_time - (7 * 24 * 60 * 60 * 1000)
            
            batch = await self.bybit_client.fetch_my_trades(
                symbol="BTCUSDT", 
                since=start_time,
                params={"category": "linear", "limit": 1000}
            )
            if batch:
                trades.extend(batch)
        return trades

    async def _save_trades(self, trades: List[Dict]) -> int:
        """거래 내역 저장"""
        saved_count = 0
        for trade in trades:
            if self.trade_store.save_trade(trade):
                saved_count += 1
        return saved_count

    async def update_trades(self):
        """새로운 거래 내역 업데이트"""
        try:
            last_update = self.trade_store.get_last_update()
            current_time = int(time.time() * 1000)
            
            new_trades = await self.bybit_client.fetch_my_trades(
                symbol='BTCUSDT',
                since=last_update
            )
            
            if new_trades:
                await self._save_trades(new_trades)
                self.trade_store.save_last_update(current_time)
                logger.info(f"새로운 거래 {len(new_trades)}건 저장")
                
        except Exception as e:
            logger.error(f"거래 내역 업데이트 실패: {str(e)}")

    async def load_trades(self, start_time: int = None, end_time: int = None) -> List[Dict]:
        """거래 내역 조회"""
        return self.trade_store.get_trades(start_time, end_time) 