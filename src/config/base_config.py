import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class BaseConfig:
    """설정 기본 클래스"""
    
    def __init__(self):
        self.config_dir = Path(__file__).parent / 'data'
        self._cache = {}
        
    def load_json_config(self, filename: str) -> Dict:
        """JSON 설정 파일 로드"""
        try:
            filepath = self.config_dir / filename
            if not filepath.exists():
                logger.warning(f"설정 파일 없음: {filepath}")
                return {}
                
            if filepath in self._cache:
                return self._cache[filepath]
                
            with open(filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self._cache[filepath] = config
                return config
                
        except Exception as e:
            logger.error(f"설정 파일 로드 중 오류: {str(e)}")
            return {}
            
    def get_env(self, key: str, default: Any = None) -> Any:
        """환경 변수 조회"""
        return os.getenv(key, default) 