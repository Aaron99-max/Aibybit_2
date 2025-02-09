from .base_formatter import BaseFormatter
from typing import Dict, List
import logging
from datetime import datetime

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

    def format_daily_stats(self, positions: List[Dict]) -> str:
        """일일 포지션 통계 포맷팅"""
        if not positions:
            return "📊 오늘은 청산된 포지션이 없습니다."
        
        total_pnl = sum(float(p['pnl']) for p in positions)
        winning_trades = len([p for p in positions if float(p['pnl']) > 0])
        losing_trades = len([p for p in positions if float(p['pnl']) < 0])
        total_trades = len(positions)
        
        # 롱/숏 구분
        long_positions = [p for p in positions if p['side'] == 'Buy']
        short_positions = [p for p in positions if p['side'] == 'Sell']
        
        long_pnl = sum(float(p['pnl']) for p in long_positions)
        short_pnl = sum(float(p['pnl']) for p in short_positions)
        
        # 승률 계산
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # 최대 수익/손실
        max_profit = max([float(p['pnl']) for p in positions]) if positions else 0
        max_loss = min([float(p['pnl']) for p in positions]) if positions else 0
        
        message = f"""
📊 일일 거래 통계

💰 수익 현황:
• 총 수익: ${self.format_number(total_pnl)}
• 최대 수익: ${self.format_number(max_profit)}
• 최대 손실: ${self.format_number(max_loss)}

📈 거래 실적:
• 총 거래: {total_trades}회
• 성공: {winning_trades}회
• 실패: {losing_trades}회
• 승률: {self.format_number(win_rate)}%

🔄 포지션별 실적:
• 롱: {len(long_positions)}회 (${self.format_number(long_pnl)})
• 숏: {len(short_positions)}회 (${self.format_number(short_pnl)})
"""
        return message.strip()

    def format_monthly_stats(self, positions: List[Dict]) -> str:
        """월간 포지션 통계 포맷팅"""
        if not positions:
            return "📊 이번 달은 청산된 포지션이 없습니다."
        
        total_pnl = sum(float(p['pnl']) for p in positions)
        winning_trades = len([p for p in positions if float(p['pnl']) > 0])
        losing_trades = len([p for p in positions if float(p['pnl']) < 0])
        total_trades = len(positions)
        
        # 롱/숏 구분
        long_positions = [p for p in positions if p['side'] == 'Buy']
        short_positions = [p for p in positions if p['side'] == 'Sell']
        
        long_pnl = sum(float(p['pnl']) for p in long_positions)
        short_pnl = sum(float(p['pnl']) for p in short_positions)
        
        # 승률 계산
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # 평균 수익/손실
        winning_pnls = [float(p['pnl']) for p in positions if float(p['pnl']) > 0]
        losing_pnls = [float(p['pnl']) for p in positions if float(p['pnl']) < 0]
        
        avg_profit = sum(winning_pnls) / len(winning_pnls) if winning_pnls else 0
        avg_loss = sum(losing_pnls) / len(losing_pnls) if losing_pnls else 0
        
        # 최대 수익/손실
        max_profit = max([float(p['pnl']) for p in positions]) if positions else 0
        max_loss = min([float(p['pnl']) for p in positions]) if positions else 0
        
        message = f"""
📊 월간 거래 통계

💰 수익 현황:
• 총 수익: ${self.format_number(total_pnl)}
• 평균 수익: ${self.format_number(avg_profit)}
• 평균 손실: ${self.format_number(avg_loss)}
• 최대 수익: ${self.format_number(max_profit)}
• 최대 손실: ${self.format_number(max_loss)}

📈 거래 실적:
• 총 거래: {total_trades}회
• 성공: {winning_trades}회
• 실패: {losing_trades}회
• 승률: {self.format_number(win_rate)}%

🔄 포지션별 실적:
• 롱: {len(long_positions)}회 (${self.format_number(long_pnl)})
• 숏: {len(short_positions)}회 (${self.format_number(short_pnl)})
"""
        return message.strip()