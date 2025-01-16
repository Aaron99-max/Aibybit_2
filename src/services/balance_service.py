import logging
import time
from typing import Dict, Optional
import traceback
from telegram_bot.utils.decorators import error_handler

logger = logging.getLogger(__name__)

class BalanceService:
    def __init__(self, bybit_client):
        self.bybit_client = bybit_client

    def safe_float(self, value, default=0.0):
        """안전한 float 변환"""
        try:
            if value is None or value == 'None' or value == '':
                return default
            return float(value)
        except (ValueError, TypeError):
            return default

    @error_handler
    async def get_balance(self) -> Optional[Dict]:
        """잔고 조회"""
        balance = await self.bybit_client.get_balance()
        if not balance:
            return None
            
        result = balance.get('list', [{}])[0]
        coin_info = result.get('coin', [{}])[0]
        
        # API 응답 로깅
        logger.info(f"Balance API Response: {balance}")
        logger.info(f"Coin Info: {coin_info}")
        
        # 추가 정보 조회
        wallet_balance = self.safe_float(coin_info.get('walletBalance'))
        used_margin = self.safe_float(coin_info.get('locked'))
        available_balance = wallet_balance - used_margin  # 사용 가능한 잔고 계산
        
        return {
            'timestamp': int(time.time() * 1000),
            'currencies': {
                'USDT': {
                    'total_equity': wallet_balance,
                    'used_margin': used_margin,
                    'available_balance': available_balance
                }
            }
        } 