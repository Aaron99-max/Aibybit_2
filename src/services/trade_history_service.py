import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
import time
import traceback

logger = logging.getLogger(__name__)

class TradeHistoryService:
    def __init__(self, bybit_client):
        self.bybit_client = bybit_client
        self.history_file = Path('src/data/trades/history.json')
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
    async def update_trades(self):
        """거래 내역 업데이트 및 저장"""
        try:
            # 현재 시간 체크
            current_hour = datetime.now().hour
            # 4시간봉 시간이 아니면 업데이트 하지 않음 (1, 5, 9, 13, 17, 21시)
            if current_hour not in [1, 5, 9, 13, 17, 21]:
                logger.debug("4시간봉 업데이트 시간이 아닙니다.")
                return
                
            # 완료된 거래 내역 조회
            new_trades = await self.bybit_client.get_closed_trades('BTCUSDT')
            
            if new_trades:
                # 기존 거래 내역 로드
                existing_trades = self.load_trades()
                
                # 새로운 거래만 추가
                updated_trades = existing_trades.copy()
                for trade in new_trades:
                    # 이미 존재하는 거래인지 확인
                    if not any(
                        existing['timestamp'] == trade['timestamp'] and
                        existing['side'] == trade['side'] and
                        existing['size'] == trade['size'] and
                        existing['entry_price'] == trade['entry_price']
                        for existing in existing_trades
                    ):
                        updated_trades.append(trade)
                
                # 시간순 정렬
                updated_trades.sort(key=lambda x: x['timestamp'], reverse=True)
                
                # 저장
                with open(self.history_file, 'w', encoding='utf-8') as f:
                    json.dump(updated_trades, f, indent=2)
                    
                logger.info(f"거래 내역 업데이트 완료: 새로운 거래 {len(new_trades)}건")
                
        except Exception as e:
            logger.error(f"거래 내역 업데이트 실패: {str(e)}")
            logger.error(traceback.format_exc())
            
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
        """이번 달 통계 계산"""
        try:
            trades = self.load_trades()
            if not trades:
                return self._empty_stats()

            # 이번 달의 첫날 타임스탬프 계산
            now = datetime.now()
            start_of_month = datetime(now.year, now.month, 1).timestamp() * 1000
            
            # 이번 달 거래만 필터링 (timestamp 비교 수정)
            monthly_trades = [trade for trade in trades 
                             if int(trade.get('timestamp', 0)) >= int(start_of_month)]
            
            if not monthly_trades:
                return self._empty_stats()
            
            # 수익/손실 계산
            pnls = [float(trade.get('realized_pnl', 0)) for trade in monthly_trades]
            total_pnl = sum(pnls)
            max_profit = max(pnls)
            max_loss = min(pnls)
            avg_pnl = total_pnl / len(monthly_trades)
            
            # 승/패 계산
            wins = sum(1 for pnl in pnls if pnl > 0)
            losses = sum(1 for pnl in pnls if pnl <= 0)
            win_rate = (wins / len(monthly_trades)) * 100 if monthly_trades else 0
            
            return {
                'period': '이번 달',
                'total_trades': len(monthly_trades),
                'winning_trades': wins,
                'losing_trades': losses,
                'win_rate': round(win_rate, 2),
                'total_profit': round(total_pnl, 2),
                'average_profit': round(avg_pnl, 2),
                'max_profit': round(max_profit, 2),
                'max_loss': round(max_loss, 2),
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"월간 통계 계산 중 오류: {str(e)}")
            return self._empty_stats()

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
        # 초기화 시에는 시간 체크 없이 무조건 업데이트
        try:
            # 완료된 거래 내역 조회
            new_trades = await self.bybit_client.get_closed_trades('BTCUSDT')
            
            if new_trades:
                # 기존 거래 내역 로드
                existing_trades = self.load_trades()
                
                # 새로운 거래만 추가
                updated_trades = existing_trades.copy()
                for trade in new_trades:
                    # 이미 존재하는 거래인지 확인
                    if not any(
                        existing['timestamp'] == trade['timestamp'] and
                        existing['side'] == trade['side'] and
                        existing['size'] == trade['size'] and
                        existing['entry_price'] == trade['entry_price']
                        for existing in existing_trades
                    ):
                        updated_trades.append(trade)
                
                # 시간순 정렬
                updated_trades.sort(key=lambda x: x['timestamp'], reverse=True)
                
                # 저장
                with open(self.history_file, 'w', encoding='utf-8') as f:
                    json.dump(updated_trades, f, indent=2)
                    
                logger.info(f"거래 내역 초기화 완료: {len(new_trades)}건 저장됨")
            else:
                logger.info("초기화할 거래 내역이 없습니다.")
                
        except Exception as e:
            logger.error(f"거래 내역 초기화 실패: {str(e)}")
            logger.error(traceback.format_exc())
            
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