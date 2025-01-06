import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import os
from pathlib import Path
from typing import Optional
import sys

def setup_logger(name, log_file, level=logging.INFO):
    # 로그 디렉토리 생성
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    # 포맷터 설정
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 메인 로그 파일 설정 (app.log)
    main_handler = None
    if name == 'main' or 'app' in name:
        main_log = log_dir / 'app.log'
        main_handler = TimedRotatingFileHandler(
            main_log,
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        main_handler.setFormatter(formatter)
        main_handler.suffix = "%Y-%m-%d"
    
    # 개별 모듈 로그 파일 설정
    module_handler = TimedRotatingFileHandler(
        log_dir / log_file,
        when='midnight',
        interval=1,
        backupCount=5,
        encoding='utf-8'
    )
    module_handler.setFormatter(formatter)
    
    # 로거 설정
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 기존 핸들러 제거
    if logger.handlers:
        logger.handlers.clear()
    
    # 핸들러 추가
    logger.addHandler(module_handler)
    if main_handler:
        logger.addHandler(main_handler)
    
    # 분석 스킵 관련 로그는 필터링
    if 'analysis' in name:
        skip_filter = SkipAnalysisFilter()
        module_handler.addFilter(skip_filter)
        if main_handler:
            main_handler.addFilter(skip_filter)
    
    # 로거가 상위 로거로 전파되지 않도록 설정
    logger.propagate = False
    
    return logger

class SkipAnalysisFilter(logging.Filter):
    def filter(self, record):
        skip_messages = [
            "skipping analysis",
            "분석 스킵",
            "체크 - 현재시간",
            "실행 여부: False",
            "4시간봉 체크"
        ]
        return not any(msg.lower() in record.msg.lower() for msg in skip_messages)

def get_logger(name: str) -> logging.Logger:
    """기존 로거 반환 또는 새로운 로거 생성"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name, f'{name}.log')
    return logger

# 전역 로그 레벨 설정
logging.getLogger('exchange.bybit_client').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING) 