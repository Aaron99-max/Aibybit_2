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
        self.max_daily_loss = 5.0  # 일일 최대 손실률 (%)
        self.max_leverage = 10     # 최대 레버리지
        self.max_position_size = 30  # 최대 포지션 크기 (%)
        
        # 자동매매 실행 조건
        self.auto_trading = {
            "confidence": {
                "min": 70,    # 75 -> 70으로 낮춤
                "high": 80    # 85 -> 80으로 낮춤
            },
            "trend_strength": {
                "min": 40,    # 기본 최소 추세 강도
                "levels": {
                    "confidence_85": 10,   # 신뢰도 85% 이상
                    "confidence_80": 15,   # 신뢰도 80~84%
                    "confidence_75": 20,   # 신뢰도 75~79%
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

# 전역 설정 인스턴스
trading_config = TradingConfig.get_instance()
