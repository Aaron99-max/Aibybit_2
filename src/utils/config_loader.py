import os
import logging
from typing import Any, Dict, Optional
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class ConfigLoader:
    """설정 로드를 위한 유틸리티 클래스"""
    
    @staticmethod
    def load_env_file(env_path: Path) -> bool:
        """환경 변수 파일 로드"""
        try:
            if not env_path.exists():
                raise FileNotFoundError(f".env 파일을 찾을 수 없습니다: {env_path}")
            load_dotenv(env_path)
            return True
        except Exception as e:
            logger.error(f"환경 변수 로드 중 에러: {str(e)}")
            return False

    @staticmethod
    def get_env_value(key: str, default: Any = None) -> Optional[Any]:
        """환경 변수 값 조회"""
        try:
            value = os.getenv(key, default)
            if value is None:
                logger.warning(f"환경 변수를 찾을 수 없습니다: {key}")
            return value
        except Exception as e:
            logger.error(f"환경 변수 조회 중 에러: {str(e)}")
            return default

    @staticmethod
    def load_api_config(mode: str = 'testnet') -> Dict[str, str]:
        """API 설정 로드"""
        try:
            if mode == 'testnet':
                return {
                    'API_KEY': os.getenv('BYBIT_TESTNET_API_KEY'),
                    'API_SECRET': os.getenv('BYBIT_TESTNET_SECRET_KEY'),
                    'BASE_URL': 'https://api-testnet.bybit.com'
                }
            else:
                return {
                    'API_KEY': os.getenv('BYBIT_API_KEY'),
                    'API_SECRET': os.getenv('BYBIT_SECRET_KEY'),
                    'BASE_URL': 'https://api.bybit.com'
                }
        except Exception as e:
            logger.error(f"API 설정 로드 중 에러: {str(e)}")
            return {}
