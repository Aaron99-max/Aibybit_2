from pathlib import Path
from datetime import datetime
import json
import logging
from typing import Dict, List
import time

logger = logging.getLogger(__name__)

class TradeStore:
    def __init__(self):
        """포지션 데이터 저장소"""
        self.base_dir = Path('src/data')
        self.positions_dir = self.base_dir / 'positions'
        self.positions_dir.mkdir(parents=True, exist_ok=True)
        self.last_update_file = self.base_dir / 'last_update.json'

    def save_positions(self, positions: List[Dict]) -> bool:
        """포지션 정보 저장"""
        try:
            for position in positions:
                # API 응답에서 실제 포지션 시간 추출
                timestamp = int(position.get('createdTime', 0))
                if not timestamp:
                    logger.warning(f"타임스탬프 없는 포지션 데이터: {position}")
                    continue
                
                position_date = datetime.fromtimestamp(timestamp/1000)
                month_str = position_date.strftime('%Y%m')
                date_str = position_date.strftime('%Y%m%d')
                
                # 월별 폴더 생성
                month_dir = self.positions_dir / month_str
                month_dir.mkdir(parents=True, exist_ok=True)
                
                # 일별 포지션 파일
                position_file = month_dir / f"{date_str}.json"
                
                # 기존 포지션 로드 또는 새로 생성
                positions_data = []
                if position_file.exists():
                    with open(position_file, 'r') as f:
                        positions_data = json.load(f)
                
                # 중복 체크 및 저장
                position_id = position.get('orderId')
                if not any(p.get('id') == position_id for p in positions_data):
                    position_data = {
                        'id': position_id,
                        'timestamp': timestamp,
                        'side': position.get('side'),
                        'entry_price': float(position.get('avgEntryPrice', 0)),
                        'exit_price': float(position.get('avgExitPrice', 0)),
                        'size': float(position.get('qty', 0)),
                        'leverage': int(position.get('leverage', 1)),
                        'type': position.get('orderType'),
                        'value': float(position.get('cumEntryValue', 0)),
                        'pnl': float(position.get('closedPnl', 0))
                    }
                    positions_data.append(position_data)
                    
                    with open(position_file, 'w') as f:
                        json.dump(positions_data, f, indent=2)
                
                logger.info(f"포지션 저장됨: {date_str} - {position_data['side']} {position_data['size']} @ {position_data['entry_price']}")
        
            return True
            
        except Exception as e:
            logger.error(f"포지션 저장 실패: {str(e)}")
            return False

    def get_positions(self, start_time: int = None, end_time: int = None) -> List[Dict]:
        """포지션 정보 조회"""
        try:
            positions = []
            
            start_date = datetime.fromtimestamp(start_time/1000) if start_time else None
            end_date = datetime.fromtimestamp(end_time/1000) if end_time else None
            
            for month_dir in sorted(self.positions_dir.iterdir()):
                if not month_dir.is_dir() or not month_dir.name.isdigit():
                    continue
                
                month_date = datetime.strptime(month_dir.name, '%Y%m')
                if (start_date and month_date.replace(day=1) < start_date.replace(day=1)) or \
                   (end_date and month_date.replace(day=1) > end_date.replace(day=1)):
                    continue
                
                for position_file in sorted(month_dir.iterdir()):
                    if not position_file.suffix == '.json':
                        continue
                    
                    file_date = datetime.strptime(position_file.stem, '%Y%m%d')
                    if (start_date and file_date.date() < start_date.date()) or \
                       (end_date and file_date.date() > end_date.date()):
                        continue
                    
                    with open(position_file, 'r') as f:
                        daily_positions = json.load(f)
                        positions.extend(daily_positions)
            
            return sorted(positions, key=lambda x: x.get('timestamp', 0))
            
        except Exception as e:
            logger.error(f"포지션 조회 실패: {str(e)}")
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