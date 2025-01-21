from typing import Dict, List

from datetime import datetime

import logging

from pathlib import Path

from collections import Counter

import numpy as np

import json

import traceback



logger = logging.getLogger(__name__)



class Position:

    def __init__(self, side, size, entry_price, entry_time):

        self.side = side          # long/short

        self.size = size          # 포지션 크기

        self.entry_price = entry_price  # 평균 진입가

        self.entry_time = entry_time    # 첫 진입 시간

        self.last_update_time = entry_time  # 마지막 업데이트 시간

        self.pnl = 0             # 실현 손익

        self.closed_size = 0     # 청산된 크기

        self.is_closed = False   # 완전 청산 여부

        self.close_type = None   # 청산 타입 (CreateByClosing/CreateByStopLoss/CreateByTakeProfit)

        self.trades = []         # 포지션에 속한 거래들



    def add(self, size, price, timestamp, trade):

        """포지션 추가"""

        self.trades.append(trade)

        total_value = (self.entry_price * self.size) + (price * size)

        total_size = self.size + size

        self.entry_price = total_value / total_size

        self.size = total_size

        self.last_update_time = timestamp



    def close(self, size, price, timestamp, close_type=None, trade=None):

        """포지션 청산"""

        if trade:

            self.trades.append(trade)

            realized_pnl = float(trade['info'].get('execRealizedPnl', 0))

            

            # 실제 청산된 크기가 있는 경우만 PnL 반영

            if float(trade['info'].get('closedSize', 0)) > 0:

                self.pnl += realized_pnl

            

            self.size -= size

            self.closed_size += size

            self.last_update_time = timestamp

            

            if close_type:

                self.close_type = close_type

            

            if self.size <= 0:

                self.is_closed = True

                return True

        return False



class TradeAnalyzer:

    def __init__(self, trade_store):

        self.trade_store = trade_store

        self.trades = []

        self.positions = []

        self.current_position = None



    def _is_valid_trade(self, trade):

        """유효한 거래인지 확인"""

        if not trade or 'info' not in trade:

            return False

        

        info = trade['info']

        exec_type = info.get('execType')

        create_type = info.get('createType')

        exec_qty = float(info.get('execQty', 0))

        closed_size = float(info.get('closedSize', 0))

        

        # Funding, 청산, 자동 감소는 제외

        invalid_types = ['Funding', 'AdlTrade', 'LiquidityTrade', 'AutoDeleveraging']

        if exec_type in invalid_types:

            return False

        

        # 실제 거래량이 있는 경우만 포함 (취소된 주문 제외)

        if exec_qty <= 0 and closed_size <= 0:

            return False

        

        # 디버그 로그 추가

        logger.debug(f"거래 유효성 검사:")

        logger.debug(f"- execType: {exec_type}")

        logger.debug(f"- createType: {create_type}")

        logger.debug(f"- execQty: {exec_qty}")

        logger.debug(f"- closedSize: {closed_size}")

        

        return True



    async def analyze_trades(self):

        """거래 데이터 종합 분석"""

        try:

            self.trades = self.trade_store.get_all_trades()

            if not self.trades:

                logger.warning("분석할 거래 데이터가 없습니다")

                return None



            # 유효한 거래만 필터링

            valid_trades = [t for t in self.trades if self._is_valid_trade(t)]

            logger.info(f"전체 거래: {len(self.trades)}, 유효한 거래: {len(valid_trades)}")

            

            # 날짜별 거래 수 확인

            date_counts = {}

            for trade in valid_trades:

                date = datetime.fromtimestamp(trade['timestamp']/1000).date()

                if date not in date_counts:

                    date_counts[date] = 0

                date_counts[date] += 1

            

            logger.info("날짜별 거래 수:")

            for date in sorted(date_counts.keys()):

                logger.info(f"- {date}: {date_counts[date]}건")



            # 디버그 로그 추가

            logger.info(f"전체 거래 수: {len(self.trades)}")

            sample_trade = self.trades[0] if self.trades else None

            logger.info(f"첫 번째 거래 샘플: {sample_trade}")

            

            # 주문ID별 거래 수 확인

            order_counts = {}

            for trade in self.trades:

                order_id = trade.get('order')

                if order_id not in order_counts:

                    order_counts[order_id] = 0

                order_counts[order_id] += 1

            

            logger.info(f"고유 주문 수: {len(order_counts)}")

            logger.info(f"주문별 거래 수 예시: {dict(list(order_counts.items())[:5])}")



            # 기본 거래 통계

            trade_stats = self._analyze_trade_stats()

            

            # 포지션 정보에서 PnL 계산

            positions = trade_stats['positions']

            

            # 롱/숏 포지션 구분

            long_positions = [p for p in positions if p['side'] == 'buy']

            short_positions = [p for p in positions if p['side'] == 'sell']

            

            # 승/패 구분

            winning_positions = [p for p in positions if p['final_pnl'] > 0]

            losing_positions = [p for p in positions if p['final_pnl'] < 0]

            

            # PnL 계산

            total_pnl = sum(p['final_pnl'] for p in positions)

            long_pnl = sum(p['final_pnl'] for p in long_positions)

            short_pnl = sum(p['final_pnl'] for p in short_positions)



            # 패턴 분석

            pattern_stats = self._analyze_patterns()

            

            # 시간대별 성과

            time_stats = self._analyze_time_performance()

            

            # 리스크 지표

            risk_stats = self._calculate_risk_metrics()



            return {

                # 기본 거래 통계

                'total_trades': len(positions),

                'winning_trades': len(winning_positions),

                'losing_trades': len(losing_positions),

                'win_rate': round(len(winning_positions) / len(positions) * 100, 2) if positions else 0,

                'total_profit': round(total_pnl, 4),

                'average_profit': round(sum(p['final_pnl'] for p in winning_positions) / len(winning_positions), 4) if winning_positions else 0,

                'average_loss': round(abs(sum(p['final_pnl'] for p in losing_positions)) / len(losing_positions), 4) if losing_positions else 0,

                'profit_factor': round(abs(long_pnl / short_pnl), 4) if short_pnl != 0 else 0,

                'max_profit': round(max((p['final_pnl'] for p in winning_positions), default=0), 4),

                'max_loss': round(min((p['final_pnl'] for p in losing_positions), default=0), 4),

                

                # 포지션별 통계

                'long_trades': len(long_positions),

                'short_trades': len(short_positions),

                'long_profit': round(long_pnl, 4),

                'short_profit': round(short_pnl, 4),

                

                # 패턴 분석

                'entry_patterns': pattern_stats['entry_patterns'],

                'exit_patterns': pattern_stats['exit_patterns'],

                'time_patterns': pattern_stats['time_patterns'],

                

                # 시간대별 성과

                'time_performance': time_stats,

                

                # 리스크 지표

                'max_drawdown': risk_stats['max_drawdown'],

                'sharpe_ratio': risk_stats['sharpe_ratio'],

                'risk_reward_ratio': risk_stats['risk_reward_ratio'],

                

                # 기간 정보

                'period': f"{self.trades[0]['datetime']} ~ {self.trades[-1]['datetime']}",

                'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            }



        except Exception as e:

            logger.error(f"거래 분석 중 오류: {str(e)}")

            logger.error(traceback.format_exc())  # 스택 트레이스 추가

            return None



    def _group_trades_by_order(self):

        """주문 ID별로 거래 그룹화"""

        order_groups = {}

        

        for trade in self.trades:

            order_id = trade.get('order')

            if order_id not in order_groups:

                order_groups[order_id] = {

                    'trades': [],

                    'side': trade['info'].get('side', '').lower(),

                    'total_size': 0,

                    'closed_size': 0,

                    'pnl': 0,

                    'entry_price': float(trade['info'].get('execPrice', 0)),

                    'timestamp': trade['timestamp'],

                    'create_type': trade['info'].get('createType')

                }

            

            group = order_groups[order_id]

            group['trades'].append(trade)

            exec_qty = float(trade['info'].get('execQty', 0))

            closed_size = float(trade['info'].get('closedSize', 0))

            group['total_size'] += exec_qty

            group['closed_size'] += closed_size

            

            if closed_size > 0:

                pnl = float(trade['info'].get('execRealizedPnl', 0))

                group['pnl'] += pnl

        

        return order_groups



    def _analyze_trade_stats(self):

        """포지션 기준 거래 통계 분석"""

        positions = []

        current_position = None

        position_count = 0
        
        for trade in sorted(self.trades, key=lambda x: x['timestamp']):
            info = trade['info']
            side = info.get('side', '').lower()
            price = float(info.get('execPrice', 0))
            exec_qty = round(float(info.get('execQty', 0)), 3)
            closed_size = round(float(info.get('closedSize', 0)), 3)
            realized_pnl = float(trade.get('execRealizedPnl', 0))
            trade_time = datetime.fromtimestamp(trade['timestamp']/1000).strftime('%Y-%m-%d %H:%M:%S')
            
            # 첫 거래 또는 포지션 없을 때
            if not current_position:
                position_count += 1
                new_position_size = round(exec_qty - closed_size, 3)
                current_position = {
                    'position_number': position_count,
                    'side': side,
                    'size': new_position_size,
                    'entry_price': price,
                    'pnl': realized_pnl,
                    'final_pnl': 0,
                    'trades': [trade],
                    'start_time': trade['timestamp']
                }
                logger.info(f"[{trade_time}] 신규 포지션 #{position_count} 생성: {side} {new_position_size}@{price}")
                continue
            
            # 청산이 있는 경우
            if closed_size > 0:
                # 현재 포지션 청산
                logger.info(f"[{trade_time}] 포지션 #{current_position['position_number']} 청산 완료")
                current_position['final_pnl'] = current_position['pnl']
                positions.append(current_position)
                
                # 청산 후 남은 수량으로 새 포지션 생성
                new_position_size = round(exec_qty - closed_size, 3)
                if new_position_size > 0:
                    position_count += 1
                    current_position = {
                        'position_number': position_count,
                        'side': side,
                        'size': new_position_size,
                        'entry_price': price,
                        'pnl': 0,
                        'final_pnl': 0,
                        'trades': [trade],
                        'start_time': trade['timestamp']
                    }
                    logger.info(f"[{trade_time}] 신규 포지션 #{position_count} 생성: {side} {new_position_size}@{price}")
                else:
                    current_position = None
            else:
                # 같은 방향이면 포지션에 추가
                if current_position['side'] == side:
                    current_position['size'] = round(current_position['size'] + exec_qty, 3)
                    current_position['trades'].append(trade)
                    current_position['pnl'] += realized_pnl
                    logger.info(f"[{trade_time}] 포지션 #{current_position['position_number']} 추가: +{exec_qty} (총 {current_position['size']})")
        
        # 마지막 포지션 처리
        if current_position:
            current_position['final_pnl'] = current_position['pnl']
            positions.append(current_position)
        
        return {
            'total_positions': len(positions),
            'long_positions': len([p for p in positions if p['side'] == 'buy']),
            'short_positions': len([p for p in positions if p['side'] == 'sell']),
            'positions': positions
        }



    def _analyze_patterns(self):

        """거래 패턴 분석"""

        patterns = {

            'entry_patterns': [],

            'exit_patterns': [],

            'time_patterns': []

        }

        

        for trade in self.trades:

            # 매수/매도 패턴

            side = trade.get('side', '').lower()

            maker_taker = trade.get('takerOrMaker', '')

            order_type = trade.get('type', '')

            pattern = f"{side}-{maker_taker}-{order_type}"

            

            # 시간대 분석

            timestamp = trade.get('timestamp', 0)

            if timestamp:

                dt = datetime.fromtimestamp(timestamp/1000)

                hour = dt.hour

                

                if 0 <= hour < 8:

                    time_zone = "아시아 장"

                elif 8 <= hour < 16:

                    time_zone = "유럽 장"

                else:

                    time_zone = "미국 장"

                    

                patterns['time_patterns'].append(time_zone)

            

            if side == 'buy':

                patterns['entry_patterns'].append(pattern)

            else:

                patterns['exit_patterns'].append(pattern)

                

        return {

            'entry_patterns': Counter(patterns['entry_patterns']).most_common(3),

            'exit_patterns': Counter(patterns['exit_patterns']).most_common(3),

            'time_patterns': Counter(patterns['time_patterns']).most_common(3)

        }



    def _analyze_time_performance(self):

        """시간대별 성과 분석"""

        time_performance = {

            'asia': {'trades': 0, 'profit': 0},

            'europe': {'trades': 0, 'profit': 0},

            'us': {'trades': 0, 'profit': 0}

        }

        

        for trade in self.trades:

            pnl = float(trade.get('execRealizedPnl', 0))

            

            timestamp = trade.get('timestamp', 0)

            if timestamp:

                hour = datetime.fromtimestamp(timestamp/1000).hour

                

                if 0 <= hour < 8:

                    market = 'asia'

                elif 8 <= hour < 16:

                    market = 'europe'

                else:

                    market = 'us'

                    

                time_performance[market]['trades'] += 1

                time_performance[market]['profit'] += pnl

        

        return time_performance



    def _calculate_risk_metrics(self):

        """리스크 지표 계산"""

        if not self.trades:

            return {'max_drawdown': 0, 'sharpe_ratio': 0, 'risk_reward_ratio': 0}



        # 일별 PnL 집계

        daily_pnl = {}

        for trade in self.trades:

            if float(trade['info'].get('closedSize', 0)) > 0:

                date = datetime.fromtimestamp(trade['timestamp']/1000).date()

                pnl = float(trade['info'].get('execRealizedPnl', 0))

                

                if date not in daily_pnl:

                    daily_pnl[date] = 0

                daily_pnl[date] += pnl



        dates = sorted(daily_pnl.keys())

        cumulative_pnl = []

        current_pnl = 0

        

        for date in dates:

            current_pnl += daily_pnl[date]

            cumulative_pnl.append(current_pnl)



        if not cumulative_pnl:

            return {'max_drawdown': 0, 'sharpe_ratio': 0, 'risk_reward_ratio': 0}



        # 최대 손실폭 계산

        peak = np.maximum.accumulate(cumulative_pnl)

        drawdown = peak - cumulative_pnl

        max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0



        # 샤프 비율 계산

        if len(cumulative_pnl) > 1:

            daily_returns = np.diff(cumulative_pnl)

            sharpe_ratio = np.sqrt(365) * (np.mean(daily_returns) / np.std(daily_returns)) if np.std(daily_returns) != 0 else 0

        else:

            sharpe_ratio = 0



        # 리스크/리워드 비율 계산

        profitable_trades = []

        loss_trades = []

        

        for trade in self.trades:

            if float(trade['info'].get('closedSize', 0)) > 0:

                pnl = float(trade['info'].get('execRealizedPnl', 0))

                if pnl > 0:

                    profitable_trades.append(pnl)

                elif pnl < 0:

                    loss_trades.append(abs(pnl))



        avg_profit = np.mean(profitable_trades) if profitable_trades else 0

        avg_loss = np.mean(loss_trades) if loss_trades else 0

        risk_reward_ratio = round(avg_profit / avg_loss, 2) if avg_loss != 0 else 0



        return {

            'max_drawdown': round(max_drawdown, 2),

            'sharpe_ratio': round(sharpe_ratio, 2),

            'risk_reward_ratio': risk_reward_ratio

        } 