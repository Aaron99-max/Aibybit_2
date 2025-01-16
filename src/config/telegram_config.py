import os
import logging
from typing import List

logger = logging.getLogger(__name__)

class TelegramConfig:
    def __init__(self):
        self.bot_token: str = os.getenv('TELEGRAM_BOT_TOKEN')
        
        # 관리자 채팅방 ID (명령어 처리용)
        admin_id = os.getenv('TELEGRAM_ADMIN_CHAT_ID', '0')
        self.admin_chat_id = int(admin_id) if admin_id else 0
        
        # 알림방 ID (알림 전용)
        alert_id = os.getenv('TELEGRAM_ALERT_CHAT_IDS', '0')
        self.alert_chat_ids = [int(id.strip()) for id in alert_id.split(',') if id.strip()]
        self.alert_chat_id = self.alert_chat_ids[0] if self.alert_chat_ids else 0
        
        if not all([self.bot_token, self.admin_chat_id, self.alert_chat_id]):
            raise ValueError("필수 텔레그램 설정이 없습니다.")
            
        logger.info("텔레그램 설정 완료:")
        logger.info(f"- 관리자방 ID: {self.admin_chat_id}")
        logger.info(f"- 알림방 IDs: {self.alert_chat_ids}")

    def is_admin(self, chat_id: int) -> bool:
        """관리자 권한 확인"""
        return chat_id == self.admin_chat_id

    def get_alert_chat_ids(self) -> List[int]:
        """알림을 보낼 모든 채팅방 ID 반환"""
        return self.alert_chat_ids
