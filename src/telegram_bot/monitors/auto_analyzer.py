import asyncio
import logging
import traceback
from typing import Dict, Optional
from datetime import datetime, timedelta
from ..utils.time_utils import TimeUtils
from ..formatters.order_formatter import OrderFormatter
from ..formatters.storage_formatter import StorageFormatter
from config.trading_config import trading_config
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from ..formatters.analysis_formatter import AnalysisFormatter

logger = logging.getLogger(__name__)

class AutoAnalyzer:
    def __init__(self, market_data_service, gpt_analyzer, order_service, telegram_bot=None):
        logger.info("AutoAnalyzer 초기화 시작")
        self.market_data_service = market_data_service
        self.gpt_analyzer = gpt_analyzer
        self.order_service = order_service
        self.telegram_bot = telegram_bot
        self.storage_formatter = StorageFormatter()
        self.order_formatter = OrderFormatter()
        self.analysis_formatter = AnalysisFormatter()  # 누락된 부분 추가
        self.is_running = False
        self.last_run_time = None
        self._current_analysis_task = None
        self._stop_event = asyncio.Event()

        # 스케줄러 설정 개선
        try:
            logger.info("스케줄러 설정 시작")
            self.scheduler = AsyncIOScheduler(timezone='Asia/Seoul')
            self.scheduler.add_job(
                self._scheduled_analysis,  # 래퍼 함수 사용
                'interval',  # cron 대신 interval 사용
                minutes=60,  # 60분마다
                next_run_time=self._get_next_hour(),  # 다음 정시에 시작
                id='hourly_analysis',
                replace_existing=True
            )
            logger.info("스케줄러 설정 완료")
        except Exception as e:
            logger.error(f"스케줄러 설정 중 오류 발생: {str(e)}")
            logger.error(traceback.format_exc())

    def _get_next_hour(self):
        """다음 정시 시간 계산"""
        now = datetime.now()
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        logger.info(f"다음 실행 예정 시간: {next_hour}")
        return next_hour

    async def _scheduled_analysis(self):
        """스케줄된 분석 실행 래퍼"""
        try:
            logger.info(f"스케줄된 분석 시작 - {datetime.now()}")
            await self.analyze_market(manual=False)
        except Exception as e:
            logger.error(f"스케줄된 분석 중 오류 발생: {str(e)}")
            logger.error(traceback.format_exc())

    async def start(self):
        """모니터링 시작"""
        logger.info("AutoAnalyzer 시작 요청됨")
        if self.is_running:
            logger.warning("이미 실행 중입니다")
            return

        try:
            self.is_running = True
            self.scheduler.start()
            next_run = self.scheduler.get_job('hourly_analysis').next_run_time
            logger.info(f"스케줄러 시작됨. 다음 실행 시간: {next_run}")
            
            # 시작 즉시 한 번 실행
            logger.info("초기 분석 실행 시작")
            await self._scheduled_analysis()
            logger.info("초기 분석 실행 완료")
        except Exception as e:
            logger.error(f"시작 중 오류 발생: {str(e)}")
            logger.error(traceback.format_exc())

    async def stop(self):
        """AutoAnalyzer 중지"""
        try:
            # 스케줄러 중지
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown(wait=False)
                logger.info("스케줄러가 중지되었습니다")
            
            # 실행 중인 분석 작업 취소
            if self._current_analysis_task:
                self._current_analysis_task.cancel()
                logger.info("실행 중인 분석 작업이 취소되었습니다")
            
            # 중지 이벤트 설정
            self._stop_event.set()
            logger.info("AutoAnalyzer가 중지되었습니다")
            
            return True
            
        except Exception as e:
            logger.error(f"AutoAnalyzer 중지 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def analyze_market(self, manual: bool = False):
        """시장 분석 실행"""
        try:
            if not self.is_running and not manual:
                logger.warning("자동 분석이 비활성화 상태입니다")
                return

            current_time = datetime.now()
            # 마지막 실행 시간 체크
            if not manual and self.last_run_time:
                time_diff = (current_time - self.last_run_time).total_seconds()
                if time_diff < 3600:  # 1시간(3600초) 미만이면 스킵
                    logger.info(f"마지막 실행 후 {time_diff}초 경과 - 스킵")
                    return

            logger.info("🔄' 1시간봉 분석 시작 " + ("(수동)" if manual else "(자동)") + " ...")
            
            # 분석 실행
            analysis_result = await self._run_analysis()
            if not analysis_result:
                return

            # 결과 저장
            self.storage_formatter.save_analysis('1h', analysis_result)
            
            # 분석 결과 알림 전송
            if self.telegram_bot:
                message = self.analysis_formatter.format_analysis(analysis_result)
                await self.telegram_bot.send_message_to_all(message, self.telegram_bot.MSG_TYPE_ANALYSIS)
            
            # 매매 신호 처리
            await self._handle_trading_signals(analysis_result['trading_signals'])
            
            self.last_run_time = current_time
            
        except Exception as e:
            logger.error(f"시장 분석 중 오류 발생: {str(e)}")
            logger.error(traceback.format_exc())

    async def _run_analysis(self):
        """분석 실행"""
        try:
            # OHLCV 데이터 조회 및 검증
            klines = await self.market_data_service.get_ohlcv('BTCUSDT', '1h')
            if not isinstance(klines, list) or not klines:
                await self._handle_error("시장 데이터 조회 실패")
                return None
            
            # 분석 실행
            analysis = await self.gpt_analyzer.analyze_market('1h', klines)
            if not analysis:
                await self._handle_error("분석 실패")
                return None

            return analysis

        except Exception as e:
            logger.error(f"분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            await self._handle_error("분석 중 오류가 발생했습니다")
            return None

    async def _handle_error(self, message: str):
        """에러 처리"""
        logger.error(message)
        if self.telegram_bot:
            await self.telegram_bot.send_message_to_all(f"❌ {message}", self.telegram_bot.MSG_TYPE_ANALYSIS)

    async def _handle_trading_signals(self, signals: Dict):
        """매매 신호 처리"""
        try:
            if not signals or 'position_suggestion' not in signals:
                return
                
            position_suggestion = signals['position_suggestion']
            logger.info(f"분석 결과 position_suggestion: {position_suggestion}")
            
            # HOLD가 아닐 때만 자동매매 실행
            if position_suggestion != 'HOLD':
                logger.info(f"매매 신호 감지: {position_suggestion}")
                
                # 매매 신호를 trade_manager로 전달
                trade_result = await self.order_service.execute_trade(signals)
                
                if trade_result:
                    order_info = {
                        'symbol': 'BTCUSDT',
                        'side': 'BUY' if position_suggestion == 'BUY' else 'SELL',
                        'leverage': signals['leverage'],
                        'price': signals['entry_price'],
                        'amount': signals['position_size'],
                        'status': 'NEW',
                        'stopLoss': signals['stop_loss'],
                        'takeProfit': signals['take_profit1'],
                        'is_btc_unit': False,
                        'position_size': signals['position_size']
                    }
                    message = self.order_formatter.format_order(order_info)
                    await self.telegram_bot.send_message_to_all(message, self.telegram_bot.MSG_TYPE_TRADE)
                else:
                    error_msg = self.order_formatter.format_order_failure(signals, "자동매매 실행 실패")
                    await self.telegram_bot.send_message_to_all(error_msg, self.telegram_bot.MSG_TYPE_TRADE)
            else:
                logger.info("관망 신호, 자동 매매 실행하지 않음")
            
        except Exception as e:
            logger.error(f"매매 신호 처리 중 오류: {str(e)}")
            logger.error(traceback.format_exc())