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
                "min": 60,    # 최소 신뢰도
                "high": 80    # 높은 신뢰도 기준
            },
            "trend_strength": {
                "min": 10,    # 기본 최소 추세 강도
                "levels": {
                    "confidence_80": 10,   # 신뢰도 80% 이상
                    "confidence_70": 15,   # 신뢰도 70~79%
                    "confidence_60": 20,   # 신뢰도 60~69%
                    "default": 25         # 그외
                }
            }
        }
        
        # Bybit 관련 설정
        self.bybit = type('BybitConfig', (), {
            'symbol': 'BTCUSDT',
            'max_daily_loss': 5.0,
            'base_url': 'https://api-testnet.bybit.com'  # 테스트넷 URL
        })
        
        # GPT 분석 결과 활용 설정
        self.gpt_settings = {
            "use_gpt_analysis": True,  # GPT 분석 사용 여부
            "risk_levels": {
                "conservative": {
                    "max_leverage": 5,
                    "position_size_range": (5, 20),
                    "min_risk_reward": 2.0
                },
                "moderate": {
                    "max_leverage": 10,
                    "position_size_range": (10, 40),
                    "min_risk_reward": 1.5
                },
                "aggressive": {
                    "max_leverage": 20,
                    "position_size_range": (20, 60),
                    "min_risk_reward": 1.0
                }
            },
            "validation": {
                "min_tp_distance": 0.1,  # 최소 TP 거리 (%)
                "min_sl_distance": 0.1,  # 최소 SL 거리 (%)
                "max_position_size": 100  # 최대 포지션 크기 (%)
            }
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
    
    # 기본 레버리지 설정
    DEFAULT_LEVERAGE = 1
    
    # 추가 설정
    TIMESTAMP_MULTIPLIER = 1000  # milliseconds 변환용

# 전역 설정 인스턴스
trading_config = TradingConfig.get_instance()
