from .base_formatter import BaseFormatter
from typing import Dict
import logging

logger = logging.getLogger(__name__)

class StatsFormatter(BaseFormatter):
    def format_stats(self, stats: Dict) -> str:
        """거래 통계 포맷팅"""
        try:
            return f"""
📊 거래 통계 ({stats['period']})

💰 수익 현황:
• 총 수익: ${self.format_number(stats['total_profit'])}
• 평균 수익: ${self.format_number(stats['average_profit'])}
• 최대 수익: ${self.format_number(stats['max_profit'])}
• 최대 손실: ${self.format_number(stats['max_loss'])}

📈 거래 실적:
• 총 거래: {stats['total_trades']}회
• 성공: {stats['winning_trades']}회
• 실패: {stats['losing_trades']}회
• 승률: {self.format_number(stats['win_rate'])}%

마지막 업데이트: {stats['last_updated'][:19]}
"""
        except Exception as e:
            logger.error(f"통계 포맷팅 실패: {str(e)}")
            return "통계 데이터 포맷팅 중 오류가 발생했습니다." 