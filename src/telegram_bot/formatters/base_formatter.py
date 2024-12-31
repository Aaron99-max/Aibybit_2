from abc import ABC, abstractmethod
from typing import Dict, Union, Any
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

class BaseFormatter(ABC):
    """메시지 포맷팅을 위한 기본 인터페이스"""

    # 기본 이모지
    BASE_EMOJIS = {
        'error': '❌',
        'success': '✅',
        'warning': '⚠️',
        'info': 'ℹ️'
    }

    # 기본 메시지 템플릿
    BASE_TEMPLATES = {
        'error_format': "{emoji} 오류: {message}",
        'success_format': "{emoji} 성공: {message}",
        'warning_format': "{emoji} 경고: {message}",
        'info_format': "{emoji} 안내: {message}"
    }

    def __init__(self):
        """초기화 메서드"""
        self.translations = {}

    def format_number(self, number: Union[str, float, int, None], decimals: int = 2) -> str:
        """숫자 포맷팅

        Args:
            number: 포맷팅할 숫자
            decimals (int): 소수점 자리수

        Returns:
            str: 포맷팅된 숫자 문자열
        """
        try:
            if number is None:
                return '-'
            if isinstance(number, str):
                number = number.replace(',', '').replace('$', '')
            number_decimal = Decimal(str(number))
            format_str = f"{{:,.{decimals}f}}"
            return format_str.format(float(number_decimal))
        except (ValueError, TypeError, decimal.InvalidOperation) as e:
            logger.error(f"숫자 포맷팅 실패: {number}, 오류: {str(e)}")
            return '-'

    def format_error(self, message: str) -> str:
        """에러 메시지 포맷팅

        Args:
            message (str): 에러 메시지

        Returns:
            str: 포맷팅된 에러 메시지
        """
        return self.BASE_TEMPLATES['error_format'].format(
            emoji=self.BASE_EMOJIS['error'],
            message=message
        )

    def format_success(self, message: str) -> str:
        """성공 메시지 포맷팅

        Args:
            message (str): 성공 메시지

        Returns:
            str: 포맷팅된 성공 메시지
        """
        return self.BASE_TEMPLATES['success_format'].format(
            emoji=self.BASE_EMOJIS['success'],
            message=message
        )

    def format_warning(self, message: str) -> str:
        """경고 메시지 포맷팅

        Args:
            message (str): 경고 메시지

        Returns:
            str: 포맷팅된 경고 메시지
        """
        return self.BASE_TEMPLATES['warning_format'].format(
            emoji=self.BASE_EMOJIS['warning'],
            message=message
        )

    def format_info(self, message: str) -> str:
        """정보 메시지 포맷팅

        Args:
            message (str): 정보 메시지

        Returns:
            str: 포맷팅된 정보 메시지
        """
        return self.BASE_TEMPLATES['info_format'].format(
            emoji=self.BASE_EMOJIS['info'],
            message=message
        )

    def validate_data(self, data: Any, required_keys: list = None, numeric_keys: list = None) -> bool:
        """데이터 유효성 검사

        Args:
            data: 검증할 데이터
            required_keys (list, optional): 필수 키 목록
            numeric_keys (list, optional): 숫자여야 하는 키 목록

        Returns:
            bool: 유효성 검사 통과 여부
        """
        try:
            if not isinstance(data, dict):
                logger.error("데이터가 딕셔너리가 아님")
                return False

            if required_keys:
                if not all(key in data for key in required_keys):
                    logger.error(f"필수 키 누락: {required_keys}")
                    return False

            if numeric_keys:
                for key in numeric_keys:
                    if key in data:
                        try:
                            float(data[key])
                        except (ValueError, TypeError):
                            logger.error(f"{key}가 숫자가 아님")
                            return False

            return True
        except Exception as e:
            logger.error(f"데이터 검증 중 오류: {str(e)}")
            return False

    def translate(self, text: str) -> str:
        """영어 텍스트를 한글로 변환

        Args:
            text (str): 변환할 텍스트

        Returns:
            str: 변환된 텍스트
        """
        if not text or text == '-':
            return '-'
        return self.translations.get(text.upper(), text)

    @abstractmethod
    def format_balance(self, balance: Dict) -> str:
        """잔고 정보 포맷팅

        Args:
            balance (Dict): 잔고 데이터

        Returns:
            str: 포맷팅된 잔고 정보
        """
        pass

    @abstractmethod
    def format_position(self, position: Dict) -> str:
        """포지션 정보 포맷팅

        Args:
            position (Dict): 포지션 데이터

        Returns:
            str: 포맷팅된 포지션 정보
        """
        pass

    @abstractmethod
    def format_status(self, status: Dict[str, Union[bool, str]]) -> str:
        """상태 정보 포맷팅

        Args:
            status (Dict[str, Union[bool, str]]): 상태 데이터

        Returns:
            str: 포맷팅된 상태 정보
        """
        pass
