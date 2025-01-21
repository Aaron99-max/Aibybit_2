from pathlib import Path
from datetime import datetime, timedelta
import json
import logging
from typing import Dict, List, Optional
import traceback
import os

logger = logging.getLogger(__name__)

class TradeStore:
    def __init__(self):
        """거래 데이터 저장소"""
        self.base_dir = Path('src/data')
        self.trades_dir = self.base_dir / 'trades'
        self.trades_dir.mkdir(parents=True, exist_ok=True)
        self.last_update_file = self.base_dir / 'last_update.json'

    def save_trade(self, trade: Dict) -> bool:
        """거래 내역 저장"""
        try:
            trade_info = trade.get('info', {})
            trade_data = {
                **trade,
                'execRealizedPnl': float(trade_info.get('execRealizedPnl', 0)) if trade_info.get('execRealizedPnl') else 0,
                'markPrice': float(trade_info.get('markPrice', 0)),
                'execPrice': float(trade_info.get('execPrice', 0)),
                'orderPrice': float(trade_info.get('orderPrice', 0)),
                'orderQty': float(trade_info.get('orderQty', 0)),
                'closedSize': float(trade_info.get('closedSize', 0)),
                'execQty': float(trade_info.get('execQty', 0)),
            }
            # 날짜 정보 추출
            trade_date = datetime.fromtimestamp(trade['timestamp']/1000)
            month_str = trade_date.strftime('%Y%m')  # 예: 202412
            date_str = trade_date.strftime('%Y%m%d')  # 예: 20241231
            
            # 월별 폴더 생성
            month_dir = self.trades_dir / month_str
            month_dir.mkdir(parents=True, exist_ok=True)

            # 일별 거래 파일
            trades_file = month_dir / f"{date_str}.json"
            
            # 기존 거래 로드 또는 새로 생성
            trades = []
            if trades_file.exists():
                with open(trades_file, 'r') as f:
                    trades = json.load(f)
                
            # 중복 체크
            trade_id = trade.get('id') or trade.get('order_id')
            if trade_id:
                if any(t.get('id') == trade_id for t in trades):
                    logger.debug(f"이미 저장된 거래입니다: {trade_id}")
                    return True

            # 새 거래 추가
            trades.append(trade_data)
            
            # 저장
            with open(trades_file, 'w') as f:
                json.dump(trades, f, indent=2)

            return True

        except Exception as e:
            logger.error(f"거래 저장 실패: {str(e)}")
            return False

    def get_trades(self, start_time: int = None, end_time: int = None) -> List[Dict]:
        """거래 내역 조회 (시간 필터링)"""
        try:
            trades = []
            
            # 월별 폴더 순회
            for month_dir in sorted(self.trades_dir.iterdir()):
                if not month_dir.is_dir():
                    continue
                
                # 일별 파일 순회
                for trade_file in sorted(month_dir.iterdir()):
                    if not trade_file.suffix == '.json':
                        continue
                    
                    with open(trade_file, 'r') as f:
                        daily_trades = json.load(f)
                    
                    # 시간 필터링
                    if start_time and end_time:
                        daily_trades = [
                            trade for trade in daily_trades
                            if start_time <= trade['timestamp'] <= end_time
                        ]
                    
                    trades.extend(daily_trades)
            
            # 전체 거래를 시간순으로 정렬
            trades.sort(key=lambda x: x['timestamp'])
            
            logger.info(f"총 {len(trades)}건의 거래 데이터 로드됨")
            if trades:
                logger.info(f"첫 거래: {datetime.fromtimestamp(trades[0]['timestamp']/1000)}")
                logger.info(f"마지막 거래: {datetime.fromtimestamp(trades[-1]['timestamp']/1000)}")
                
            return trades
            
        except Exception as e:
            logger.error(f"거래 내역 조회 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return []

    def get_all_trades(self):
        """모든 거래 데이터 조회"""
        trades = []
        
        # 월별 폴더 조회 (YYYYMM 형식으로 정렬)
        month_folders = [d for d in os.listdir(self.trades_dir) 
                        if os.path.isdir(os.path.join(self.trades_dir, d)) 
                        and d.startswith('2024')]
        month_folders.sort()  # 월별 정렬
        
        logger.info(f"조회할 월별 폴더: {month_folders}")
        
        # 각 월별 폴더에서 파일 읽기
        for month in month_folders:
            month_dir = os.path.join(self.trades_dir, month)
            json_files = [f for f in os.listdir(month_dir) 
                         if f.endswith('.json')]
            
            # 날짜순 정렬 (YYYYMMDD 기준)
            json_files.sort(key=lambda x: x.replace('.json', ''))
            
            logger.info(f"{month} 폴더의 파일 수: {len(json_files)}")
            logger.debug(f"{month} 폴더의 파일 목록: {json_files}")
            
            # 각 JSON 파일 읽기
            for file_name in json_files:
                file_path = os.path.join(month_dir, file_name)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_trades = json.load(f)
                        if isinstance(file_trades, list):
                            trades.extend(file_trades)
                            logger.debug(f"{file_name}: {len(file_trades)}건 로드")
                        else:
                            logger.warning(f"잘못된 형식의 거래 데이터: {file_path}")
                except Exception as e:
                    logger.error(f"파일 읽기 오류 ({file_path}): {str(e)}")
                    continue
        
        # 중복 제거 및 정렬
        unique_trades = self._remove_duplicates(trades)
        sorted_trades = sorted(unique_trades, key=lambda x: x['timestamp'])
        
        # 날짜별 거래 수 확인
        date_counts = {}
        for trade in sorted_trades:
            date = datetime.fromtimestamp(trade['timestamp']/1000).date()
            if date not in date_counts:
                date_counts[date] = 0
            date_counts[date] += 1
        
        logger.info("\n=== 거래 데이터 로드 결과 ===")
        logger.info(f"총 거래: {len(trades)}건")
        logger.info(f"고유 거래: {len(unique_trades)}건")
        logger.info("\n날짜별 거래 수:")
        for date in sorted(date_counts.keys()):
            logger.info(f"- {date}: {date_counts[date]}건")
        
        return sorted_trades

    def _remove_duplicates(self, trades):
        """중복 거래 제거"""
        seen = set()
        unique_trades = []
        
        for trade in trades:
            trade_id = trade.get('id')
            if trade_id and trade_id not in seen:
                seen.add(trade_id)
                unique_trades.append(trade)
        
        return unique_trades

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