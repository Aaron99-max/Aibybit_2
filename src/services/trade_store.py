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
        self._current_position = None  # 현재 활성 포지션
        self._position_history = []    # 포지션 히스토리
        self._load_positions()         # 초기화 시 포지션 데이터 로드

    def _load_positions(self):
        """저장된 포지션 데이터 로드"""
        try:
            positions = []
            # 최신 포지션 파일 찾기
            for year_dir in sorted(self.positions_dir.glob("*"), reverse=True):
                if not year_dir.is_dir():
                    continue
                for month_dir in sorted(year_dir.glob("*"), reverse=True):
                    if not month_dir.is_dir():
                        continue
                    for day_file in sorted(month_dir.glob("*.json"), reverse=True):
                        with open(day_file, 'r') as f:
                            data = json.load(f)
                            positions.extend(data)
                            if not self._current_position and data:
                                # 가장 최근 포지션을 현재 포지션으로 설정
                                self._current_position = data[-1]
                            break
                    if positions:
                        break
                if positions:
                    break
            self._position_history = positions
        except Exception as e:
            logger.error(f"포지션 데이터 로드 중 오류: {str(e)}")

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
                
                positions_by_date[date_str]['positions'].append(position)

            # 각 날짜별로 파일 저장
            for date_str, data in positions_by_date.items():
                month_str = data['month_str']
                positions = data['positions']
                
                # 파일 경로 설정
                file_path = self.positions_dir / month_str / f"{date_str}.json"
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 기존 데이터와 병합
                existing_positions = []
                if file_path.exists():
                    with open(file_path, 'r') as f:
                        existing_positions = json.load(f)
                
                # 새로운 포지션 추가
                existing_positions.extend(positions)
                
                # 파일 저장
                with open(file_path, 'w') as f:
                    json.dump(existing_positions, f, indent=2)
                
            return True
            
        except Exception as e:
            logger.error(f"포지션 저장 중 오류: {str(e)}")
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
                logger.info(f"날짜: {date_str}, 포지션 수: {len(daily_positions)}건")
                positions.extend(daily_positions)
                current += timedelta(days=1)
            
            logger.info(f"총 {len(positions)}건의 포지션 데이터 로드됨")
            return positions
            
        except Exception as e:
            logger.error(f"포지션 범위 조회 실패: {str(e)}")
            return []

    def get_daily_positions(self, date_str: str) -> List[Dict]:
        """일별 포지션 조회"""
        return self.get_positions(date_str=date_str)

    def has_positions(self, date_str: str) -> bool:
        """해당 날짜의 포지션 데이터가 있는지 확인"""
        try:
            month_str = date_str[:6]  # YYYYMM
            position_file = self.positions_dir / month_str / f"{date_str}.json"
            return position_file.exists()
            
        except Exception as e:
            logger.error(f"포지션 데이터 확인 실패: {str(e)}")
            return False

    def _save_last_update(self, timestamp: int):
        """마지막 업데이트 시간 저장"""
        with open(self.last_update_file, 'w') as f:
            json.dump({'last_update': timestamp}, f)

    def get_last_update(self) -> int:
        """마지막 업데이트 시간 조회"""
        try:
            if self.last_update_file.exists():
                with open(self.last_update_file, 'r') as f:
                    data = json.load(f)
                    return data.get('timestamp', 0)
            return 0
        except Exception as e:
            logger.error(f"마지막 업데이트 시간 조회 중 오류: {str(e)}")
            return 0

    def update_last_update(self):
        """마지막 업데이트 시간 저장"""
        try:
            current_time = int(time.time() * 1000)
            with open(self.last_update_file, 'w') as f:
                json.dump({
                    'timestamp': current_time,
                    'date': datetime.fromtimestamp(current_time/1000).strftime('%Y-%m-%d %H:%M:%S')
                }, f, indent=2)
        except Exception as e:
            logger.error(f"마지막 업데이트 시간 저장 중 오류: {str(e)}")

    def load_positions(self) -> List[Dict]:
        """저장된 모든 포지션 데이터 로드"""
        try:
            positions = []
            data_dir = Path("src/data/positions")
            
            # 모든 연도/월 디렉토리 순회
            for year_dir in sorted(data_dir.glob("*")):
                if not year_dir.is_dir():
                    continue
            
                # 각 월 디렉토리 내의 모든 JSON 파일 순회
                for day_file in sorted(year_dir.glob("*/*.json")):
                    with open(day_file, 'r') as f:
                        data = json.load(f)
                        
                        # 각 포지션의 ID와 파일명 출력
                        for p in data:
                            logger.info(f"파일: {day_file.name}, ID: {p.get('id')}, Side: {p.get('side')}")
                        
                        positions.extend(data)
            
            # 최종 데이터 확인
            logger.info("\n=== 최종 데이터 확인 ===")
            logger.info(f"총 포지션 수: {len(positions)}")
            
            # ID별 중복 체크
            id_counts = {}
            for p in positions:
                id = p.get('id')
                id_counts[id] = id_counts.get(id, 0) + 1
            
            # 중복된 ID 출력
            duplicates = {id: count for id, count in id_counts.items() if count > 1}
            if duplicates:
                logger.info("=== 중복된 ID 목록 ===")
                for id, count in duplicates.items():
                    logger.info(f"ID: {id} ({count}회)")
            
            return positions
            
        except Exception as e:
            logger.error(f"포지션 데이터 로드 중 오류: {str(e)}")
            return []

    def update_position(self, symbol: str, position_data: dict):
        """포지션 정보 업데이트"""
        self._current_position = position_data
        # 포지션 히스토리에 추가
        if position_data:
            self._position_history.append(position_data)
            self._save_position(position_data)

    def get_position(self, symbol: str) -> dict:
        """포지션 정보 조회"""
        return self._current_position if self._current_position else {}

    def _save_position(self, position_data: dict):
        """포지션 데이터 파일 저장"""
        try:
            timestamp = position_data.get('timestamp', int(time.time() * 1000))
            date = datetime.fromtimestamp(timestamp/1000)
            
            # 연/월/일 디렉토리 구조
            year_month = date.strftime('%Y%m')
            day = date.strftime('%Y%m%d')
            
            file_path = self.positions_dir / year_month / f"{day}.json"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 기존 데이터 로드 또는 새로운 리스트 생성
            positions = []
            if file_path.exists():
                with open(file_path, 'r') as f:
                    positions = json.load(f)
            
            # 새로운 포지션 추가
            positions.append(position_data)
            
            # 파일 저장
            with open(file_path, 'w') as f:
                json.dump(positions, f, indent=2)
            
        except Exception as e:
            logger.error(f"포지션 저장 중 오류: {str(e)}")