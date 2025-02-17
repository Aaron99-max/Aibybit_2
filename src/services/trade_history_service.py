import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
import traceback
from services.trade_store import TradeStore
import time
import asyncio
from exchange.bybit_client import BybitClient

logger = logging.getLogger(__name__)

class TradeHistoryService:
    def __init__(self, trade_store: TradeStore, bybit_client: BybitClient):
        self.trade_store = trade_store
        self.bybit_client = bybit_client
        # 디버그 로거 설정
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

    async def initialize(self):
        """포지션 정보 초기화"""
        try:
            logger.info("=== 포지션 정보 초기화 시작 ===")
            
            # 1. 먼저 저장된 데이터 확인 (90일)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=90)
            start_timestamp = int(start_date.timestamp() * 1000)
            end_timestamp = int(end_date.timestamp() * 1000)
            
            existing_positions = self.trade_store.get_positions(start_timestamp, end_timestamp)
            
            # 2. 저장된 데이터가 없으면 90일 데이터 조회
            if not existing_positions:
                logger.info("기존 데이터가 없습니다. 전체 기간 조회를 시작합니다.")
                await self.fetch_and_update_positions(
                    start_time=start_timestamp,
                    end_time=end_timestamp,
                    force_full_update=True
                )
            
            # 3. 마지막 업데이트 이후 새로운 데이터 확인
            last_update = self.trade_store.get_last_update()
            if last_update:
                logger.info(f"마지막 업데이트: {datetime.fromtimestamp(last_update/1000)}")
                
                # 새로운 포지션 데이터 조회
                new_positions = await self.fetch_and_update_positions(
                    start_time=last_update,
                    end_time=int(time.time() * 1000)
                )
                
                if new_positions:
                    logger.info(f"새로운 포지션 데이터 발견: {len(new_positions)}건")
                else:
                    logger.info("새로운 포지션 데이터 없음")
            else:
                logger.info("마지막 업데이트 정보가 없습니다. 전체 기간 조회를 시작합니다.")
                await self.fetch_and_update_positions(
                    start_time=start_timestamp,
                    end_time=end_timestamp,
                    force_full_update=True
                )

        except Exception as e:
            logger.error(f"포지션 정보 초기화 실패: {str(e)}")
            logger.error(traceback.format_exc())

    def _find_missing_periods(self, existing_trades, start_timestamp, end_timestamp):
        """누락된 기간 찾기"""
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
        """특정 기간의 포지션 정보 조회"""
        try:
            positions = []
            cursor = None
            
            while True:
                params = {
                    'category': 'linear',
                    'symbol': 'BTCUSDT',
                    'limit': 100,
                    'startTime': start_time,
                    'endTime': end_time
                }
                if cursor:
                    params['cursor'] = cursor

                # closed-pnl API 사용
                response = await self.bybit_client.v5_get_closed_pnl(params)
                
                if not response or 'result' not in response:
                    logger.error(f"API 응답 오류: {response}")
                    break

                result = response['result']
                list_data = result.get('list', [])
                
                if not list_data:
                    break

                # 디버그 로깅 추가
                logger.debug(f"API 응답 데이터: {list_data[0] if list_data else 'empty'}")

                for pnl in list_data:
                    # closed-pnl 데이터를 포지션 형식으로 매핑
                    mapped_position = {
                        'id': pnl.get('orderId', ''),
                        'timestamp': int(pnl.get('updatedTime', 0)),
                        'symbol': pnl.get('symbol', ''),
                        'side': pnl.get('side', ''),
                        'position_side': pnl.get('positionIdx', ''),
                        'type': pnl.get('orderType', ''),
                        'entry_price': float(pnl.get('avgEntryPrice', 0)),
                        'exit_price': float(pnl.get('avgExitPrice', 0)),
                        'size': float(pnl.get('qty', 0)),
                        'leverage': float(pnl.get('leverage', 1)),
                        'entry_value': float(pnl.get('entryRealised', 0)),
                        'exit_value': float(pnl.get('exitRealised', 0)),
                        'pnl': float(pnl.get('closedPnl', 0)),
                        'created_time': int(pnl.get('createdTime', 0)),
                        'closed_time': int(pnl.get('updatedTime', 0)),
                        'closed_size': float(pnl.get('qty', 0)),
                        'exec_type': pnl.get('execType', ''),
                        'fill_count': 1
                    }
                    positions.append(mapped_position)

                cursor = result.get('nextPageCursor')
                if not cursor:
                    break

            logger.info(f"포지션 정보 {len(positions)}건 조회 완료")
            if positions:
                self.trade_store._save_last_update(max(int(p.get('timestamp', 0)) for p in positions))
            return positions

        except Exception as e:
            logger.error(f"포지션 정보 업데이트 실패: {str(e)}")
            logger.error(traceback.format_exc())
            return []

    async def _fetch_trades_with_pagination(self, start_time: int, end_time: int) -> List[Dict]:
        """페이지네이션을 사용하여 거래 내역 조회"""
        trades = []
        cursor = None
        
        try:
            # 바이빗 서버 시간 조회 수정
            server_time = int(time.time() * 1000)  # 로컬 시간으로 대체
            ninety_days_ago = server_time - (90 * 24 * 60 * 60 * 1000)
            
            # 시작 시간이 90일 이전이면 조정
            if start_time < ninety_days_ago:
                logger.warning(f"시작 시간이 90일 이전입니다. {datetime.fromtimestamp(start_time/1000)} -> {datetime.fromtimestamp(ninety_days_ago/1000)}")
                start_time = ninety_days_ago
            
            while True:
                try:
                    params = {
                        "category": "linear",
                        "symbol": "BTCUSDT",
                        "limit": 100,
                        "startTime": start_time,  # 밀리초 단위 유지
                        "endTime": end_time,      # 밀리초 단위 유지
                        "execType": "Trade",      # orderType 대신 execType 사용
                        "recvWindow": 5000
                    }
                    
                    if cursor:
                        params["cursor"] = cursor
                    
                    logger.debug(f"API 요청 파라미터: {params}")
                    
                    # API 호출
                    batch = await self.bybit_client.fetch_my_trades(
                        symbol="BTCUSDT",
                        params=params
                    )
                    
                    if not batch:
                        break
                        
                    trades.extend(batch)
                    logger.debug(f"조회된 거래 수: {len(batch)}건")
                    
                    # 다음 페이지 커서 확인
                    if isinstance(batch[-1].get('info'), dict):
                        cursor = batch[-1]['info'].get('nextPageCursor')
                        if not cursor:
                            break
                    else:
                        break
                    
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"거래 조회 중 오류 발생: {str(e)}")
                    logger.error(traceback.format_exc())
                    await asyncio.sleep(2)
                    break
                
        except Exception as e:
            logger.error(f"거래 조회 실패: {str(e)}")
            return []
        
        return trades 

    def _validate_trades(self, trades: List[Dict]) -> List[Dict]:
        """거래 데이터 유효성 검사"""
        valid_trades = []
        for trade in trades:
            try:
                # 필수 필드 확인
                required_fields = ['timestamp', 'side', 'price', 'amount', 'info']
                if all(field in trade for field in required_fields):
                    valid_trades.append(trade)
                else:
                    logger.warning(f"유효하지 않은 거래 데이터: {trade}")
            except Exception as e:
                logger.error(f"거래 데이터 검증 중 오류: {str(e)}")
        return valid_trades

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
            
            response = await self.bybit_client.v5_get_closed_pnl(params)
            if response and response.get('retCode') == 0:
                positions = response.get('result', {}).get('list', [])
                if positions:
                    logger.info(f"포지션 {len(positions)}건 조회됨")
                    
                    processed_positions = []
                    for p in positions:
                        # 실제 포지션 방향 계산 (Sell로 청산 = 롱 포지션)
                        position_side = 'Long' if p.get('side') == 'Sell' else 'Short'
                        
                        processed_position = {
                            'id': p.get('orderId'),
                            'timestamp': int(p.get('updatedTime')),
                            'symbol': 'BTCUSDT',
                            'side': p.get('side'),
                            'position_side': position_side,  # 포지션 방향 추가
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

    async def fetch_and_update_positions(self, start_time: int, end_time: int, force_full_update: bool = False):
        """포지션 정보 조회 및 업데이트"""
        try:
            all_positions = []
            current_start = start_time
            
            # 7일씩 나누어 조회
            while current_start < end_time:
                # 현재 구간의 종료 시간 (7일 또는 남은 기간)
                current_end = min(current_start + (7 * 24 * 60 * 60 * 1000), end_time)
                
                logger.info(f"기간별 조회: {datetime.fromtimestamp(current_start/1000).strftime('%Y-%m-%d')} ~ {datetime.fromtimestamp(current_end/1000).strftime('%Y-%m-%d')}")
                
                # 바이비트에서 포지션 정보 조회
                positions = await self.get_positions(
                    start_time=current_start,
                    end_time=current_end
                )
                
                if positions:
                    all_positions.extend(positions)
                    logger.info(f"포지션 {len(positions)}건 조회됨")
                
                # 다음 구간으로 이동
                current_start = current_end + 1
                await asyncio.sleep(1)  # API 호출 간격 조절
            
            if all_positions:
                # 전체 포지션 저장
                self.trade_store.save_positions(all_positions)
                # 마지막 업데이트 시간 저장
                self.trade_store.update_last_update()
                logger.info(f"총 {len(all_positions)}건의 포지션 저장 완료")
                return all_positions
            
            return []
            
        except Exception as e:
            logger.error(f"포지션 정보 조회 및 업데이트 중 오류: {str(e)}")
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

    async def get_position(self, symbol: str) -> dict:
        """포지션 정보 조회"""
        # 마지막 업데이트 이후 새로운 데이터 확인
        last_update = self.trade_store.get_last_update()
        if last_update:
            await self.fetch_and_update_positions(
                start_time=last_update,
                end_time=int(time.time() * 1000)
            )
        
        # 저장된 포지션 정보 반환
        return self.trade_store.get_position(symbol) 