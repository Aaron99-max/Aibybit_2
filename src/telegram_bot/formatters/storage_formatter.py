import os
import json
import logging
from typing import Dict, Optional, Set, List
from datetime import datetime, timezone, timedelta
from pathlib import Path
from ..utils.time_utils import TimeUtils
from config import config

logger = logging.getLogger(__name__)

class StorageFormatter:
    """분석 결과 저장 및 포맷팅 클래스"""

    VALID_TIMEFRAMES = {'15m', '1h', '4h', '1d', 'final'}
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    
    def __init__(self):
        self.analysis_dir = config.data_dir / 'analysis'
        os.makedirs(self.analysis_dir, exist_ok=True)
        
    def save_analysis(self, analysis: Dict, timeframe: str) -> bool:
        """분석 결과 저장"""
        try:
            # 저장 시간 추가
            analysis['saved_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
            
            # 파일 경로 설정
            filename = f"analysis_{timeframe}.json"
            filepath = os.path.join(self.analysis_dir, filename)
            
            # 기존 데이터 로드
            existing_data = self.load_analysis(timeframe) or {}
            
            # 새 데이터 병합
            existing_data.update(analysis)
            
            # 파일 저장
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
                
            logger.info(f"{timeframe} 분석 결과 저장 완료: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"분석 결과 저장 중 오류: {str(e)}")
            return False
            
    def load_analysis(self, timeframe: str) -> Optional[Dict]:
        """저장된 분석 결과 로드"""
        try:
            filepath = os.path.join(self.analysis_dir, f"analysis_{timeframe}.json")
            if not os.path.exists(filepath):
                return None
                
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            return data
            
        except Exception as e:
            logger.error(f"분석 결과 로드 중 오류: {str(e)}")
            return None
            
    def get_last_analysis(self, timeframe: str) -> Optional[Dict]:
        """마지막 분석 결과 조회"""
        try:
            data = self.load_analysis(timeframe)
            if not data:
                return None
                
            # 저장 시간 확인
            saved_at = data.get('saved_at')
            if not saved_at:
                return None
                
            # 저장 시간이 오래된 경우 None 반환
            saved_time = datetime.strptime(saved_at, "%Y-%m-%d %H:%M:%S KST")
            if (datetime.now() - saved_time).total_seconds() > 3600:  # 1시간
                return None
                
            return data
            
        except Exception as e:
            logger.error(f"마지막 분석 결과 조회 중 오류: {str(e)}")
            return None
