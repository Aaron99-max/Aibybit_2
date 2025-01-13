from pathlib import Path
from datetime import datetime
import json
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

class GPTAnalysisStore:
    def __init__(self):
        """GPT 분석 결과 저장소"""
        self.base_dir = Path('src/data')  # v2 제거
        
        # 디렉토리 구조 생성
        self.dirs = {
            'analysis': self.base_dir / 'analysis',  # GPT 분석 결과
            'trades': self.base_dir / 'trades'       # 거래 분석 결과
        }
        
        # 디렉토리 생성
        for dir_path in self.dirs.values():
            dir_path.mkdir(parents=True, exist_ok=True)

    def save_analysis(self, analysis: Dict) -> bool:
        """GPT 분석 결과 저장"""
        try:
            timeframe = analysis.get('timeframe', '15m')
            date_str = datetime.fromtimestamp(analysis['timestamp']/1000).strftime('%Y%m%d')
            
            # 날짜/시간대별로 저장
            save_dir = self.dirs['analysis'] / date_str / timeframe
            save_dir.mkdir(parents=True, exist_ok=True)
            
            # 파일명에 timestamp 포함
            filename = f"analysis_{int(analysis['timestamp'])}.json"
            save_path = save_dir / filename
            
            with open(save_path, 'w') as f:
                json.dump(analysis, f, indent=2)
                
            return True
            
        except Exception as e:
            logger.error(f"GPT 분석 결과 저장 중 오류: {str(e)}")
            return False

    def load_latest_analysis(self, timeframe: str) -> Optional[Dict]:
        """최신 분석 결과 로드"""
        try:
            # 오늘 날짜 디렉토리 확인
            date_str = datetime.now().strftime('%Y%m%d')
            analysis_dir = self.dirs['analysis'] / date_str / timeframe
            
            if not analysis_dir.exists():
                return None
                
            # 가장 최근 파일 찾기
            files = list(analysis_dir.glob('analysis_*.json'))
            if not files:
                return None
                
            latest_file = max(files, key=lambda x: int(x.stem.split('_')[1]))
            
            with open(latest_file, 'r') as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"최신 분석 로드 중 오류: {str(e)}")
            return None

    def load_analysis_at_time(self, timestamp: int) -> Optional[Dict]:
        """특정 시점의 분석 결과 로드"""
        try:
            date_str = datetime.fromtimestamp(timestamp/1000).strftime('%Y%m%d')
            
            analyses = []
            # 모든 시간대 검색
            for timeframe in ['15m', '1h', '4h', '1d']:
                timeframe_dir = self.dirs['analysis'] / date_str / timeframe
                if not timeframe_dir.exists():
                    continue
                    
                for file_path in timeframe_dir.glob('analysis_*.json'):
                    with open(file_path, 'r') as f:
                        analysis = json.load(f)
                        analyses.append(analysis)
            
            if not analyses:
                return None
                
            # 가장 가까운 시점의 분석 찾기
            return min(analyses, key=lambda x: abs(x['timestamp'] - timestamp))
            
        except Exception as e:
            logger.error(f"분석 결과 로드 중 오류: {str(e)}")
            return None

    def get_analyses_in_range(self, start_time: int, end_time: int) -> List[Dict]:
        """특정 기간의 분석 결과들 로드"""
        try:
            start_date = datetime.fromtimestamp(start_time/1000)
            end_date = datetime.fromtimestamp(end_time/1000)
            
            analyses = []
            current_date = start_date
            
            while current_date <= end_date:
                date_str = current_date.strftime('%Y%m%d')
                
                # 해당 날짜의 모든 시간대 검색
                for timeframe in ['15m', '1h', '4h', '1d']:
                    analysis_dir = self.dirs['analysis'] / date_str / timeframe
                    if not analysis_dir.exists():
                        continue
                        
                    # 해당 시간대의 모든 분석 파일 검색
                    for file_path in analysis_dir.glob('analysis_*.json'):
                        with open(file_path, 'r') as f:
                            analysis = json.load(f)
                            if start_time <= analysis['timestamp'] <= end_time:
                                analyses.append(analysis)
                
                current_date = current_date.replace(day=current_date.day + 1)
                
            return analyses
            
        except Exception as e:
            logger.error(f"기간별 분석 결과 로드 중 오류: {str(e)}")
            return [] 