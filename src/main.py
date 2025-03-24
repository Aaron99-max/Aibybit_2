import os
import sys
import asyncio
import logging
from telegram import Bot
from telegram_bot.bot import TelegramBot
from exchange.bybit_client import BybitClient
from config.bybit_config import BybitConfig
from indicators.technical import TechnicalIndicators
from ai.gpt_analyzer import GPTAnalyzer
import platform
import time
from config import config
from config.telegram_config import TelegramConfig
from services.market_data_service import MarketDataService
from trade.trade_manager import TradeManager
from services import PositionService, OrderService, BalanceService
from ai.ai_trader import AITrader
import traceback
from dotenv import load_dotenv
from config.logging_config import setup_logging
from config import Config
import signal

# 환경 변수 로드
load_dotenv()  

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# httpx 로거 레벨 설정
logging.getLogger('httpx').setLevel(logging.WARNING)

logger = logging.getLogger('main')

# 프로젝트 루트 디렉토리를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

if project_root not in sys.path:
    sys.path.insert(0, project_root)

if platform.system() == 'Windows':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    try:
        logger.info("=== 메인 프로그램 시작 ===")
        
        # Config 초기화
        Config.initialize()
        logger.info("Config 초기화됨")
        
        logger.info("환경변수 및 설정 초기화 중...")
        telegram_config = TelegramConfig()
        
        # Bybit 클라이언트 초기화
        logger.info("Bybit 테스트넷 클라이언트 초기화 중...")
        bybit_client = BybitClient()
        
        # 웹소켓 연결
        logger.info("웹소켓 연결 시작...")
        await bybit_client.ws_client.start()
        
        # 서비스 초기화
        market_data_service = MarketDataService(bybit_client)
        position_service = PositionService(bybit_client)
        balance_service = BalanceService(bybit_client)
        order_service = OrderService(
            bybit_client=bybit_client,
            position_service=position_service,
            balance_service=balance_service
        )
        
        # 봇 초기화
        telegram_bot = TelegramBot(
            config=telegram_config,
            bybit_client=bybit_client,
            market_data_service=market_data_service
        )
        
        # OrderService에 telegram_bot 설정
        order_service.telegram_bot = telegram_bot
        
        # 종료 시그널 핸들러 설정
        def signal_handler():
            logger.info("종료 시그널 감지됨")
            asyncio.create_task(telegram_bot.stop())
        
        # Ctrl+C 핸들러 설정
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)
        
        # 봇 실행
        try:
            await telegram_bot.run()
        except asyncio.CancelledError:
            logger.info("봇 실행이 취소되었습니다")
        finally:
            # 봇 종료
            await telegram_bot.stop()
            # 웹소켓 종료
            await bybit_client.close()
            # 프로세스 종료
            os._exit(0)
        
    except Exception as e:
        logger.error(f"실행 중 에러 발생: {str(e)}")
        logger.error(traceback.format_exc())
        os._exit(1)

if __name__ == "__main__":
    # Windows에서 asyncio 이벤트 루프 정책 설정
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 메인 실행
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("프로그램이 Ctrl+C로 종료되었습니다")
    except Exception as e:
        logger.error(f"메인 루프 오류: {e}")
        os._exit(1)