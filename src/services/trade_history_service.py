import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class TradeHistoryService:
    def __init__(self, bybit_client):
        self.bybit_client = bybit_client
        self.history_file = Path('data/trades/history.json')
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
    async def update_trades(self):
        """거래 내역 업데이트 및 저장"""
        try:
            # 완료된 거래 내역 조회
            trades = await self.bybit_client.get_closed_trades('BTCUSDT')
            
            if trades:
                # 마지막 조회 결과 저장
                with open(self.history_file, 'w', encoding='utf-8') as f:
                    json.dump(trades, f, indent=2)
                logger.info(f"거래 내역 업데이트 완료: {len(trades)}건")
        except Exception as e:
            logger.error(f"거래 내역 업데이트 실패: {str(e)}")
            
    def load_trades(self) -> List[Dict]:
        """저장된 거래 내역 로드"""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"거래 내역 로드 실패: {str(e)}")
            return []

    async def calculate_stats(self, days: Optional[int] = None) -> Dict:
        """거래 통계 계산"""
        try:
            trades = self.load_trades()
            if not trades:
                return self._empty_stats()

            # 기간 필터링
            if days:
                cutoff = datetime.now() - timedelta(days=days)
                trades = [t for t in trades if t['timestamp'] > cutoff.timestamp() * 1000]

            total_trades = len(trades)
            winning_trades = len([t for t in trades if float(t.get('realized_pnl', 0)) > 0])
            losing_trades = len([t for t in trades if float(t.get('realized_pnl', 0)) < 0])
            
            total_profit = sum(float(t.get('realized_pnl', 0)) for t in trades)
            max_profit = max((float(t.get('realized_pnl', 0)) for t in trades), default=0)
            max_loss = min((float(t.get('realized_pnl', 0)) for t in trades), default=0)
            
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            avg_profit = total_profit / total_trades if total_trades > 0 else 0
            
            return {
                'period': f"{days}일" if days else "전체",
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': round(win_rate, 2),
                'total_profit': round(total_profit, 2),
                'average_profit': round(avg_profit, 2),
                'max_profit': round(max_profit, 2),
                'max_loss': round(max_loss, 2),
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"통계 계산 실패: {str(e)}")
            return self._empty_stats()

    def _empty_stats(self) -> Dict:
        return {
            'period': "N/A",
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0,
            'total_profit': 0,
            'average_profit': 0,
            'max_profit': 0,
            'max_loss': 0,
            'last_updated': datetime.now().isoformat()
        }

    async def get_current_month_stats(self) -> Dict:
        """이번 달 통계"""
        now = datetime.now()
        days_in_month = (now - now.replace(day=1)).days + 1
        return await self.calculate_stats(days_in_month)

    async def get_daily_stats(self) -> Dict:
        """일일 통계"""
        return await self.calculate_stats(1)

    async def get_weekly_stats(self) -> Dict:
        """주간 통계"""
        return await self.calculate_stats(7)

    async def get_monthly_stats(self) -> Dict:
        """월간 통계"""
        return await self.calculate_stats(30)

    async def initialize(self):
        """초기 거래 내역 조회 및 저장"""
        logger.info("거래 내역 초기화 시작...")
        await self.update_trades()
        logger.info("거래 내역 초기화 완료") 

    async def should_update(self) -> bool:
        """업데이트 필요 여부 확인 (1, 5, 9, 13, 17, 21시)"""
        current_time = datetime.now()
        current_hour = current_time.hour
        
        # 정해진 시간(1, 5, 9, 13, 17, 21시)에만 실행
        if current_hour in [1, 5, 9, 13, 17, 21] and current_time.minute == 0:
            logger.info(f"거래 내역 업데이트 시간: {current_hour:02d}:00")
            return True
            
        return False 