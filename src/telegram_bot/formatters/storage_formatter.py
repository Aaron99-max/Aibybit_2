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
        
    def save_analysis(self, timeframe: str, analysis: Dict) -> bool:
        """분석 결과 저장"""
        try:
            # 저장 시간과 타임스탬프 추가
            now = datetime.now()
            # 문자열이면 그대로 사용, 딕셔너리면 복사
            analysis_data = analysis.copy() if isinstance(analysis, dict) else analysis
            
            if isinstance(analysis_data, dict):
                # 숫자 데이터 소수점 정리
                if 'market_summary' in analysis_data:
                    market = analysis_data['market_summary']
                    market['current_price'] = round(float(market.get('current_price', 0)), 2)

                if 'technical_analysis' in analysis_data:
                    tech = analysis_data['technical_analysis']
                    if 'indicators' in tech:
                        indicators = tech['indicators']
                        indicators['rsi'] = round(float(indicators.get('rsi', 0)), 2)

                if 'trading_signals' in analysis_data:
                    signals = analysis_data['trading_signals']
                    signals['entry_price'] = round(float(signals.get('entry_price', 0)), 2)
                    signals['stop_loss'] = round(float(signals.get('stop_loss', 0)), 1)
                    signals['take_profit1'] = round(float(signals.get('take_profit1', 0)), 2)
                    signals['take_profit2'] = round(float(signals.get('take_profit2', 0)), 2)

                analysis_data['saved_at'] = now.strftime("%Y-%m-%d %H:%M:%S KST")
                analysis_data['timestamp'] = int(now.timestamp() * 1000)
            
            # 파일 경로 설정
            filename = f"analysis_{timeframe}.json"
            filepath = os.path.join(self.analysis_dir, filename)
            
            # 디렉토리 생성
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # 파일 직접 저장
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(analysis_data, f, ensure_ascii=False, indent=2)
                
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
