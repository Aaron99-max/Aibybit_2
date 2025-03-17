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
        """잔고 조회 - CCXT 사용"""
        try:
            # CCXT를 통한 잔고 조회
            balance = await self.bybit_client.exchange.fetch_balance({
                'type': 'unified',
                'accountType': 'UNIFIED'
            })
            
            if not balance:
                logger.error("잔고 조회 실패: 응답 없음")
                return None

            # USDT 잔고 정보 추출
            usdt = balance.get('USDT', {})
            
            # 응답 포맷팅
            return {
                'timestamp': int(time.time() * 1000),
                'currencies': {
                    'USDT': {
                        'total_equity': self.safe_float(usdt.get('total')),
                        'used_margin': self.safe_float(usdt.get('used')),
                        'available_balance': self.safe_float(usdt.get('free'))
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"잔고 조회 중 오류 발생: {str(e)}")
            logger.error(traceback.format_exc())
            return None