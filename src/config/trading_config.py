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
            "max_difference": 2  # 허용 가능한 최대 레버리지 차이
        }
        
        # 자동매매 실행 조건
        self.auto_trading = {
            "confidence": {
                "min": 70,    # 75 -> 70으로 낮춤
                "high": 80    # 85 -> 80으로 낮춤
            },
            "trend_strength": {
                "min": 10,    # 기본 최소 추세 강도
                "levels": {
                    "confidence_80": 10,   # 신뢰도 85% 이상
                    "confidence_75": 15,   # 신뢰도 80~84%
                    "confidence_70": 20,   # 신뢰도 75~79%
                    "default": 25         # 신뢰도 70~74%
                }
            }
        }
        
        # Bybit 관련 설정
        self.bybit = type('BybitConfig', (), {
            'symbol': 'BTCUSDT',
            'max_daily_loss': 5.0,
            'base_url': 'https://api-testnet.bybit.com'  # 테스트넷 URL
        })
        
        # GPT 분석 결과 관련 설정
        self.gpt_settings = {
            "default_leverage": None,     # GPT 분석 결과 사용
            "risk_reward_ratio": None,    # GPT 분석 결과의 TP/SL 비율 사용
            "tp_percentage": None,        # GPT 분석 결과의 TP 사용
            "sl_percentage": None,        # GPT 분석 결과의 SL 사용
            "max_position_size": None     # GPT 분석 결과의 position_size 사용
        }

    @classmethod
    def get_instance(cls):
        """싱글톤 인스턴스 반환"""
        if not hasattr(cls, '_instance'):
            cls._instance = cls()
        return cls._instance

    # 포지션 관련 설정
    MIN_POSITION_SIZE = 0.001  # 최소 주문 수량 (BTC)
    DECIMAL_PLACES = 3         # 수량 소수점 자리수
    
    # 손익 설정
    LONG_SL_PERCENT = 1.0     # 롱 포지션 손절 퍼센트
    LONG_TP_PERCENT = 2.0     # 롱 포지션 익절 퍼센트
    SHORT_SL_PERCENT = 1.0    # 숏 포지션 손절 퍼센트
    SHORT_TP_PERCENT = 2.0    # 숏 포지션 익절 퍼센트

    # 추가 설정
    DEFAULT_LEVERAGE = 1  # 기본 레버리지
    TIMESTAMP_MULTIPLIER = 1000  # milliseconds 변환용

# 전역 설정 인스턴스
trading_config = TradingConfig.get_instance()
