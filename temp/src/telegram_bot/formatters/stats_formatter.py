from .base_formatter import BaseFormatter
from typing import Dict
import logging

logger = logging.getLogger(__name__)

class StatsFormatter(BaseFormatter):
    def format_stats(self, stats: Dict) -> str:
        """거래 통계 포맷팅"""
        try:
            # 시간대별 성과 포맷팅
            time_perf = stats['time_performance']
            time_performance = "\n".join([
                f"• {market.upper()}: {data['trades']}건, ${self.format_number(data['profit'])}"
                for market, data in time_perf.items()
            ])

            # 패턴 분석 포맷팅
            entry_patterns = ", ".join([f"{p[0]}({p[1]}회)" for p in stats['entry_patterns'][:2]])
            exit_patterns = ", ".join([f"{p[0]}({p[1]}회)" for p in stats['exit_patterns'][:2]])
            time_patterns = ", ".join([f"{p[0]}({p[1]}회)" for p in stats['time_patterns'][:2]])

            return f"""
📊 거래 통계 ({stats['period']})

💰 수익 현황:
• 총 수익: ${self.format_number(stats['total_profit'])}
• 평균 수익: ${self.format_number(stats['average_profit'])}
• 평균 손실: ${self.format_number(stats['average_loss'])}
• 최대 수익: ${self.format_number(stats['max_profit'])}
• 최대 손실: ${self.format_number(stats['max_loss'])}

📈 거래 실적:
• 총 거래: {stats['total_trades']}회
• 성공: {stats['winning_trades']}회
• 실패: {stats['losing_trades']}회
• 승률: {self.format_number(stats['win_rate'])}%
• 수익률: {self.format_number(stats['profit_factor'])}

🔄 포지션별 실적:
• 롱: {stats['long_trades']}회 (${self.format_number(stats['long_profit'])})
• 숏: {stats['short_trades']}회 (${self.format_number(stats['short_profit'])})

⏰ 시간대별 성과:
{time_performance}

📊 거래 패턴:
• 주요 진입: {entry_patterns}
• 주요 청산: {exit_patterns}
• 선호 시간대: {time_patterns}

📉 리스크 지표:
• 최대 손실폭: ${self.format_number(stats['max_drawdown'])}
• 샤프 비율: {self.format_number(stats['sharpe_ratio'])}
• 리스크/리워드: {self.format_number(stats['risk_reward_ratio'])}

마지막 업데이트: {stats['last_updated']}
"""
        except Exception as e:
            logger.error(f"통계 포맷팅 실패: {str(e)}")
            return "통계 데이터 포맷팅 중 오류가 발생했습니다."

    # BaseFormatter의 추상 메서드 구현
    def format_balance(self, balance: Dict) -> str:
        """잔고 정보 포맷팅 (StatsFormatter에서는 미사용)"""
        return "Not implemented"

    def format_position(self, position: Dict) -> str:
        """포지션 정보 포맷팅 (StatsFormatter에서는 미사용)"""
        return "Not implemented"

    def format_status(self, status: Dict) -> str:
        """상태 정보 포맷팅 (StatsFormatter에서는 미사용)"""
        return "Not implemented" 