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
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

    def _load_last_update(self):
        """마지막 업데이트 시간 로드"""
        return self.trade_store.get_last_update()

    def _save_last_update(self, timestamp):
        """마지막 업데이트 시간 저장"""
        self.trade_store.save_last_update(timestamp)

    async def initialize(self):
        """포지션 정보 초기화"""
        try:
            # 마지막 업데이트 시간부터 현재까지의 데이터 조회
            start_timestamp = self.trade_store.get_last_update()
            end_timestamp = int(datetime.now().timestamp() * 1000)
            
            positions = await self.fetch_and_update_positions(start_timestamp, end_timestamp)
            logger.info(f"포지션 정보 초기화 완료: {len(positions)}건")
            
            return positions
            
        except Exception as e:
            logger.error(f"포지션 정보 초기화 실패: {e}")
            return []

    def _find_missing_periods(self, existing_trades, start_timestamp, end_timestamp):
        """누락된 기간 찾기"""
        # 마지막 업데이트 시간 이후의 데이터만 조회
        last_update = self.trade_store.get_last_update()
        if start_timestamp < last_update:
            start_timestamp = last_update
        
        if not existing_trades:
            return [(start_timestamp, end_timestamp)]
        
        # 거래 데이터를 날짜별로 정리
        trade_dates = set()
        for trade in existing_trades:
            trade_time = datetime.fromtimestamp(trade['timestamp']/1000)
            trade_dates.add(trade_time.date())
        
        # 전체 기간의 날짜 생성
        start_date = datetime.fromtimestamp(start_timestamp/1000).date()
        end_date = datetime.fromtimestamp(end_timestamp/1000).date()
        
        all_dates = set()
        current_date = start_date
        while current_date <= end_date:
            all_dates.add(current_date)
            current_date += timedelta(days=1)
        
        # 누락된 날짜 찾기
        missing_dates = sorted(all_dates - trade_dates)
        
        # 연속된 날짜를 기간으로 묶기
        missing_periods = []
        if missing_dates:
            period_start = missing_dates[0]
            prev_date = period_start
            
            for current_date in missing_dates[1:]:
                if (current_date - prev_date).days > 1:
                    period_end = prev_date
                    missing_periods.append((
                        int(datetime.combine(period_start, datetime.min.time()).timestamp() * 1000),
                        int(datetime.combine(period_end, datetime.max.time()).timestamp() * 1000)
                    ))
                    period_start = current_date
                prev_date = current_date
            
            # 마지막 기간 추가
            missing_periods.append((
                int(datetime.combine(period_start, datetime.min.time()).timestamp() * 1000),
                int(datetime.combine(prev_date, datetime.max.time()).timestamp() * 1000)
            ))
        
        return missing_periods

    async def _fetch_trades_for_period(self, start_time: int, end_time: int):
        """특정 기간의 포지션 정보 조회 (CCXT 사용)"""
        try:
            positions = []
            
            # 7일 단위로 나누어 조회 (7일 = 604800000 밀리초)
            current_start = start_time
            while current_start < end_time:
                current_end = min(current_start + 604800000, end_time)
                
                params = {
                    'category': 'linear',
                    'symbol': 'BTCUSDT',
                    'limit': 100,
                    'startTime': str(current_start),
                    'endTime': str(current_end)
                }
                
                logger.debug(f"CCXT fetch_my_trades 호출 - params: {params}")
                trades = await self.bybit_client.exchange.fetch_my_trades(
                    symbol='BTC/USDT:USDT',
                    since=current_start,
                    limit=100,
                    params=params
                )
                
                if trades:
                    positions.extend(self._convert_trades_to_positions(trades))
                
                # 다음 기간으로 이동
                current_start = current_end + 1
                
                # API 호출 간격 조절
                await asyncio.sleep(0.1)
            
            logger.info(f"포지션 정보 {len(positions)}건 조회 완료")
            return positions

        except Exception as e:
            logger.error(f"거래 조회 중 오류 발생: {str(e)}")
            logger.error(traceback.format_exc())
            return []

    async def fetch_and_update_positions(self, start_time: Optional[int] = None, end_time: Optional[int] = None, force_full_update: bool = False):
        """포지션 정보 조회 및 업데이트"""
        try:
            if not start_time:
                start_time = int((datetime.now() - timedelta(days=90)).timestamp() * 1000)
            if not end_time:
                end_time = int(datetime.now().timestamp() * 1000)

            # 기존 데이터 조회
            existing_trades = self.trade_store.get_positions(start_time, end_time)
            
            # 누락된 기간 찾기
            if force_full_update:
                missing_periods = [(start_time, end_time)]
            else:
                missing_periods = self._find_missing_periods(existing_trades, start_time, end_time)
            
            total_positions = []
            for period_start, period_end in missing_periods:
                positions = await self._fetch_trades_for_period(period_start, period_end)
                if positions:
                    total_positions.extend(positions)
                    
                    # 데이터 저장
                    self.trade_store.save_positions(positions)
                    
                    # 마지막 업데이트 시간 저장
                    max_timestamp = max(int(p.get('timestamp', 0)) for p in positions)
                    self._save_last_update(max_timestamp)
                
                # API 호출 간격 조절
                await asyncio.sleep(0.1)
            
            return total_positions

        except Exception as e:
            logger.error(f"포지션 정보 업데이트 실패: {str(e)}")
            logger.error(traceback.format_exc())
            return []

    async def get_positions(self, start_time: int, end_time: int) -> List[Dict]:
        """포지션 정보 조회"""
        try:
            params = {
                "category": "linear",
                "symbol": "BTCUSDT",
                "startTime": str(start_time),
                "endTime": str(end_time),
                "limit": 100
            }
            
            logger.debug(f"API 요청 파라미터: {params}")
            
            response = await self.bybit_client.v5_get_closed_pnl(params)
            
            if response and response.get('retCode') == 0:
                positions = response.get('result', {}).get('list', [])
                if positions:
                    logger.info(f"포지션 {len(positions)}건 조회됨")
                    
                    processed_positions = []
                    for p in positions:
                        # 실제 포지션 방향 계산 (진입 시점의 side 기준)
                        entry_side = p.get('side')
                        position_side = 'Long' if entry_side == 'Buy' else 'Short'
                        
                        processed_position = {
                            'id': p.get('orderId'),
                            'timestamp': int(p.get('updatedTime')),
                            'symbol': 'BTCUSDT',
                            'side': entry_side,
                            'position_side': position_side,  # 수정된 포지션 방향
                            'type': p.get('orderType'),
                            'entry_price': float(p.get('avgEntryPrice', 0)),
                            'exit_price': float(p.get('avgExitPrice', 0)),
                            'size': float(p.get('qty', 0)),
                            'leverage': int(p.get('leverage', 1)),
                            'entry_value': float(p.get('cumEntryValue', 0)),
                            'exit_value': float(p.get('cumExitValue', 0)),
                            'pnl': float(p.get('closedPnl', 0)),
                            'created_time': int(p.get('createdTime', 0)),
                            'closed_time': int(p.get('updatedTime', 0)),
                            'closed_size': float(p.get('closedSize', 0)),
                            'exec_type': p.get('execType'),
                            'fill_count': 1
                        }
                        processed_positions.append(processed_position)
                    
                    return processed_positions
                return []
            
            return []
            
        except Exception as e:
            logger.error(f"포지션 조회 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return []

    async def get_position_stats(self, days: int) -> Dict:
        """포지션 통계 조회"""
        try:
            end_time = int(time.time() * 1000)
            start_time = end_time - (days * 24 * 60 * 60 * 1000)
            
            positions = self.trade_store.get_positions(start_time, end_time)
            
            if not positions:
                return None
            
            total_pnl = sum(float(p.get('closed_pnl', 0)) for p in positions)
            win_trades = sum(1 for p in positions if float(p.get('closed_pnl', 0)) > 0)
            total_trades = len(positions)
            
            return {
                'period': f"{days}일",
                'total_trades': total_trades,
                'win_rate': round(win_trades / total_trades * 100, 2) if total_trades > 0 else 0,
                'total_pnl': round(total_pnl, 4),
                'avg_pnl': round(total_pnl / total_trades, 4) if total_trades > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"포지션 통계 조회 실패: {str(e)}")
            return None

    async def load_trades(self, start_time: int = None, end_time: int = None) -> List[Dict]:
        """거래 내역 조회"""
        return self.trade_store.get_trades(start_time, end_time)

    def get_positions_by_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        """날짜 범위로 포지션 조회"""
        try:
            positions = []
            current_date = datetime.strptime(start_date, '%Y%m%d')
            end = datetime.strptime(end_date, '%Y%m%d')
            
            while current_date <= end:
                # 일별 포지션 조회
                daily_positions = self.trade_store.get_daily_positions(
                    current_date.strftime('%Y%m%d')
                )
                positions.extend(daily_positions)
                current_date += timedelta(days=1)
                
            return positions
            
        except Exception as e:
            logger.error(f"날짜 범위 포지션 조회 중 오류: {str(e)}")
            return [] 

    def _process_positions(self, positions: List[Dict]) -> List[Dict]:
        """포지션 데이터 처리"""
        processed = []
        for p in positions:
            try:
                processed_position = {
                    'id': p.get('orderId'),
                    'timestamp': int(p.get('updatedTime')),
                    'side': p.get('side'),
                    'size': float(p.get('qty', 0)),
                    'entry_price': float(p.get('avgEntryPrice', 0)),
                    'exit_price': float(p.get('avgExitPrice', 0)),
                    'leverage': int(p.get('leverage', 1)),
                    'value': float(p.get('cumEntryValue', 0)),
                    'pnl': float(p.get('closedPnl', 0))
                }
                processed.append(processed_position)
            except Exception as e:
                logger.error(f"포지션 데이터 처리 중 오류: {str(e)}")
                logger.error(f"원본 데이터: {p}")
            
        return processed 

    def _convert_trades_to_positions(self, trades):
        """CCXT 거래 데이터를 포지션 형식으로 매핑"""
        positions = []
        try:
            for trade in trades:
                # 거래 방향 확인
                side = trade.get('side', '').lower()
                is_close = trade.get('reduceOnly', False)
                
                # 포지션 방향 결정
                # reduceOnly가 True면 청산 거래, False면 진입 거래
                if is_close:
                    position_side = 'Long' if side == 'sell' else 'Short'  # 청산 시에는 반대 방향이 포지션 방향
                else:
                    position_side = 'Long' if side == 'buy' else 'Short'  # 진입 시에는 같은 방향이 포지션 방향
                
                # 수량은 양수로 저장 (부호는 position_side로 구분)
                size = abs(float(trade.get('amount', 0)))
                
                # 가격 정보
                price = float(trade.get('price', 0))
                
                # 수수료 계산
                fee = float(trade.get('fee', {}).get('cost', 0))
                
                # 거래 가치 계산
                value = size * price
                
                # 생성 시간과 종료 시간
                created_time = trade.get('timestamp', 0)
                closed_time = trade.get('timestamp', 0)
                
                mapped_position = {
                    'id': trade.get('id', ''),
                    'timestamp': closed_time,
                    'symbol': 'BTCUSDT',
                    'side': side.capitalize(),
                    'position_side': position_side,
                    'type': trade.get('type', 'limit').capitalize(),
                    'entry_price': price,
                    'exit_price': price,
                    'size': size,
                    'leverage': float(trade.get('leverage', 1)) if 'leverage' in trade else 1,
                    'entry_value': value,
                    'exit_value': value,
                    'pnl': float(trade.get('realizedPnl', 0)) if 'realizedPnl' in trade else 0,
                    'created_time': created_time,
                    'closed_time': closed_time,
                    'closed_size': size,
                    'exec_type': 'Trade',
                    'fill_count': 1
                }
                positions.append(mapped_position)
                
                logger.debug(f"변환된 포지션: {json.dumps(mapped_position, indent=2)}")
                
            return positions
            
        except Exception as e:
            logger.error(f"거래 데이터 변환 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return []