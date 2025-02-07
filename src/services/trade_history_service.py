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
        """초기 포지션 정보 조회 및 저장"""
        try:
            end_timestamp = int(time.time() * 1000)
            start_timestamp = end_timestamp - (90 * 24 * 60 * 60 * 1000)
            
            logger.info("=== 포지션 정보 초기화 시작 ===")
            logger.info(f"조회 기간: {datetime.fromtimestamp(start_timestamp/1000).strftime('%Y-%m-%d')} ~ {datetime.fromtimestamp(end_timestamp/1000).strftime('%Y-%m-%d')}")
            
            # 마지막 업데이트 시간 확인
            last_update = self.trade_store.get_last_update()
            
            # 저장된 데이터 확인
            existing_positions = self.trade_store.get_positions(start_timestamp, end_timestamp)
            
            if not existing_positions:
                logger.info("기존 데이터가 없습니다. 전체 기간 조회를 시작합니다.")
                await self.update_positions(force_full_update=True)
            elif not last_update or (end_timestamp - last_update) > (24 * 60 * 60 * 1000):  # 하루 이상 지났으면
                logger.info(f"마지막 업데이트 이후 {((end_timestamp - last_update)/1000/60/60):.1f}시간 경과")
                logger.info("최신 데이터만 업데이트합니다.")
                await self.update_positions(start_time=last_update)
            else:
                logger.info(f"기존 데이터: {len(existing_positions)}건")
                logger.info("최신 데이터입니다. 업데이트가 필요하지 않습니다.")
            
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
                logger.debug(f"API 응답: {response[:2]}")  # 처음 2개 항목만 로깅
                
                if not response:
                    break
                    
                # 응답 데이터 변환
                trades = []
                for trade in response:
                    trade_data = {
                        'id': trade.get('id'),
                        'timestamp': int(trade.get('timestamp')),
                        'datetime': trade.get('datetime'),
                        'symbol': trade.get('symbol'),
                        'side': trade.get('side'),
                        'price': float(trade.get('price', 0)),
                        'amount': float(trade.get('amount', 0)),
                        'cost': float(trade.get('cost', 0)),
                        'info': {
                            'symbol': trade.get('info', {}).get('symbol'),
                            'execFee': trade.get('info', {}).get('execFee'),
                            'execId': trade.get('info', {}).get('execId'),
                            'execPrice': trade.get('info', {}).get('execPrice'),
                            'execQty': trade.get('info', {}).get('execQty'),
                            'execType': trade.get('info', {}).get('execType'),
                            'execValue': trade.get('info', {}).get('execValue'),
                            'feeRate': trade.get('info', {}).get('feeRate'),
                            'lastLiquidityInd': trade.get('info', {}).get('lastLiquidityInd'),
                            'orderId': trade.get('info', {}).get('orderId'),
                            'orderLinkId': trade.get('info', {}).get('orderLinkId'),
                            'orderPrice': trade.get('info', {}).get('orderPrice'),
                            'orderQty': trade.get('info', {}).get('orderQty'),
                            'orderType': trade.get('info', {}).get('orderType'),
                            'stopOrderType': trade.get('info', {}).get('stopOrderType'),
                            'side': trade.get('info', {}).get('side'),
                            'execTime': trade.get('info', {}).get('execTime'),
                            'closedSize': trade.get('info', {}).get('closedSize', 0),
                            'markPrice': trade.get('info', {}).get('markPrice', 0)
                        }
                    }
                    trades.append(trade_data)
                
                all_trades.extend(trades)
                logger.debug(f"조회된 거래 수: {len(trades)}건 (총 {len(all_trades)}건)")
                
                if trades:
                    current_time = min(t['timestamp'] for t in trades) - 1
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

    async def get_positions(self, start_time: int, end_time: int) -> List[Dict]:
        """포지션 정보 조회"""
        try:
            params = {
                "category": "linear",
                "symbol": "BTCUSDT",
                "limit": 100,
                "startTime": str(start_time),
                "endTime": str(end_time)
            }
            
            response = await self.bybit_client.v5_get_closed_pnl(params)
            if response and response.get('retCode') == 0:
                positions = response.get('result', {}).get('list', [])
                if positions:
                    logger.info(f"포지션 {len(positions)}건 조회됨")
                    # API 응답 형태 확인을 위한 로그
                    logger.info(f"첫 번째 포지션 데이터: {positions[0]}")
                    
                    # 포지션 데이터 전처리
                    processed_positions = []
                    for p in positions:
                        # 포지션 방향 결정
                        side = p.get('side')
                        exec_type = p.get('execType')
                        closed_size = float(p.get('closedSize', 0))
                        
                        # 실제 포지션 방향 계산
                        is_long = (side == 'Buy' and exec_type == 'Trade') or \
                                 (side == 'Sell' and exec_type == 'Trade' and closed_size > 0)
                        
                        processed_positions.append({
                            **p,
                            'position_side': 'Long' if is_long else 'Short'
                        })
                    
                    return processed_positions
                return []
            
            return []
            
        except Exception as e:
            logger.error(f"포지션 조회 중 오류: {str(e)}")
            return []

    async def update_positions(self, force_full_update: bool = False, start_time: int = None):
        """포지션 정보 업데이트"""
        try:
            end_time = int(time.time() * 1000)
            
            if force_full_update:
                start_time = end_time - (90 * 24 * 60 * 60 * 1000)  # 90일 전
            elif not start_time:
                start_time = self.trade_store.get_last_update() or (end_time - 90 * 24 * 60 * 60 * 1000)
            
            logger.info(f"포지션 정보 업데이트 시작: {datetime.fromtimestamp(start_time/1000).strftime('%Y-%m-%d')} ~ {datetime.fromtimestamp(end_time/1000).strftime('%Y-%m-%d')}")
            
            # 7일씩 나눠서 조회
            current_start = start_time
            while current_start < end_time:
                current_end = min(current_start + (7 * 24 * 60 * 60 * 1000), end_time)
                
                if current_end <= current_start:
                    break
                    
                logger.info(f"조회 기간: {datetime.fromtimestamp(current_start/1000).strftime('%Y-%m-%d')} ~ {datetime.fromtimestamp(current_end/1000).strftime('%Y-%m-%d')}")
                
                positions = await self.get_positions(current_start, current_end)
                if positions:
                    self.trade_store.save_positions(positions)
                    logger.info(f"포지션 정보 {len(positions)}건 저장 완료")
                
                current_start = current_end
                await asyncio.sleep(0.5)
            
            # 마지막 업데이트 시간 저장
            self.trade_store.save_last_update(end_time)
            
        except Exception as e:
            logger.error(f"포지션 정보 업데이트 실패: {str(e)}")

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