import logging
import time
from typing import Dict, Optional
import traceback

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

    async def get_balance(self) -> Optional[Dict]:
        """잔고 조회"""
        try:
            balance = await self.bybit_client.get_balance()
            if balance:
                result = balance.get('list', [{}])[0]
                coin_info = result.get('coin', [{}])[0]
                
                return {
                    'timestamp': int(time.time() * 1000),
                    'currencies': {
                        'USDT': {
                            'total_equity': self.safe_float(coin_info.get('walletBalance')),
                            'used_margin': self.safe_float(coin_info.get('locked')),
                            'available_balance': self.safe_float(coin_info.get('availableToWithdraw'))
                        }
                    }
                }
            return None
        except Exception as e:
            logger.error(f"잔고 조회 중 오류: {str(e)}")
            return None 