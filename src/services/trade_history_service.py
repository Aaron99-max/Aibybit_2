import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os
from pathlib import Path

logger = logging.getLogger(__name__)

class TradeHistoryService:
    def __init__(self):
        self.history_file = config.data_dir / 'trades' / 'history.json'
        
    def save_trade(self, trade: Dict):
        """거래 기록 저장"""
        try:
            # 기존 기록 로드
            trades = self.load_trades()
            
            # 새 거래 추가
            trades.append({
                **trade,
                'timestamp': datetime.now().isoformat()
            })
            
            # 파일 저장
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(trades, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"거래 기록 저장 중 오류: {str(e)}")

    def load_trades(self) -> List[Dict]:
        """거래 기록 로드"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"거래 기록 로드 실패: {str(e)}")
            return []

    def get_trades(self, days: Optional[int] = None) -> List[Dict]:
        """기간별 거래 기록 조회"""
        try:
            if days is None:
                return self.load_trades()
                
            cutoff = datetime.now() - timedelta(days=days)
            return [
                trade for trade in self.load_trades()
                if datetime.fromisoformat(trade['timestamp']) > cutoff
            ]
        except Exception as e:
            logger.error(f"거래 기록 조회 실패: {str(e)}")
            return []

    def calculate_stats(self, days: Optional[int] = None) -> Dict:
        """거래 통계 계산"""
        try:
            trades = self.get_trades(days)
            if not trades:
                return self._empty_stats()

            total_trades = len(trades)
            winning_trades = len([t for t in trades if float(t.get('realized_pnl', 0)) > 0])
            losing_trades = len([t for t in trades if float(t.get('realized_pnl', 0)) < 0])
            
            total_profit = sum(float(t.get('realized_pnl', 0)) for t in trades)
            max_profit = max(float(t.get('realized_pnl', 0)) for t in trades)
            max_loss = min(float(t.get('realized_pnl', 0)) for t in trades)
            
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            avg_profit = total_profit / total_trades if total_trades > 0 else 0
            
            return {
                'period': f"{days}일" if days else "전체",
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': win_rate,
                'total_profit': total_profit,
                'average_profit': avg_profit,
                'max_profit': max_profit,
                'max_loss': max_loss,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"통계 계산 실패: {str(e)}")
            return self._empty_stats()

    def _empty_stats(self) -> Dict:
        """빈 통계 데이터"""
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
        return self.calculate_stats(days_in_month)

    async def get_daily_stats(self) -> Dict:
        """일일 통계"""
        return self.calculate_stats(1)

    async def get_weekly_stats(self) -> Dict:
        """주간 통계"""
        return self.calculate_stats(7)

    async def get_monthly_stats(self) -> Dict:
        """월간 통계"""
        return self.calculate_stats(30) 