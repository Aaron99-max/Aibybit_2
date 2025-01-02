import os
import logging
from typing import Optional
import json

logger = logging.getLogger(__name__)

class TelegramConfig:
    """텔레그램 봇 설정"""
    
    def __init__(self):
        self.bot_token: str = os.getenv('TELEGRAM_BOT_TOKEN')
        
        # 관리자 채팅방 ID (명령어 처리용)
        self.admin_chat_id = int(os.getenv('TELEGRAM_ADMIN_CHAT_ID'))
        
        # 알림을 받을 채팅방 ID 목록
        alert_chat_ids = os.getenv('TELEGRAM_ALERT_CHAT_IDS', '').split(',')
        self.alert_chat_ids = [int(id.strip()) for id in alert_chat_ids if id.strip()]
        
        # group_chat_id 제거 (단일 알람방 사용)
        self.group_chat_id = None
        
        if not self.bot_token or not self.admin_chat_id:
            raise ValueError("필수 텔레그램 설정이 없습니다.")
            
        logger.info("텔레그램 설정 완료:")
        logger.info(f"- 관리자 chat_id: {self.admin_chat_id}")
        logger.info(f"- 알림 chat_ids: {self.alert_chat_ids}")

def load_telegram_config():
    """텔레그램 설정 로드"""
    try:
        # 설정 로드
        config = {
            'admin_chat_id': int(os.getenv('TELEGRAM_ADMIN_CHAT_ID', '0')),
            'notification_chat_ids': [int(os.getenv('TELEGRAM_ADMIN_CHAT_ID', '0'))],  # 관리자 ID만 포함
        }
        
        # 로그는 한 번만 출력
        logger.info("텔레그램 설정 완료:")
        logger.info(f"- 관리자 chat_id: {config['admin_chat_id']}")
        logger.info(f"- 알림 chat_ids: {config['notification_chat_ids']}")
        
        return config
        
    except Exception as e:
        logger.error(f"텔레그램 설정 로드 중 오류: {str(e)}")
        return None
