import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import os
from pathlib import Path
from typing import Optional
import sys

def setup_logger(
    name: str,
    log_file: str,
    level: int = logging.INFO,
    max_bytes: int = 1024 * 1024,  # 1MB
    backup_count: int = 5,
    format_string: Optional[str] = None
) -> logging.Logger:
    """로거 설정
    
    Args:
        name: 로거 이름
        log_file: 로그 파일명
        level: 로깅 레벨
        max_bytes: 최대 파일 크기
        backup_count: 백업 파일 수
        format_string: 커스텀 포맷 문자열
    """
    try:
        # 로그 디렉토리 생성
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        
        # 로거 설정
        logger = logging.getLogger(name)
        logger.setLevel(level)
        
        # 이미 핸들러가 있다면 제거
        if logger.handlers:
            logger.handlers.clear()
        
        # 기본 포맷 설정
        if format_string is None:
            format_string = (
                '%(asctime)s - %(name)s - %(levelname)s - '
                '%(filename)s:%(lineno)d - %(message)s'
            )
        
        formatter = logging.Formatter(format_string)
        
        # 파일 핸들러 설정 (일별 로테이션)
        file_handler = TimedRotatingFileHandler(
            log_dir / log_file,
            when='midnight',
            interval=1,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        
        # 콘솔 핸들러 설정
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        
        # 핸들러 추가
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger
        
    except Exception as e:
        print(f"로거 설정 중 에러 발생: {str(e)}")
        raise

def get_logger(name: str) -> logging.Logger:
    """기존 로거 반환 또는 새로운 로거 생성"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name, f'{name}.log')
    return logger 

logging.getLogger('exchange.bybit_client').setLevel(logging.DEBUG) 