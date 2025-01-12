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
            new_trades = await self.bybit_client.get_closed_trades(
                symbol='BTCUSDT',
                limit=1000,
                days=90
            )
            
            if new_trades:
                # 기존 거래 내역 로드
                existing_trades = self.load_trades()
                
                # 새로운 거래만 추가
                updated_trades = existing_trades.copy()
                for trade in new_trades:
                    # 이미 존재하는 거래인지 확인 (필드명 수정)
                    if not any(
                        existing['id'] == trade['id'] and
                        existing['timestamp'] == trade['timestamp'] and
                        existing['side'] == trade['side'] and
                        existing['amount'] == trade['amount'] and  # size -> amount
                        existing['price'] == trade['price']        # entry_price -> price
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

    async def calculate_stats(self, start_time: Optional[datetime] = None, days: Optional[int] = None) -> Dict:
        """거래 통계 계산"""
        try:
            trades = self.load_trades()
            if not trades:
                logger.warning("거래 내역이 없습니다.")
                return self._empty_stats()

            # 디버그 로깅 추가
            logger.debug(f"전체 거래 수: {len(trades)}")
            logger.debug(f"첫 번째 거래: {trades[0]}")

            # 기간 필터링
            if start_time:
                trades = [t for t in trades if datetime.fromtimestamp(int(t['timestamp'])/1000) >= start_time]
            elif days:
                cutoff = datetime.now() - timedelta(days=days)
                trades = [t for t in trades if int(t['timestamp']) > int(cutoff.timestamp() * 1000)]

            if not trades:
                logger.warning("필터링 후 거래 내역이 없습니다.")
                return self._empty_stats()

            # 디버그 로깅 추가
            logger.debug(f"필터링 후 거래 수: {len(trades)}")

            # 통계 계산
            total_trades = len(trades)
            pnls = []
            
            for trade in trades:
                try:
                    pnl = float(trade.get('realized_pnl', 0))
                    if pnl != 0:  # 실현된 손익이 있는 경우만 포함
                        pnls.append(pnl)
                except (ValueError, TypeError) as e:
                    logger.error(f"PNL 변환 오류: {trade.get('realized_pnl')}, {str(e)}")
                    continue

            if not pnls:
                logger.warning("유효한 PNL 데이터가 없습니다.")
                return self._empty_stats()

            # 디버그 로깅 추가
            logger.debug(f"유효한 PNL 수: {len(pnls)}")
            logger.debug(f"PNL 합계: {sum(pnls)}")
            
            winning_trades = len([pnl for pnl in pnls if pnl > 0])
            losing_trades = len([pnl for pnl in pnls if pnl < 0])
            
            total_profit = sum(pnls)
            max_profit = max(pnls) if pnls else 0
            max_loss = min(pnls) if pnls else 0
            
            win_rate = (winning_trades / len(pnls) * 100) if pnls else 0
            avg_profit = total_profit / len(pnls) if pnls else 0

            period_text = "전체"
            if start_time:
                if start_time.date() == datetime.now().date():
                    period_text = "일간"
                elif start_time.day == 1:
                    period_text = "월간"
                else:
                    period_text = "주간"
            elif days:
                period_text = f"{days}일"

            stats = {
                'period': period_text,
                'total_trades': len(pnls),  # 유효한 거래만 카운트
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': round(win_rate, 2),
                'total_profit': round(total_profit, 2),
                'average_profit': round(avg_profit, 2),
                'max_profit': round(max_profit, 2),
                'max_loss': round(max_loss, 2),
                'last_updated': datetime.now().isoformat()
            }

            logger.debug(f"계산된 통계: {stats}")
            return stats

        except Exception as e:
            logger.error(f"통계 계산 실패: {str(e)}")
            logger.error(traceback.format_exc())
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
            logger.debug(f"로드된 전체 거래 수: {len(trades)}")
            
            if not trades:
                logger.warning("거래 내역이 없습니다")
                return self._empty_stats()

            # 최근 30일 데이터 사용
            now = datetime.now()
            start_time = (now - timedelta(days=30)).timestamp() * 1000
            
            # 최근 30일 거래만 필터링
            recent_trades = [trade for trade in trades 
                            if int(trade.get('timestamp', 0)) >= int(start_time)]
            
            logger.debug(f"최근 30일 거래 수: {len(recent_trades)}")
            if recent_trades:
                logger.debug(f"첫 번째 거래: {recent_trades[0]}")
                logger.debug(f"마지막 거래: {recent_trades[-1]}")
            
            if not recent_trades:
                logger.warning("최근 30일 거래 내역이 없습니다")
                return self._empty_stats()
            
            # 수익/손실 계산
            pnls = []
            for trade in recent_trades:
                try:
                    pnl = float(trade.get('realized_pnl', 0))
                    if pnl != 0:  # 실현된 손익이 있는 경우만 포함
                        pnls.append(pnl)
                        logger.debug(f"거래 PNL: {pnl}")
                except (ValueError, TypeError) as e:
                    logger.error(f"PNL 변환 오류: {trade.get('realized_pnl')}, {str(e)}")
                    continue
            
            if not pnls:
                logger.warning("유효한 PNL 데이터가 없습니다")
                return self._empty_stats()
            
            total_pnl = sum(pnls)
            max_profit = max(pnls)
            max_loss = min(pnls)
            avg_pnl = total_pnl / len(pnls)
            
            # 승/패 계산
            wins = sum(1 for pnl in pnls if pnl > 0)
            losses = sum(1 for pnl in pnls if pnl < 0)
            win_rate = (wins / len(pnls)) * 100 if pnls else 0
            
            stats = {
                'period': '최근 30일',
                'total_trades': len(pnls),
                'winning_trades': wins,
                'losing_trades': losses,
                'win_rate': round(win_rate, 2),
                'total_profit': round(total_pnl, 2),
                'average_profit': round(avg_pnl, 2),
                'max_profit': round(max_profit, 2),
                'max_loss': round(max_loss, 2),
                'last_updated': datetime.now().isoformat()
            }
            
            logger.debug(f"계산된 통계: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"통계 계산 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return self._empty_stats()

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
        
    async def initialize(self):
        """초기 거래 내역 조회 및 저장"""
        logger.info("거래 내역 초기화 시작...")
        try:
            # 완료된 거래 내역 조회 (최근 90일, 최대 1000개)
            new_trades = await self.bybit_client.get_closed_trades(
                symbol='BTCUSDT',
                limit=1000,
                days=90
            )
            
            if new_trades:
                # 기존 거래 내역 로드
                existing_trades = self.load_trades()
                
                # 새로운 거래만 추가
                updated_trades = existing_trades.copy()
                for trade in new_trades:
                    # 이미 존재하는 거래인지 확인 (timestamp와 side만으로 비교)
                    if not any(
                        existing.get('timestamp') == trade['timestamp'] and
                        existing.get('side') == trade['side'] and
                        existing.get('amount') == trade['amount'] and
                        existing.get('price') == trade['price']
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