from typing import Dict, List
from datetime import datetime
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class TradeAnalyzer:
    def __init__(self, trade_history_service):
        """
        Args:
            trade_history_service: 거래 기록 서비스 인스턴스
        """
        self.trade_history_service = trade_history_service
        self.analysis_dir = Path('src/data/analysis/trade_patterns')
        self.analysis_dir.mkdir(parents=True, exist_ok=True)

    def _analyze_profitable_trades(self, trades: List[Dict]) -> Dict:
        """수익 거래 분석"""
        profitable_trades = [t for t in trades if float(t.get('realized_pnl', 0)) > 0]
        return {
            'count': len(profitable_trades),
            'avg_profit': sum(float(t['realized_pnl']) for t in profitable_trades) / len(profitable_trades) if profitable_trades else 0,
            'best_profit': max((float(t['realized_pnl']) for t in profitable_trades), default=0)
        }

    def _analyze_time_patterns(self, trades: List[Dict]) -> Dict:
        """시간대별 패턴 분석"""
        hourly_stats = {hour: {
            'trades': 0,
            'profitable': 0,
            'total_pnl': 0.0,
            'win_rate': 0.0
        } for hour in range(24)}
        
        for trade in trades:
            trade_hour = datetime.fromtimestamp(int(trade['timestamp'])/1000).hour
            pnl = float(trade.get('realized_pnl', 0))
            
            hourly_stats[trade_hour]['trades'] += 1
            hourly_stats[trade_hour]['total_pnl'] += pnl
            if pnl > 0:
                hourly_stats[trade_hour]['profitable'] += 1
        
        best_hours = []
        best_win_rate = 0
        
        for hour, stats in hourly_stats.items():
            if stats['trades'] > 0:
                stats['win_rate'] = (stats['profitable'] / stats['trades']) * 100
                if stats['trades'] >= 3 and stats['win_rate'] > best_win_rate:
                    best_win_rate = stats['win_rate']
                    best_hours = [hour]
                elif stats['trades'] >= 3 and stats['win_rate'] == best_win_rate:
                    best_hours.append(hour)
        
        return {
            'hourly_stats': hourly_stats,
            'summary': {
                'most_active_hour': max(hourly_stats.items(), key=lambda x: x[1]['trades'])[0],
                'best_win_rate': best_win_rate,
                'best_hours': [f"{hour:02d}:00-{hour+1:02d}:00" for hour in best_hours]
            }
        }

    def _analyze_position_sizes(self, trades: List[Dict]) -> Dict:
        """포지션 크기 패턴 분석"""
        size_ranges = [
            (0.001, 0.005),  # 소형
            (0.005, 0.01),   # 중소형
            (0.01, 0.05),    # 중형
            (0.05, 0.1),     # 대형
            (0.1, float('inf'))  # 초대형
        ]
        
        size_names = ['small', 'medium_small', 'medium', 'large', 'extra_large']
        size_stats = {name: {'trades': 0, 'profitable': 0, 'total_pnl': 0.0, 'win_rate': 0.0}
                     for name in size_names}
        
        for trade in trades:
            amount = float(trade.get('amount', 0))
            pnl = float(trade.get('realized_pnl', 0))
            
            for (min_size, max_size), size_name in zip(size_ranges, size_names):
                if min_size <= amount < max_size:
                    stats = size_stats[size_name]
                    stats['trades'] += 1
                    stats['total_pnl'] += pnl
                    if pnl > 0:
                        stats['profitable'] += 1
                    break
        
        best_size = None
        best_roi = float('-inf')
        
        for size_name, stats in size_stats.items():
            if stats['trades'] > 0:
                stats['win_rate'] = (stats['profitable'] / stats['trades']) * 100
                stats['avg_pnl'] = stats['total_pnl'] / stats['trades']
                roi = stats['avg_pnl'] * stats['win_rate'] / 100
                if roi > best_roi and stats['trades'] >= 3:
                    best_roi = roi
                    best_size = size_name
        
        return {
            'size_stats': size_stats,
            'summary': {
                'best_size': best_size,
                'best_roi': best_roi,
                'size_ranges': {
                    'small': '0.001-0.005 BTC',
                    'medium_small': '0.005-0.01 BTC',
                    'medium': '0.01-0.05 BTC',
                    'large': '0.05-0.1 BTC',
                    'extra_large': '0.1+ BTC'
                }
            }
        }

    def _analyze_price_levels(self, trades: List[Dict]) -> Dict:
        """가격대별 패턴 분석"""
        try:
            if not trades:
                return {}
            
            prices = []
            for trade in trades:
                try:
                    # 첫 번째 형태 (entry_price/exit_price)
                    if 'entry_price' in trade:
                        prices.extend([
                            float(trade['entry_price']),
                            float(trade['exit_price'])
                        ])
                    # 두 번째 형태 (price)
                    elif 'price' in trade:
                        prices.append(float(trade['price']))
                    
                except (KeyError, ValueError) as e:
                    continue

            if not prices:
                logger.warning("처리 가능한 가격 데이터가 없습니다")
                return {}

            min_price = min(prices)
            max_price = max(prices)
            price_range = max_price - min_price
            
            interval = price_range / 5
            price_ranges = []
            for i in range(5):
                range_min = min_price + (i * interval)
                range_max = min_price + ((i + 1) * interval)
                price_ranges.append((range_min, range_max))
            
            price_stats = {}
            for i, (range_min, range_max) in enumerate(price_ranges):
                price_stats[f"range_{i+1}"] = {
                    'min_price': range_min,
                    'max_price': range_max,
                    'trades': 0,
                    'buys': 0,
                    'sells': 0,
                    'profitable': 0,
                    'total_pnl': 0.0,
                    'win_rate': 0.0,
                    'price_range': f"{range_min:,.0f} - {range_max:,.0f}"
                }
            
            for trade in trades:
                try:
                    # 첫 번째 형태 (entry_price/exit_price)
                    if 'entry_price' in trade:
                        price = float(trade['entry_price'])
                    # 두 번째 형태 (price)
                    elif 'price' in trade:
                        price = float(trade['price'])
                    else:
                        continue

                    pnl = float(trade.get('realized_pnl', 0))
                    side = trade.get('side', '').lower()
                    
                    for i, (range_min, range_max) in enumerate(price_ranges):
                        if range_min <= price <= range_max:
                            range_key = f"range_{i+1}"
                            stats = price_stats[range_key]
                            stats['trades'] += 1
                            stats['total_pnl'] += pnl
                            if pnl > 0:
                                stats['profitable'] += 1
                            if side == 'buy':
                                stats['buys'] += 1
                            else:
                                stats['sells'] += 1
                            break
                except (KeyError, ValueError):
                    continue
            
            best_range = None
            best_win_rate = 0
            
            for range_key, stats in price_stats.items():
                if stats['trades'] > 0:
                    stats['win_rate'] = (stats['profitable'] / stats['trades']) * 100
                    stats['avg_pnl'] = stats['total_pnl'] / stats['trades']
                    stats['buy_ratio'] = (stats['buys'] / stats['trades']) * 100
                    if stats['trades'] >= 3 and stats['win_rate'] > best_win_rate:
                        best_win_rate = stats['win_rate']
                        best_range = range_key
            
            return {
                'price_stats': price_stats,
                'summary': {
                    'price_range': f"{min_price:,.0f} - {max_price:,.0f} USDT",
                    'best_range': best_range,
                    'best_win_rate': best_win_rate,
                    'avg_price': sum(prices) / len(prices)
                }
            }

        except Exception as e:
            logger.error(f"가격대별 분석 중 오류: {str(e)}")
            logger.error("상세 에러: ", exc_info=True)
            return {} 

    async def analyze_patterns(self, days: int = 30) -> Dict:
        """
        최근 N일간의 거래 패턴 분석
        Args:
            days: 분석할 기간 (일)
        Returns:
            분석 결과 딕셔너리
        """
        try:
            trades = self.trade_history_service.load_trades()
            if not trades:
                logger.warning("분석할 거래 기록이 없습니다.")
                return {}

            # 기간 필터링
            cutoff_time = datetime.now().timestamp() * 1000 - (days * 24 * 60 * 60 * 1000)
            recent_trades = [t for t in trades if t['timestamp'] > cutoff_time]

            # 각 분석 결과를 개별적으로 처리
            patterns = {}
            
            try:
                patterns['profitable_trades'] = self._analyze_profitable_trades(recent_trades)
            except Exception as e:
                logger.error(f"수익성 분석 중 오류: {str(e)}")
                patterns['profitable_trades'] = {}
                
            try:
                patterns['time_patterns'] = self._analyze_time_patterns(recent_trades)
            except Exception as e:
                logger.error(f"시간대별 분석 중 오류: {str(e)}")
                patterns['time_patterns'] = {}
                
            try:
                patterns['size_patterns'] = self._analyze_position_sizes(recent_trades)
            except Exception as e:
                logger.error(f"포지션 크기 분석 중 오류: {str(e)}")
                patterns['size_patterns'] = {}
                
            try:
                patterns['price_patterns'] = self._analyze_price_levels(recent_trades)
            except Exception as e:
                logger.error(f"가격대별 분석 중 오류: {str(e)}")
                patterns['price_patterns'] = {}

            return patterns

        except Exception as e:
            logger.error(f"거래 패턴 분석 중 오류: {str(e)}")
            logger.error("상세 에러: ", exc_info=True)
            return {} 