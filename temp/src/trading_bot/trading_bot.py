import telegram
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram import Update
from telegram_bot.bot import TelegramBot  # 새로운 경로로 수정
import os
from dotenv import load_dotenv
from logger_config import setup_logger
from exchange.bybit_client import BybitClient
from indicators.technical import TechnicalIndicators
import pandas as pd
import asyncio
import queue
import threading
import time
from telegram.request import HTTPXRequest
import httpx  # httpx 모듈 추가
from gpt_client import call_gpt_api  # gpt_client.py에서 함수 import
import json
from datetime import datetime
from ai.ai_trader import AITrader
from ai.order_service import OrderService
from ai.position_service import PositionService

logger = setup_logger('trading', 'trading.log')

class TradingBot:
    def __init__(self, config):
        # 환경 변수 로딩 전 현재 작업 디렉토리 출력
        print(f"현재 작업 디렉토리: {os.getcwd()}")
        
        # .env 파일 존재 여부 확인
        env_path = os.path.join(os.getcwd(), '.env')
        print(f".env 파일 존재 여부: {os.path.exists(env_path)}")
        
        load_dotenv()
        self.token = config.get('token')
        
        # 환경 변수 로딩 확인
        print(f"환경 변수 TELEGRAM_BOT_TOKEN: {os.getenv('TELEGRAM_BOT_TOKEN')}")
        print(f"config에서 가져온 token: {self.token}")
        
        self.chat_id = config.get('chat_id')
        
        # config 변수를 정의
        self.config = {
            "token": self.token,
            "chat_id": self.chat_id
        }
        
        # 커스텀 request 객체 생성
        request = HTTPXRequest(
            connection_pool_size=8,
            connect_timeout=60,
            read_timeout=60,
            pool_timeout=60
        )
        
        # 환경 변수 로딩 확인을 위한 디버깅 출력 추가
        print(f"Telegram Bot Token: {self.token}")
        
        if not self.token:
            raise ValueError("Telegram Bot Token is missing in environment variables")
        
        request = telegram.utils.request.Request(con_pool_size=8)
        self.bot = telegram.Bot(token=self.token, request=request)
        self.bybit_client = None
        self.message_queue = queue.Queue()
        self.event_loop = None
        self.last_message_time = 0
        self.offset = 0  # 업데이트 오프셋 추가
        
        # 메시지 처리 스레드 시작
        self.message_thread = threading.Thread(target=self._process_messages)
        self.message_thread.daemon = True
        self.message_thread.start()
        
        self.telegram_bot = TelegramBot(self.config)  # TelegramBot 인스턴스 생성
        
        # OrderService 초기화 추가
        self.order_service = OrderService(self.bybit_client)
        self.position_service = PositionService(self.bybit_client, self.order_service)
        
        # AITrader 초기화 시 필요한 서비스들 전달
        self.ai_trader = AITrader(
            bybit_client=self.bybit_client,
            telegram_bot=self.telegram_bot,
            order_service=self.order_service
        )
        
    def _process_messages(self):
        """메시지 큐를 처리하는 스레드"""
        self.event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.event_loop)
        
        while True:
            try:
                message = self.message_queue.get()
                if message is None:  # 종료 신호
                    break
                
                # 메시지 간 최소 1초 간격 유지
                current_time = time.time()
                if current_time - self.last_message_time < 1:
                    time.sleep(1 - (current_time - self.last_message_time))
                
                self.event_loop.run_until_complete(self._send_message_async(message))
                self.last_message_time = time.time()
            except Exception as e:
                logger.error(f"메시지 처리 중 에러: {e}")
                time.sleep(1)

    async def _send_message_async(self, message):
        """비동기로 텔레그램 메시지 전송"""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='HTML'
            )
            await asyncio.sleep(0.1)
        except telegram.error.RetryAfter as e:
            logger.warning(f"Rate limit exceeded. Waiting {e.retry_after} seconds")
            await asyncio.sleep(e.retry_after)
            await self._send_message_async(message)  # 재시도
        except Exception as e:
            logger.error(f"메시지 전송 중 에러: {e}")

    def send_message(self, message):
        """메시지를 큐에 추가"""
        self.message_queue.put(message)

    async def initialize(self):
        """초기화"""
        self.bybit_client = BybitClient()
        await self.bybit_client.initialize()
        self.send_message("🤖 바이빗 트레이딩 봇이 시작되었습니.")

    async def run(self):
        """봇 실행"""
        await self.telegram_bot.run()  # TelegramBot의 run 메서드 호출

    async def handle_command(self, message):
        """명령어 처리"""
        await self.telegram_bot.handle_command(message)  # TelegramBot의 handle_command 호출

    async def stop(self):
        """봇 종료"""
        try:
            self.send_message("봇을 종료합니다...")
            self.message_queue.put(None)
            if self.bybit_client:
                await self.bybit_client.close()
        except Exception as e:
            logger.error(f"봇 종료 중 에러: {e}")

    async def send_status(self, message):
        """상태 정보 전송"""
        try:
            btc_data = await self.bybit_client.fetch_ohlcv('BTC/USDT', '1h', limit=100)
            btc_data = TechnicalIndicators.calculate_indicators(btc_data)
            btc_data = TechnicalIndicators.check_rsi_divergence(btc_data)
            
            latest = btc_data.iloc[-1]
            
            status_message = (
                "🔍 현재 시장 상태\n\n"
                f"💰 BTC 가격: ${latest['close']:,.2f}\n"
                f"📊 RSI: {latest['rsi']:.2f}\n"
                f"📈 MACD: {latest['macd']:.2f}\n"
                f"📉 VWAP: ${latest['vwap']:,.2f}\n"
            )
            
            if latest['bullish_divergence']:
                status_message += "\n🚀 불리시 다이버전스 감지!"
            if latest['bearish_divergence']:
                status_message += "\n⚠️ 베어리시 다이버전스 감지!"
                
            self.send_message(status_message)
            
        except Exception as e:
            self.send_message(f"상태 조회 중 에러 발생: {e}")

    async def send_balance(self, message):
        """잔고 정보 전송"""
        try:
            balance = await self.bybit_client.get_balance()
            if 'USDT' in balance['total']:
                self.send_message(f"💰 USDT 잔고: ${balance['total']['USDT']:,.2f}")
            else:
                self.send_message("USDT 잔고가 없습니다.")
        except Exception as e:
            self.send_message(f"잔고 조회 중 에러 발생: {e}")

    async def send_price(self, message):
        """가격 정보 전송"""
        try:
            btc_data = await self.bybit_client.fetch_ohlcv('BTC/USDT', '1h', limit=1)
            current_price = btc_data['close'].iloc[-1]
            self.send_message(f"💰 BTC 현재가: ${current_price:,.2f}")
        except Exception as e:
            self.send_message(f"가격 조회 중 에러 발생: {e}")

    async def send_position(self, message):
        """포지션 정보 전송"""
        try:
            # 선물 시장 포지션 정보 가져오기
            positions = await self.bybit_client.exchange.fetch_positions(['BTCUSDT'])  # 심볼 형식 변경
            
            if not positions or all(float(pos['contracts'] or 0) == 0 for pos in positions):
                self.send_message("현재 열린 포지션이 없습니다.")
                return
                
            for position in positions:
                if float(position.get('contracts', 0) or 0) > 0:
                    position_message = (
                        "📊 현재 포지션\n\n"
                        f"심볼: {position.get('symbol', 'N/A')}\n"
                        f"방향: {'롱' if position.get('side') == 'long' else '숏'}\n"
                        f"크기: {position.get('contracts', 'N/A')} 계약\n"
                        f"평균 진입가: ${float(position.get('entryPrice', 0) or 0):,.2f}\n"
                        f"현재가: ${float(position.get('markPrice', 0) or 0):,.2f}\n"
                        f"미실현 손익: ${float(position.get('unrealizedPnl', 0) or 0):,.2f}\n"
                        f"레버리지: {position.get('leverage', 'N/A')}x"
                    )
                    self.send_message(position_message)
            
        except Exception as e:
            logger.error(f"포지션 조회 중 에러: {str(e)}")
            self.send_message(f"포지션 조회  에러 발생: {str(e)}")

    async def get_market_data(self):
        """현재 시장 데이터 가져오기"""
        try:
            ohlcv = await self.bybit_client.fetch_ohlcv('BTC/USDT', '1h', limit=100)
            df = TechnicalIndicators.calculate_indicators(ohlcv)

            # RSI nan일 경우 기본값 설정
            rsi_value = df['rsi'].iloc[-1] if not df['rsi'].isnull().all() else 0

            # 시장 요약 및 신호 결정 로직 추가
            market_summary = "시장 상태 요약"
            signal = "long" if rsi_value < 30 else "short" if rsi_value > 70 else "hold"
            entry_price = df['close'].iloc[-1]
            stop_loss = entry_price * 0.98  # 예시: 2% 손절
            take_profit = entry_price * 1.02  # 예시: 2% 익절
            risk_level = 3  # 예시: 중간 위험
            additional_notes = "추 노트 내용"

            # 필요한 데이터 추출
            market_data = {
                'price': entry_price,
                'rsi': rsi_value,
                'macd': df['macd'].iloc[-1],
                'market_summary': market_summary,
                'signal': signal,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'risk_level': risk_level,
                'additional_notes': additional_notes,
            }
            return market_data
        except Exception as e:
            logger.error(f"시장 데이터 가져오기 중 에러: {e}")
            return None

    async def execute_trade(self):
        """자동매매 실행"""
        try:
            # 최종 분석 결과 확인
            with open('analysis_data/analysis_final.json', 'r', encoding='utf-8') as f:
                final_analysis = json.load(f)
            
            # AITrader를 통한 매매 실행
            success = await self.ai_trader.execute_trade(final_analysis)
            
            if success:
                logger.info("자동매매 실행 완료")
                return True
            else:
                logger.error("자동매매 실행 실패")
                return False
            
        except Exception as e:
            logger.error(f"자동매매 실행 중 오류: {str(e)}")
            return False

    def _validate_auto_trading_conditions(self, analysis: Dict, rules: Dict) -> bool:
        """자동매매 조건 검증"""
        try:
            # 자동매매 활성화 여부 확인
            auto_trading = analysis.get('trading_strategy', {}).get('auto_trading', {})
            if not auto_trading.get('enabled'):
                logger.info("자동매매가 비활성화되어 있음")
                return False
            
            # 최소 신뢰도 확인
            confidence = analysis['market_summary']['confidence']
            if confidence < rules['min_confidence']:
                logger.info(f"신뢰도 부족: {confidence} < {rules['min_confidence']}")
                return False
            
            # 추세 강도 확인
            trend_strength = analysis['market_conditions']['trend_strength']
            if trend_strength < rules['min_trend_strength']:
                logger.info(f"추세 강도 부족: {trend_strength} < {rules['min_trend_strength']}")
                return False
            
            # 일일 거래 ���수 확인
            if not self._check_daily_trade_limit(rules['max_daily_trades']):
                logger.info("일일 거래 한도 초과")
                return False
            
            # 쿨다운 시간 확인
            if not self._check_trade_cooldown(rules['cooldown_minutes']):
                logger.info("거래 쿨다운 시간")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"자동매매 조건 검증 중 오류: {str(e)}")
            return False

    async def _notify_trade_execution(self, order: Dict, analysis: Dict):
        """거래 실행 알림"""
        try:
            message = f"""
🤖 자동매매 실행

📊 거래 정보:
• 방향: {order['side']}
• 가격: {order['price']}
• 수량: {order['amount']}
• 레버리지: {order.get('leverage', '미설정')}x

📈 분석 근거:
• 시장 단계: {analysis['market_summary']['market_phase']}
• 신뢰도: {analysis['market_summary']['confidence']}%
• 추세 강도: {analysis['market_conditions']['trend_strength']}%

⚠️ 리스크 관리:
• 손절가: {order.get('stopLoss', '미설정')}
• 목표가: {order.get('takeProfit', '미설정')}
"""
            await self.send_message(message)
            
        except Exception as e:
            logger.error(f"거래 실행 알림 중 오류: {str(e)}")

    def _check_trade_limits(self) -> bool:
        """거래 제한 체크"""
        try:
            with open('config/gpt_config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            trade_limits = config['trading_rules']['trade_limits']
            
            current_time = time.time()
            current_date = datetime.now().date()
            
            # 일일 거래 횟수 체크
            if self.last_trade_date != current_date:
                self.daily_trades = 0
                self.last_trade_date = current_date
            
            if self.daily_trades >= trade_limits['max_daily_trades']:
                logger.info("일일 최대 거래 횟�� 초과")
                return False
            
            # 4시간 간격 체크
            min_interval = trade_limits['auto_trade']['min_trades_interval'] * 60  # 분을 초로 변환
            if current_time - self.last_trade_time < min_interval:
                logger.info(f"최소 거래 간격 미충족: {min_interval/60}분 대기 필요")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"거래 제한 체크 중 오류: {str(e)}")
            return False

if __name__ == "__main__":
    config = {
        "token": os.getenv('TELEGRAM_BOT_TOKEN'),
        "chat_id": os.getenv('TELEGRAM_CHAT_ID')
    }
    trading_bot = TradingBot(config)  # TradingBot 인스턴스 생성
    asyncio.run(trading_bot.run())  # TradingBot의 run 메서드 호출