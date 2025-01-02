import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class BalanceService:
    def __init__(self, bybit_client):
        self.bybit_client = bybit_client

    async def get_balance(self) -> Optional[Dict]:
        """잔고 조회"""
        try:
            params = {
                'accountType': 'UNIFIED',
                'recvWindow': 20000
            }
            
            balance = await self.bybit_client.exchange.fetch_balance(params=params)
            
            if balance:
                logger.debug(f"Raw balance data: {balance}")
                result = {
                    'timestamp': int(time.time() * 1000),
                    'currencies': {}
                }
                
                # USDT 잔고
                if 'USDT' in balance:
                    usdt = balance['USDT']
                    result['currencies']['USDT'] = {
                        'total_equity': float(usdt.get('total', 0)),
                        'used_margin': float(usdt.get('used', 0)),
                        'available_balance': float(usdt.get('free', 0))
                    }
                
                return result
                
            logger.error("잔고 정보를 찾을 수 없습니다")
            return None
            
        except Exception as e:
            logger.error(f"잔고 조회 실패: {str(e)}")
            return None 