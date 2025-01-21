import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
import traceback
from services.trade_store import TradeStore
import time
import asyncio

logger = logging.getLogger(__name__)

class TradeHistoryService:
    def __init__(self, bybit_client):
        self.bybit_client = bybit_client
        self.trade_store = TradeStore()
        # 디버그 로거 설정
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

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
            try:
                end_time = int(time.time() * 1000) - (i * 24 * 60 * 60 * 1000)
                start_time = end_time - (7 * 24 * 60 * 60 * 1000)
                cursor = None
                
                while True:  # 페이징 처리를 위한 루프
                    params = {
                        "category": "linear",
                        "limit": 1000,
                        "execType": "Trade",
                        "endTime": end_time,
                        "fields": [
                            "symbol", "side", "price", "size", "execFee",
                            "execRealizedPnl", "execTime", "execValue",
                            "closedSize", "execType", "createType", "leverage",
                            "markPrice", "execPrice", "markIv", "orderPrice",
                            "orderQty", "orderType", "stopOrderType", "leavesQty",
                            "isMaker", "indexPrice", "underlyingPrice", "blockTradeId",
                            "feeCurrency", "feeRate", "tradeIv", "orderId", "orderLinkId",
                            "execQty", "execId", "seq"
                        ]
                    }
                    
                    if cursor:
                        params["cursor"] = cursor
                    
                    batch = await self.bybit_client.fetch_my_trades(
                        symbol="BTCUSDT", 
                        since=start_time,
                        params=params
                    )
                    
                    if not batch:
                        break
                        
                    self.logger.debug(f"조회된 거래: {len(batch)}건")
                    self.logger.debug(f"API 응답 샘플:\n{json.dumps(batch[0], indent=2)}")
                    trades.extend(batch)
                    
                    # 다음 페이지 커서 확인
                    if batch and isinstance(batch[-1].get('info'), dict):
                        cursor = batch[-1]['info'].get('nextPageCursor')
                        if not cursor:
                            break
                    else:
                        break
                    
                    # API 호출 제한을 위한 딜레이
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                self.logger.error(f"거래 조회 중 오류: {str(e)}")
                self.logger.error(traceback.format_exc())
                
        return trades

    async def _save_trades(self, trades: List[Dict]) -> int:
        """거래 내역 저장"""
        saved_count = 0
        for trade in trades:
            # 원본 API 응답 데이터를 포함하여 저장
            trade_data = {
                **trade,
                'raw_info': trade.get('info', {})  # 원본 API 응답 데이터 저장
            }
            if self.trade_store.save_trade(trade_data):
                saved_count += 1
        return saved_count

    async def update_trades(self):
        """새로운 거래 내역 업데이트"""
        try:
            last_update = self.trade_store.get_last_update()
            current_time = int(time.time() * 1000)
            cursor = None
            all_trades = []
            
            while True:  # 페이징 처리를 위한 루프
                params = {
                    "category": "linear",
                    "limit": 1000,
                    "execType": "Trade",
                    "endTime": current_time,
                    "fields": [
                        "symbol", "side", "price", "size", "execFee",
                        "execRealizedPnl", "execTime", "execValue",
                        "closedSize", "execType", "createType", "leverage",
                        "markPrice", "execPrice", "markIv", "orderPrice",
                        "orderQty", "orderType", "stopOrderType", "leavesQty",
                        "isMaker", "indexPrice", "underlyingPrice", "blockTradeId",
                        "feeCurrency", "feeRate", "tradeIv", "orderId", "orderLinkId",
                        "execQty", "execId", "seq"
                    ]
                }
                
                if cursor:
                    params["cursor"] = cursor
                
                new_trades = await self.bybit_client.fetch_my_trades(
                    symbol='BTCUSDT',
                    since=last_update,
                    params=params
                )
                
                if not new_trades:
                    break
                    
                all_trades.extend(new_trades)
                
                # 다음 페이지 커서 확인
                if new_trades and isinstance(new_trades[-1].get('info'), dict):
                    cursor = new_trades[-1]['info'].get('nextPageCursor')
                    if not cursor:
                        break
                else:
                    break
                
                # API 호출 제한을 위한 딜레이
                await asyncio.sleep(0.5)
            
            if all_trades:
                self.logger.debug(f"첫 새 거래 데이터:\n{json.dumps(all_trades[0], indent=2)}")
                await self._save_trades(all_trades)
                self.trade_store.save_last_update(current_time)
                self.logger.info(f"새로운 거래 {len(all_trades)}건 저장")
                
        except Exception as e:
            self.logger.error(f"거래 내역 업데이트 실패: {str(e)}")
            self.logger.error(traceback.format_exc())

    async def load_trades(self, start_time: int = None, end_time: int = None) -> List[Dict]:
        """거래 내역 조회"""
        return self.trade_store.get_trades(start_time, end_time) 