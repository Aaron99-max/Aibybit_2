import time
import logging
import os
from datetime import datetime
from pytz import timezone

logger = logging.getLogger(__name__)

class TimeUtils:
    def __init__(self):
        self.kst_tz = timezone('Asia/Seoul')

    @staticmethod
    def get_kst_time(timestamp=None):
        """KST 시간 반환"""
        if timestamp is None:
            timestamp = int(time.time())
        return time.localtime(timestamp)

    @staticmethod
    def format_kst_time(timestamp=None):
        """KST 시간 문자열 포맷팅"""
        kst_time = TimeUtils.get_kst_time(timestamp)
        return time.strftime('%Y-%m-%d %H:%M:%S KST', kst_time)

    @staticmethod
    def format_timestamp(timestamp):
        """타임스탬프를 KST 시간 문자열로 포맷팅"""
        if isinstance(timestamp, str):
            try:
                # ISO 형식 문자열인 경우
                if 'T' in timestamp:
                    dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f")
                    return dt.strftime('%Y-%m-%d %H:%M:%S KST')
                # 숫자 문자열인 경우
                timestamp = int(timestamp)
            except ValueError:
                return timestamp  # 파싱 실패시 원본 반환

        # 타임스탬프가 너무 큰 경우 (초 대신 밀리초로 가정)
        if timestamp > 32503680000:  # 3000년 이후의 타임스탬프
            timestamp = timestamp / 1000
            
        return TimeUtils.format_kst_time(timestamp)

    def format_file_time(self, filepath: str) -> str:
        """파일의 수정 시간을 KST로 포맷팅"""
        try:
            mtime = os.path.getmtime(filepath)
            dt = datetime.fromtimestamp(mtime)
            kst = dt.astimezone(self.kst_tz)
            return kst.strftime("%Y-%m-%d %H:%M:%S KST")
        except Exception as e:
            logger.error(f"파일 시간 포맷팅 오류: {e}")
            return self.format_kst_time()  # 실패시 현재 시간 반환