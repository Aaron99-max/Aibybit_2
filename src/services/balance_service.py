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
        # API 호출
        response = await self.bybit_client.get_balance()
        
        # 응답 검증
        if not response or response.get('retCode') != 0:
            logger.error(f"잔고 조회 실패: {response}")
            return None
            
        # 데이터 추출
        wallet_info = response.get('result', {}).get('list', [{}])[0]
        
        # 로깅
        logger.debug(f"지갑 정보: {wallet_info}")
        
        # 데이터 가공
        wallet_balance = self.safe_float(wallet_info.get('totalWalletBalance'))
        used_margin = self.safe_float(wallet_info.get('totalInitialMargin'))
        available_balance = self.safe_float(wallet_info.get('totalAvailableBalance'))
        
        # 응답 포맷팅
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