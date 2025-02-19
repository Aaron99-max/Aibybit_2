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
    def __init__(self, trade_store: TradeStore, bybit_client):
        """
        Args:
            trade_store: 거래 데이터 저장소
            bybit_client: Bybit API 클라이언트
        """
        self.trade_store = trade_store
        self.bybit_client = bybit_client
        # 디버그 로거 설정
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

    async def initialize(self):
        """초기 거래 내역 조회 및 저장"""
        try:
            # 현재 시간 기준 90일 전부터만 조회
            end_timestamp = int(time.time() * 1000)
            start_timestamp = end_timestamp - (90 * 24 * 60 * 60 * 1000)
            
            logger.info("=== 거래 내역 초기화 시작 ===")
            logger.info(f"조회 기간: {datetime.fromtimestamp(start_timestamp/1000).strftime('%Y-%m-%d')} ~ {datetime.fromtimestamp(end_timestamp/1000).strftime('%Y-%m-%d')}")
            
            # 기존 데이터 확인
            existing_trades = self.trade_store.get_trades(start_timestamp, end_timestamp)
            
            if not existing_trades:
                # 데이터가 없는 경우 전체 기간 조회
                logger.info("기존 데이터가 없습니다. 전체 기간 조회를 시작합니다.")
                await self.update_trades(force_full_update=True)
            else:
                # 증분 업데이트
                logger.info(f"기존 데이터: {len(existing_trades)}건")
                await self.update_trades()
            
        except Exception as e:
            logger.error(f"거래 내역 초기화 실패: {str(e)}")
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

    async def _fetch_trades_for_period(self, start_time: int, end_time: int) -> List[Dict]:
        """특정 기간의 거래 내역 조회"""
        all_trades = []
        current_time = end_time
        
        while current_time > start_time:
            try:
                params = {
                    "category": "linear",
                    "symbol": "BTCUSDT",
                    "limit": 1000,
                    "startTime": start_time,
                    "endTime": current_time
                }
                
                response = await self.bybit_client.fetch_my_trades(
                    symbol="BTCUSDT",
                    params=params
                )
                
                # 응답 구조 로깅
                logger.debug(f"API 응답: {response[:2]}")
                
                if not response:
                    break
                    
                # 응답 데이터를 포지션 형식으로 변환
                positions = []
                for trade in response:
                    position_data = {
                        'id': trade.get('info', {}).get('orderId'),
                        'timestamp': int(trade.get('info', {}).get('execTime')),
                        'symbol': 'BTCUSDT',
                        'side': trade.get('info', {}).get('side'),
                        'position_side': 'Long' if trade.get('info', {}).get('side') == 'Buy' else 'Short',
                        'type': trade.get('info', {}).get('orderType'),
                        'entry_price': float(trade.get('info', {}).get('execPrice')),
                        'exit_price': float(trade.get('info', {}).get('execPrice')),
                        'size': float(trade.get('info', {}).get('execQty')),
                        'leverage': 5,  # 기본값
                        'entry_value': float(trade.get('info', {}).get('execValue')),
                        'exit_value': float(trade.get('info', {}).get('execValue')),
                        'pnl': 0,  # 실제 PnL 계산 필요
                        'created_time': int(trade.get('info', {}).get('execTime')),
                        'closed_time': int(trade.get('info', {}).get('execTime')),
                        'closed_size': float(trade.get('info', {}).get('closedSize') or 0),
                        'exec_type': trade.get('info', {}).get('execType'),
                        'fill_count': 1
                    }
                    positions.append(position_data)
                
                all_trades.extend(positions)
                logger.debug(f"조회된 거래 수: {len(positions)}건 (총 {len(all_trades)}건)")
                
                if positions:
                    current_time = min(t['timestamp'] for t in positions) - 1
                    logger.debug(f"다음 조회 시작 시간: {datetime.fromtimestamp(current_time/1000)}")
                else:
                    break
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"거래 조회 중 오류 발생: {str(e)}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(1)
                break
        
        all_trades.sort(key=lambda x: x['timestamp'])
        return all_trades

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

    async def update_trades(self, force_full_update: bool = False):
        """거래 내역 업데이트"""
        try:
            current_time = int(time.time() * 1000)
            
            if force_full_update:
                last_update = current_time - (90 * 24 * 60 * 60 * 1000)  # 90일 전
            else:
                last_update = self.trade_store.get_last_update()
                if not last_update:
                    last_update = current_time - (90 * 24 * 60 * 60 * 1000)
            
            logger.info(f"거래 내역 업데이트 시작: {datetime.fromtimestamp(last_update/1000).strftime('%Y-%m-%d %H:%M:%S')} ~ 현재")
            
            while last_update < current_time:
                period_end = min(last_update + (7 * 24 * 60 * 60 * 1000), current_time)  # 7일 단위로 조회
                logger.info(f"조회 기간: {datetime.fromtimestamp(last_update/1000)} ~ {datetime.fromtimestamp(period_end/1000)}")
                
                new_trades = await self._fetch_trades_for_period(last_update, period_end)
                if new_trades:
                    # 각 거래를 개별적으로 저장
                    for trade in new_trades:
                        self.trade_store.save_trade(trade)
                    logger.info(f"새로운 거래 {len(new_trades)}건 저장 완료")
                
                # 마지막 업데이트 시간 저장
                self.trade_store.save_last_update(period_end)
                last_update = period_end
                
                await asyncio.sleep(0.5)  # API 레이트 리밋 고려
            
        except Exception as e:
            logger.error(f"거래 내역 업데이트 실패: {str(e)}")
            logger.error(traceback.format_exc())

    async def load_trades(self, start_time: int = None, end_time: int = None) -> List[Dict]:
        """거래 내역 조회"""
        return self.trade_store.get_trades(start_time, end_time)

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

    async def _process_trades(self, trades: List[Dict]) -> List[Dict]:
        """거래 내역 처리"""
        processed_trades = []
        for trade in trades:
            # CCXT 거래 데이터를 positions 형식으로 변환
            processed_trade = {
                "id": trade["id"],
                "timestamp": trade["timestamp"],
                "symbol": trade["symbol"].split("/")[0] + trade["symbol"].split(":")[1],
                "side": trade["side"].capitalize(),
                "position_side": "Long" if trade["side"] == "buy" else "Short",
                "type": trade["info"]["orderType"],
                "entry_price": float(trade["info"]["execPrice"]),
                "exit_price": float(trade["info"]["execPrice"]),
                "size": float(trade["info"]["execQty"]),
                "leverage": 5,  # 기본값 설정
                "entry_value": float(trade["info"]["execValue"]),
                "exit_value": float(trade["info"]["execValue"]),
                "pnl": 0,  # 실제 PnL 계산 필요
                "created_time": trade["timestamp"],
                "closed_time": trade["timestamp"],
                "closed_size": float(trade["info"]["closedSize"] or 0),
                "exec_type": trade["info"]["execType"],
                "fill_count": 1
            }
            processed_trades.append(processed_trade)

        return processed_trades 