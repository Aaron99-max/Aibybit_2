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
        """거래 내역 서비스"""
        self.bybit_client = bybit_client
        self.trade_store = TradeStore()
        
    async def initialize(self):
        """초기 거래 내역 조회 및 저장"""
        try:
            # 1. 저장된 거래 기록 확인
            existing_trades = self.trade_store.get_all_trades()
            if existing_trades:
                logger.info(f"저장된 거래 기록: {len(existing_trades)}건")
                return
            
            # 2. API에서 거래 내역 가져오기
            trades = []
            # 7일 단위로 나누어 조회
            for i in range(0, 90, 7):  # 90일치
                end_time = int(time.time() * 1000) - (i * 24 * 60 * 60 * 1000)
                start_time = end_time - (7 * 24 * 60 * 60 * 1000)
                
                params = {
                    "category": "linear",
                    "symbol": "BTCUSDT",
                    "limit": 1000,
                    "until": end_time  # 종료 시간 추가
                }
                
                batch = await self.bybit_client.fetch_my_trades(
                    symbol="BTCUSDT", 
                    since=start_time,
                    params=params
                )
                if batch:
                    trades.extend(batch)
                    logger.info(f"{i}~{i+7}일 전 거래: {len(batch)}건")
            
            # 3. 거래 저장
            saved_count = 0
            for trade in trades:
                if self.trade_store.save_trade(trade):
                    saved_count += 1
                
            logger.info(f"거래 내역 초기화 완료: {saved_count}건 저장")
            
        except Exception as e:
            logger.error(f"거래 내역 초기화 실패: {str(e)}")

    async def update_trades(self):
        """거래 내역 업데이트"""
        try:
            last_update = self.trade_store.get_last_update()
            current_time = int(time.time() * 1000)
            
            # 마지막 업데이트 이후의 거래만 조회
            new_trades = await self.bybit_client.fetch_my_trades(
                symbol='BTCUSDT',
                since=last_update
            )
            
            if new_trades:
                for trade in new_trades:
                    self.trade_store.save_trade(trade)
                
                # 마지막 업데이트 시간 저장
                self.trade_store.save_last_update(current_time)
                logger.info(f"새로운 거래 {len(new_trades)}건 저장")
                
        except Exception as e:
            logger.error(f"거래 내역 업데이트 실패: {str(e)}")

    async def calculate_stats(self, start_time: Optional[datetime] = None, days: Optional[int] = None) -> Dict:
        """거래 통계 계산"""
        try:
            # 시작 시간 설정
            if start_time:
                start_timestamp = int(start_time.timestamp() * 1000)
            elif days:
                start_timestamp = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
            else:
                start_timestamp = int((datetime.now() - timedelta(days=7)).timestamp() * 1000)
                
            end_timestamp = int(datetime.now().timestamp() * 1000)
            
            # 거래 내역 조회 (GPT 분석 결과 포함)
            trades = self.trade_store.get_trades_with_analysis(start_timestamp, end_timestamp)
            
            if not trades:
                logger.warning("거래 내역이 없습니다.")
                return self._empty_stats()

            # 통계 계산
            total_trades = len(trades)
            pnls = [float(t.get('realized_pnl', 0)) for t in trades]
            total_pnl = sum(pnls)
            win_trades = len([p for p in pnls if p > 0])
            
            stats = {
                'total_trades': total_trades,
                'total_pnl': round(total_pnl, 2),
                'win_rate': round(win_trades / total_trades * 100, 2) if total_trades > 0 else 0,
                'avg_pnl': round(total_pnl / total_trades, 2) if total_trades > 0 else 0,
                'max_profit': round(max(pnls), 2) if pnls else 0,
                'max_loss': round(min(pnls), 2) if pnls else 0,
                'period': {
                    'start': datetime.fromtimestamp(start_timestamp/1000).strftime('%Y-%m-%d %H:%M:%S'),
                    'end': datetime.fromtimestamp(end_timestamp/1000).strftime('%Y-%m-%d %H:%M:%S')
                }
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"거래 통계 계산 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return self._empty_stats()

    def _empty_stats(self) -> Dict:
        """빈 통계 객체 반환"""
        return {
            'total_trades': 0,
            'total_pnl': 0,
            'win_rate': 0,
            'avg_pnl': 0,
            'max_profit': 0,
            'max_loss': 0,
            'period': {
                'start': '',
                'end': ''
            }
        }

    async def get_daily_stats(self) -> Dict:
        """일간 통계"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return await self.calculate_stats(start_time=today)
        
    async def get_weekly_stats(self) -> Dict:
        """주간 통계"""
        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        return await self.calculate_stats(start_time=week_start)
        
    async def get_monthly_stats(self) -> Dict:
        """월간 통계"""
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return await self.calculate_stats(start_time=month_start)

    async def load_trades(self, start_time: int = None, end_time: int = None) -> List[Dict]:
        """특정 기간의 거래 내역 조회
        
        Args:
            start_time: 시작 시간 (밀리초)
            end_time: 종료 시간 (밀리초)
            
        Returns:
            List[Dict]: 거래 내역 리스트
        """
        try:
            # 전체 거래 내역 로드
            all_trades = self.trade_store.get_all_trades()
            
            # 기간 필터링
            if start_time and end_time:
                filtered_trades = [
                    trade for trade in all_trades 
                    if start_time <= trade['timestamp'] <= end_time
                ]
                return filtered_trades
            
            return all_trades
            
        except Exception as e:
            logger.error(f"거래 내역 조회 중 오류: {str(e)}")
            return [] 

    async def init_trade_history(self):
        """거래 내역 초기화"""
        try:
            logger.info("거래 내역 초기화 시작...")
            await self._load_trade_history()  # 실제 API 호출 및 저장
            
        except Exception as e:
            logger.error(f"거래 내역 초기화 중 오류: {str(e)}")

    async def _load_trade_history(self):
        """거래 내역 조회 및 저장"""
        try:
            trades = await self.bybit_client.get_closed_trades(
                symbol='BTCUSDT',
                start_time=None,  # 최근 90일치
                end_time=None
            )
            
            saved_count = 0
            for trade in trades:
                success = self.trade_store.save_trade(trade)
                if success:
                    saved_count += 1
                else:
                    logger.error(f"거래 저장 실패: {trade.get('id')}")
                
            logger.info(f"거래 내역 초기화 완료: 전체 {len(trades)}건 중 {saved_count}건 저장됨")
            
        except Exception as e:
            logger.error(f"거래 내역 로드 중 오류: {str(e)}")
            logger.error(traceback.format_exc()) 

    async def get_closed_trades(self, symbol: str, limit: int = 1000, days: int = 90) -> List[Dict]:
        """거래 내역 조회"""
        try:
            trades = []
            # 7일 단위로 나누어 조회
            for i in range(0, days, 7):
                end_time = int(time.time() * 1000) - (i * 24 * 60 * 60 * 1000)
                start_time = end_time - (7 * 24 * 60 * 60 * 1000)
                
                params = {
                    "category": "linear",
                    "symbol": symbol,
                    "limit": limit
                }
                
                batch = await self.bybit_client.fetch_my_trades(symbol, since=start_time, params=params)
                trades.extend(batch)
                
            logger.info(f"최종 포맷팅된 거래 내역: {len(trades)}건")
            return trades
            
        except Exception as e:
            logger.error(f"거래 내역 조회 중 오류: {str(e)}")
            return [] 