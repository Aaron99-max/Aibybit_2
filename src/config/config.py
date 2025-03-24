from .base_config import BaseConfig

class Config(BaseConfig):
    """전역 설정 클래스"""
    _instance = None
    
    @classmethod
    def initialize(cls):
        """설정 초기화"""
        if not cls._instance:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        super().__init__()
        # 여기에 필요한 초기화 로직 추가
