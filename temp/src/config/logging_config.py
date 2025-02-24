import logging
import logging.handlers
import os
from datetime import datetime

def setup_logging():
    # logs 디렉토리 생성
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    # 로그 포맷 설정
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 파일 핸들러 설정
    app_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_dir, 'app.log'),
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    app_handler.setFormatter(formatter)

    # 에러 로그 핸들러
    error_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_dir, 'error.log'),
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)

    # 거래 로그 핸들러
    trading_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_dir, 'trading.log'),
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    trading_handler.setFormatter(formatter)

    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(app_handler)
    root_logger.addHandler(error_handler)

    # 거래 관련 로거 설정
    trading_logger = logging.getLogger('trade')
    trading_logger.addHandler(trading_handler) 