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
        """일일 거래 통계 포맷팅"""
        if not positions:
            return "거래 내역이 없습니다."
            
        total_pnl = sum(float(p['pnl']) for p in positions)
        win_trades = len([p for p in positions if float(p['pnl']) > 0])
        total_trades = len(positions)
        win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0
        
        # 최대 수익/손실
        max_profit = max((float(p['pnl']) for p in positions), default=0)
        max_loss = min((float(p['pnl']) for p in positions), default=0)
        
        # 평균 레버리지
        avg_leverage = sum(float(p['leverage']) for p in positions) / len(positions) if positions else 0
        
        message = (
            "📊 일일 거래 통계\n\n"
            f"💰 총 손익: {total_pnl:.2f} USDT\n"
            f"📈 승률: {win_rate:.1f}% ({win_trades}/{total_trades})\n"
            f"📊 최대 수익: {max_profit:.2f} USDT\n"
            f"📉 최대 손실: {max_loss:.2f} USDT\n"
            f"⚡ 평균 레버리지: {avg_leverage:.1f}x\n"
        )
        
        return message

    def format_monthly_stats(self, positions: List[Dict]) -> str:
        """월간 거래 통계 포맷팅"""
        if not positions:
            return "이번 달 거래 내역이 없습니다."
            
        total_pnl = sum(float(p['pnl']) for p in positions)
        win_trades = len([p for p in positions if float(p['pnl']) > 0])
        total_trades = len(positions)
        win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0
        
        # 일별 수익 계산
        daily_pnl = {}
        for position in positions:
            date = datetime.fromtimestamp(int(position['timestamp'])/1000).strftime('%Y-%m-%d')
            daily_pnl[date] = daily_pnl.get(date, 0) + float(position['pnl'])
            
        # 연속 손익
        max_win_streak = 0
        max_loss_streak = 0
        current_win_streak = 0
        current_loss_streak = 0
        
        sorted_positions = sorted(positions, key=lambda x: x['timestamp'])
        for position in sorted_positions:
            pnl = float(position['pnl'])
            if pnl > 0:
                current_win_streak += 1
                current_loss_streak = 0
                max_win_streak = max(max_win_streak, current_win_streak)
            else:
                current_loss_streak += 1
                current_win_streak = 0
                max_loss_streak = max(max_loss_streak, current_loss_streak)
        
        message = (
            "📊 월간 거래 통계\n\n"
            f"💰 총 손익: {total_pnl:.2f} USDT\n"
            f"📈 승률: {win_rate:.1f}% ({win_trades}/{total_trades})\n"
            f"📊 일평균 거래량: {total_trades/len(daily_pnl):.1f}회\n"
            f"🔥 최대 연승: {max_win_streak}회\n"
            f"💧 최대 연패: {max_loss_streak}회\n\n"
            "📅 일별 손익:\n"
        )
        
        # 최근 7일 손익 추가
        recent_days = sorted(daily_pnl.items())[-7:]
        for date, pnl in recent_days:
            emoji = "📈" if pnl > 0 else "📉"
            message += f"{emoji} {date}: {pnl:.2f} USDT\n"
        
        return message 