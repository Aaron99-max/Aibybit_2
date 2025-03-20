from pathlib import Path
from datetime import datetime, timedelta
import json
import logging
from typing import Dict, List
import time
import traceback

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
            # 날짜별로 포지션 그룹화
            positions_by_date = {}
            for position in positions:
                timestamp = position.get('timestamp')
                if not timestamp:
                    logger.warning(f"타임스탬프 없는 포지션 데이터: {position}")
                    continue

                position_date = datetime.fromtimestamp(timestamp/1000)
                date_str = position_date.strftime('%Y%m%d')
                month_str = position_date.strftime('%Y%m')
                
                if date_str not in positions_by_date:
                    positions_by_date[date_str] = {
                        'month_str': month_str,
                        'positions': []
                    }
                
                # 포지션 데이터 변환 (필수 필드만 저장)
                position_data = {
                    'id': position.get('id'),
                    'timestamp': timestamp,
                    'symbol': position.get('symbol'),
                    'side': position.get('side'),
                    'position_side': position.get('position_side'),
                    'size': float(position.get('size', 0)),
                    'entry_price': float(position.get('entry_price', 0)),
                    'exit_price': float(position.get('exit_price', 0)),
                    'leverage': int(position.get('leverage', 1)),
                    'value': float(position.get('value', 0)),
                    'pnl': float(position.get('pnl', 0))
                }
                
                positions_by_date[date_str]['positions'].append(position_data)
            
            # 날짜별로 파일 저장
            for date_str, data in positions_by_date.items():
                month_str = data['month_str']
                positions_data = data['positions']
                
                # 저장 경로 생성
                month_dir = self.positions_dir / month_str
                month_dir.mkdir(exist_ok=True)
                position_file = month_dir / f"{date_str}.json"
                
                # 기존 데이터 로드
                existing_positions = []
                if position_file.exists():
                    with open(position_file, 'r') as f:
                        existing_positions = json.load(f)
                
                # 기존 데이터와 새 데이터 병합 (중복 제거)
                existing_ids = {p['id']: i for i, p in enumerate(existing_positions)}
                
                for new_position in positions_data:
                    position_id = new_position['id']
                    if position_id in existing_ids:
                        # 기존 포지션 업데이트
                        existing_positions[existing_ids[position_id]] = new_position
                    else:
                        # 새 포지션 추가
                        existing_positions.append(new_position)
                
                # timestamp 기준으로 정렬
                existing_positions.sort(key=lambda x: x['timestamp'], reverse=True)
                
                # 파일 저장
                with open(position_file, 'w') as f:
                    json.dump(existing_positions, f, indent=2)
                
                # 마지막 업데이트 시간 저장
                if positions_data:
                    latest_timestamp = max(p['timestamp'] for p in positions_data)
                    self.save_last_update(latest_timestamp)

            return True

        except Exception as e:
            logger.error(f"포지션 저장 중 오류 발생: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def get_positions(self, start_time=None, end_time=None, date_str=None) -> List[Dict]:
        """포지션 조회"""
        try:
            # date_str이 주어진 경우
            if date_str:
                month_str = date_str[:6]  # YYYYMM
                position_file = self.positions_dir / month_str / f"{date_str}.json"
                
                if not position_file.exists():
                    return []
                
                with open(position_file, 'r') as f:
                    return json.load(f)
            
            # timestamp 범위가 주어진 경우
            elif start_time and end_time:
                start_date = datetime.fromtimestamp(start_time/1000)
                end_date = datetime.fromtimestamp(end_time/1000)
                
                start_str = start_date.strftime('%Y%m%d')
                end_str = end_date.strftime('%Y%m%d')
                
                return self.get_positions_by_date_range(start_str, end_str)
            
            return []
                
        except Exception as e:
            logger.error(f"포지션 조회 실패: {str(e)}")
            return []

    def get_positions_by_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        """날짜 범위의 포지션 조회"""
        try:
            positions = []
            
            # 시작일과 종료일을 datetime으로 변환
            start = datetime.strptime(start_date, '%Y%m%d')
            end = datetime.strptime(end_date, '%Y%m%d')
            
            logger.info(f"날짜 범위 조회: {start_date} ~ {end_date}")
            
            # 각 날짜별로 포지션 데이터 수집
            current = start
            while current <= end:
                date_str = current.strftime('%Y%m%d')
                daily_positions = self.get_positions(date_str=date_str)
                positions.extend(daily_positions)
                current += timedelta(days=1)
            
            # timestamp 기준으로 정렬
            positions.sort(key=lambda x: x['timestamp'], reverse=True)
            return positions
            
        except Exception as e:
            logger.error(f"포지션 범위 조회 실패: {str(e)}")
            return []

    def get_daily_positions(self, date_str: str) -> List[Dict]:
        """일별 포지션 조회"""
        return self.get_positions(date_str=date_str)

    def get_last_update(self) -> int:
        """마지막 업데이트 시간 조회"""
        try:
            if self.last_update_file.exists():
                with open(self.last_update_file, 'r') as f:
                    data = json.load(f)
                    return data.get('last_update', 0)
            return 0
        except Exception as e:
            logger.error(f"마지막 업데이트 시간 로드 실패: {e}")
            return 0
            
    def save_last_update(self, timestamp: int):
        """마지막 업데이트 시간 저장"""
        try:
            with open(self.last_update_file, 'w') as f:
                json.dump({'last_update': timestamp}, f)
        except Exception as e:
            logger.error(f"마지막 업데이트 시간 저장 실패: {e}")