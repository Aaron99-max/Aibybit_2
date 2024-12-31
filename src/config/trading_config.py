import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class TradingConfig:
    """트레이딩 설정"""
    
    def __init__(self):
        self.symbol = 'BTCUSDT'
        self.max_daily_loss = 5.0  # 일일 최대 손실률 (%)
        
        # Bybit 관련 설정 추가
        self.bybit = type('BybitConfig', (), {
            'symbol': 'BTCUSDT',
            'max_daily_loss': 5.0,
            'base_url': 'https://api-testnet.bybit.com'  # 테스트넷 URL
        })

TRADING_CONFIG = {
    "default_leverage": None,  # GPT 분석 결과 사용
    "risk_reward_ratio": None,  # GPT 분석 결과의 TP/SL 비율 사용
    "tp_percentage": None,     # GPT 분석 결과의 TP 사용
    "sl_percentage": None,     # GPT 분석 결과의 SL 사용
    "max_position_size": None  # GPT 분석 결과의 position_size 사용
}
