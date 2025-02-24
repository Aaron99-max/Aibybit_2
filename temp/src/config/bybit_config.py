import os
import logging

logger = logging.getLogger(__name__)

class BybitConfig:
    def __init__(self):
        self.mode: str = os.getenv('BYBIT_MODE', 'testnet')
        
        # 테스트넷/메인넷에 따른 API 키 설정
        if self.mode == 'testnet':
            self.api_key: str = os.getenv('BYBIT_TESTNET_API_KEY')
            self.api_secret: str = os.getenv('BYBIT_TESTNET_SECRET_KEY')
            self.base_url: str = 'https://api-testnet.bybit.com'
            self.testnet = True
        else:
            self.api_key: str = os.getenv('BYBIT_API_KEY')
            self.api_secret: str = os.getenv('BYBIT_SECRET_KEY')
            self.base_url: str = 'https://api.bybit.com'
            self.testnet = False
            
        if not self.api_key or not self.api_secret:
            raise ValueError("Bybit API 키가 설정되지 않았습니다")

    @property
    def is_testnet(self) -> bool:
        """테스트넷 여부"""
        return self.testnet
