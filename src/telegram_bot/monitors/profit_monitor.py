import logging
import asyncio
import time
from typing import Dict
from telegram_bot.utils.time_utils import TimeUtils
import traceback

logger = logging.getLogger(__name__)

class ProfitMonitor:
    def __init__(self, bot):
        self.bot = bot
        self.time_utils = TimeUtils()
        self.scheduler = None
        self._is_running = False
        self.monitor_task = None

    def is_running(self):
        """실행 상태 확인"""
        return self._is_running

    async def start(self):
        """수익률 모니터링 시작"""
        if self._is_running:
            logger.info("이미 수익률 모니터링이 실행 중입니다")
            return False

        self._is_running = True
        self.monitor_task = asyncio.create_task(self.monitor_profit())
        logger.info("수익률 모니터링 시작됨")
        return True

    async def stop(self):
        """수익률 모니터링 중지"""
        self._is_running = False
        if self.monitor_task:
            self.monitor_task.cancel()
            self.monitor_task = None
        logger.info("수익률 모니터링 중지됨")

    async def monitor_profit(self):
        """실시간 수익률 모니터링"""
        while self._is_running:
            try:
                positions = await self.bot.bybit_client.fetch_positions('BTCUSDT')
                if positions:
                    for position in positions:
                        unrealized_pnl = float(position.get('unrealizedPnl', 0))
                        percentage = float(position.get('percentage', 0))
                        entry_price = float(position.get('entryPrice', 0))
                        current_size = float(position.get('size', 0))
                        leverage = float(position.get('leverage', 0))
                        
                        # 수익률 알림 기준
                        if percentage <= -1.5:  # -1.5% 손실
                            await self.bot.send_message(
                                f"⚠️ 손실 경고\n"
                                f"수익률: {percentage:.2f}%\n"
                                f"미실현 손익: ${unrealized_pnl:.2f}\n"
                                f"레버리지: {leverage}x\n"
                                f"포지션 크기: {current_size:.4f} BTC"
                            )
                        elif percentage >= 2.0:  # 2% 이상 수익
                            await self.bot.send_message(
                                f"✅ 수익률 달성\n"
                                f"수익률: {percentage:.2f}%\n"
                                f"미실현 손익: ${unrealized_pnl:.2f}\n"
                                f"레버리지: {leverage}x\n"
                                f"포지션 크기: {current_size:.4f} BTC"
                            )
                
            except Exception as e:
                logger.error(f"수익률 모니터링 중 오류: {str(e)}")
                logger.debug(traceback.format_exc())
                # 에러가 발생해도 계속 실행
            
            await asyncio.sleep(60)  # 1분마다 체크