import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class TradingConfig:
    """트레이딩 설정"""
    
    def __init__(self):
        # 기본 설정
        self.symbol = 'BTCUSDT'
        self.max_daily_loss = 5.0
        self.max_leverage = 10
        self.max_position_size = 30
        
        # 레버리지 차이 허용 범위만 설정
        self.leverage_settings = {
            "max_difference": 2,  # 허용 가능한 최대 레버리지 차이
            "default": 3,        # 기본 레버리지
            "min": 1,           # 최소 레버리지
            "max": 10          # 최대 레버리지
        }
        
        # 포지션 크기 설정
        self.position_settings = {
            "default": 10,     # 기본 포지션 크기 (%)
            "min": 5,         # 최소 포지션 크기 (%)
            "max": 30         # 최대 포지션 크기 (%)
        }
        
        # 자동매매 설정
        self.auto_trading = {
            "enabled": True,  # 전체 자동매매 on/off
            "follow_gpt": True  # GPT 신호 그대로 따를지
        }
        
        # 자동매매 신뢰도 기준
        self.min_confidence = 60  # 60% 이상일 때만 자동매매 활성화
        
        # Bybit 관련 설정
        self.bybit = type('BybitConfig', (), {
            'symbol': 'BTCUSDT',
            'max_daily_loss': 5.0,
            'base_url': 'https://api-testnet.bybit.com'  # 테스트넷 URL
        })

    @classmethod
    def get_instance(cls):
        """싱글톤 인스턴스 반환"""
        if not hasattr(cls, '_instance'):
            cls._instance = cls()
        return cls._instance

    # 포지션 관련 설정
    MIN_POSITION_SIZE = 0.001  # 최소 주문 수량 (BTC)
    DECIMAL_PLACES = 3         # 수량 소수점 자리수
    
    # 기본 레버리지 설정
    DEFAULT_LEVERAGE = 1
    
    # 추가 설정
    TIMESTAMP_MULTIPLIER = 1000  # milliseconds 변환용

# 전역 설정 인스턴스
trading_config = TradingConfig.get_instance()
