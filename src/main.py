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
from services import PositionService, OrderService
from ai.ai_trader import AITrader
import traceback
from dotenv import load_dotenv
from config.logging_config import setup_logging

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
if project_root not in sys.path:
    sys.path.insert(0, project_root)

if platform.system() == 'Windows':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    try:
        logger.info("=== 메인 프로그램 시작 ===")
        
        # 로깅 설정 초기화
        setup_logging()
        
        # 환경변수 로드
        logger.info("환경변수 및 설정 초기화 중...")
        load_dotenv()
        
        # Bybit 클라이언트 초기화
        logger.info("Bybit 테스트넷 클라이언트 초기화 중...")
        bybit_config = BybitConfig()  # 환경변수에서 자동으로 설정 로드
        bybit_client = BybitClient(config=bybit_config)
        
        # 마켓 데이터 서비스 초기화
        logger.info("마켓 데이터 서비스 중...")
        market_data_service = MarketDataService(bybit_client)
        await market_data_service.initialize()
        
        # Telegram Bot 초기화
        logger.info("Telegram Bot 초기화 중...")
        telegram_config = TelegramConfig()
        telegram_bot = TelegramBot(
            config=telegram_config,
            bybit_client=bybit_client
        )
        
        # 봇 실행
        await telegram_bot.run()
        
    except Exception as e:
        logger.error(f"실행 중 에러 발생: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        if 'bybit_client' in locals():
            await bybit_client.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"메인 루프 오류: {e}")
        os._exit(1)