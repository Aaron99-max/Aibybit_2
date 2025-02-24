from pathlib import Path
from datetime import datetime
import json
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

class AnalysisStore:
    def __init__(self):
        """분석 결과 저장소 초기화"""
        self.base_dir = Path('src/data')
        
        # 디렉토리 구조 생성
        self.dirs = {
            'analysis': self.base_dir / 'analysis',
            'history': self.base_dir / 'analysis_history',
            'gpt': self.base_dir / 'analysis_history/gpt',
            'trades': self.base_dir / 'analysis_history/trades'
        }
        
        # 모든 디렉토리 생성
        for dir_path in self.dirs.values():
            dir_path.mkdir(parents=True, exist_ok=True)

    def save_gpt_analysis(self, analysis: Dict, timeframe: str) -> bool:
        """GPT 분석 결과 저장"""
        try:
            date_str = datetime.fromtimestamp(analysis['timestamp']/1000).strftime('%Y%m%d')
            
            # 날짜/시간대별 디렉토리 생성
            save_dir = self.dirs['gpt'] / date_str / timeframe
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

    def save_trade_analysis(self, analysis: Dict, category: str) -> bool:
        """거래 분석 결과 저장"""
        try:
            date_str = datetime.now().strftime('%Y%m%d')
            
            # 날짜/카테고리별 디렉토리 생성
            save_dir = self.dirs['trades'] / date_str / category
            save_dir.mkdir(parents=True, exist_ok=True)
            
            # 파일명에 timestamp 포함
            filename = f"analysis_{int(datetime.now().timestamp()*1000)}.json"
            save_path = save_dir / filename
            
            with open(save_path, 'w') as f:
                json.dump(analysis, f, indent=2)
                
            return True
            
        except Exception as e:
            logger.error(f"거래 분석 결과 저장 중 오류: {str(e)}")
            return False 