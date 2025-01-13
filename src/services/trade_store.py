from pathlib import Path
from datetime import datetime, timedelta
import json
import logging
from typing import Dict, List, Optional
import traceback

logger = logging.getLogger(__name__)

class TradeStore:
    def __init__(self):
        """거래 데이터 저장소"""
        self.base_dir = Path('src/data')
        self.trades_dir = self.base_dir / 'trades'
        self.trades_dir.mkdir(parents=True, exist_ok=True)
        self.last_update_file = self.base_dir / 'last_update.json'

    def save_trade(self, trade: Dict) -> bool:
        """거래 기록 저장"""
        try:
            date_str = datetime.fromtimestamp(trade['timestamp']/1000).strftime('%Y%m%d')
            trade_dir = self.trades_dir / date_str
            trade_dir.mkdir(parents=True, exist_ok=True)

            # 거래 기록 파일
            trades_file = trade_dir / 'trades.json'
            
            # 기존 거래 로드 또는 새로 생성
            trades = []
            if trades_file.exists():
                with open(trades_file, 'r') as f:
                    trades = json.load(f)
                
            # 중복 체크
            trade_id = trade.get('id') or trade.get('order_id')
            if trade_id:
                # 이미 존재하는 거래인지 확인
                if any(t.get('id') == trade_id for t in trades):
                    logger.debug(f"이미 저장된 거래입니다: {trade_id}")
                    return True

            # 새 거래 추가
            trades.append(trade)
            
            # 저장
            with open(trades_file, 'w') as f:
                json.dump(trades, f, indent=2)

            return True

        except Exception as e:
            logger.error(f"거래 저장 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def get_trades_with_analysis(self, start_time: int = None, end_time: int = None) -> List[Dict]:
        """거래 내역 조회"""
        try:
            trades = []
            seen_trade_ids = set()
            
            for date_dir in sorted(self.trades_dir.iterdir(), reverse=True):
                if not date_dir.is_dir():
                    continue
                
                trades_file = date_dir / 'trades.json'
                if not trades_file.exists():
                    continue
                
                with open(trades_file, 'r') as f:
                    daily_trades = json.load(f)
                
                for trade in daily_trades:
                    trade_id = trade.get('id')
                    if trade_id in seen_trade_ids:
                        continue
                        
                    if start_time and end_time:
                        timestamp = trade.get('timestamp', 0)
                        if not (start_time <= timestamp <= end_time):
                            continue
                    
                    seen_trade_ids.add(trade_id)
                    trades.append(trade)
            
            trades.sort(key=lambda x: x.get('timestamp', 0))
            return trades
            
        except Exception as e:
            logger.error(f"거래 내역 조회 중 오류: {str(e)}")
            return [] 

    def get_all_trades(self) -> List[Dict]:
        """모든 거래 내역 조회"""
        try:
            trades = []
            seen_trade_ids = set()
            
            # 모든 날짜 폴더에서 trades.json 파일 읽기
            for date_dir in sorted(self.trades_dir.iterdir(), reverse=True):
                if not date_dir.is_dir():
                    continue
                
                trades_file = date_dir / 'trades.json'
                if not trades_file.exists():
                    continue
                
                with open(trades_file, 'r') as f:
                    daily_trades = json.load(f)
                
                # 중복 제거하면서 거래 추가
                for trade in daily_trades:
                    trade_id = trade.get('id')
                    if trade_id and trade_id not in seen_trade_ids:
                        seen_trade_ids.add(trade_id)
                        trades.append(trade)
            
            # 시간순 정렬
            trades.sort(key=lambda x: x.get('timestamp', 0))
            return trades
            
        except Exception as e:
            logger.error(f"전체 거래 내역 조회 중 오류: {str(e)}")
            return [] 

    def save_last_update(self, timestamp: int):
        """마지막 업데이트 시간 저장"""
        with open(self.last_update_file, 'w') as f:
            json.dump({'last_update': timestamp}, f)

    def get_last_update(self) -> int:
        """마지막 업데이트 시간 조회"""
        if self.last_update_file.exists():
            with open(self.last_update_file, 'r') as f:
                data = json.load(f)
                return data.get('last_update', 0)
        return 0 