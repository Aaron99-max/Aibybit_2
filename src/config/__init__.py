from typing import Optional
import logging
import os
from dotenv import load_dotenv
from pathlib import Path
from .base_config import BaseConfig

logger = logging.getLogger(__name__)

# 환경변수 로드
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    logger.warning(f".env 파일을 찾을 수 없습니다: {env_path}")

class Config(BaseConfig):
    """통합 설정 클래스"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        try:
            super().__init__()
            
            # 설정 인스턴스들을 지연 초기화를 위해 None으로 설정
            self._bybit = None
            self._telegram = None
            self._trading = None
            
            # 기본 디렉토리 설정
            self.root_dir = Path(__file__).parent.parent
            self.config_dir = self.root_dir / 'config' / 'data'
            self.data_dir = self.root_dir / 'data'
            
            # 디렉토리 생성
            self.config_dir.mkdir(parents=True, exist_ok=True)
            (self.data_dir / 'trades').mkdir(parents=True, exist_ok=True)
            (self.data_dir / 'analysis').mkdir(parents=True, exist_ok=True)
            (self.data_dir / 'cache').mkdir(parents=True, exist_ok=True)
            
            # 기본 설정값 로드
            self._load_configs()
            
            self._initialized = True
            logger.info("Config 초기화 완료")
            
        except Exception as e:
            logger.error(f"Config 초기화 중 오류 발생: {str(e)}")
            raise
    
    def _load_configs(self):
        """각 설정 모듈 import 및 초기화"""
        try:
            from .bybit_config import BybitConfig
            from .telegram_config import TelegramConfig
            from .trading_config import TradingConfig
            
            # 설정 클래스들 미리 import
            self.BybitConfig = BybitConfig
            self.TelegramConfig = TelegramConfig
            self.TradingConfig = TradingConfig
            
        except ImportError as e:
            logger.error(f"설정 모듈 import 중 오류: {str(e)}")
            raise
    
    @property
    def bybit(self):
        if self._bybit is None:
            self._bybit = self.BybitConfig()
        return self._bybit
    
    @property
    def telegram(self):
        if self._telegram is None:
            self._telegram = self.TelegramConfig()
        return self._telegram
    
    @property
    def trading(self):
        if self._trading is None:
            self._trading = self.TradingConfig()
        return self._trading

# 전역 설정 인스턴스
config = Config()

# 하위 호환성을 위한 별칭들
bybit_config = config.bybit
telegram_config = config.telegram
trading_config = config.trading

__all__ = ['config', 'bybit_config', 'telegram_config', 'trading_config']
