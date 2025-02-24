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

        

        # 로깅 설정 추가

        self.logger = logging.getLogger(__name__)

        self.logger.setLevel(logging.INFO)



    async def analyze_trades(self):

        """거래 데이터 종합 분석"""

        try:

            self.trades = await self.trade_store.get_all_trades()

            self.logger.info(f"로드된 거래 수: {len(self.trades)}")

            

            if not self.trades:

                self.logger.warning("분석할 거래 데이터가 없습니다")

                return None



            # 거래 데이터 유효성 검사

            valid_trades = []

            invalid_count = 0

            for trade in self.trades:

                if self._is_valid_trade(trade):

                    valid_trades.append(trade)

                else:

                    invalid_count += 1

            

            self.logger.info(f"유효한 거래 수: {len(valid_trades)}")

            self.logger.info(f"유효하지 않은 거래 수: {invalid_count}")



            if not valid_trades:

                self.logger.warning("유효한 거래 데이터가 없습니다")

                return None



            self.trades = valid_trades

            

            # 거래 데이터 정렬

            self.trades.sort(key=lambda x: x['timestamp'])



            # 거래 데이터 유효성 검사

            valid_trades = [t for t in self.trades if self._is_valid_trade(t)]

            self.logger.info(f"전체 거래: {len(self.trades)}, 유효한 거래: {len(valid_trades)}")

            

            # 날짜별 거래 수 확인

            date_counts = {}

            for trade in valid_trades:

                date = datetime.fromtimestamp(trade['timestamp']/1000).date()

                if date not in date_counts:

                    date_counts[date] = 0

                date_counts[date] += 1

            

            self.logger.info("날짜별 거래 수:")

            for date in sorted(date_counts.keys()):

                self.logger.info(f"- {date}: {date_counts[date]}건")



            # 디버그 로그 추가

            self.logger.info(f"전체 거래 수: {len(self.trades)}")

            sample_trade = self.trades[0] if self.trades else None

            self.logger.info(f"첫 번째 거래 샘플: {sample_trade}")

            

            # 주문ID별 거래 수 확인

            order_counts = {}

            for trade in self.trades:

                order_id = trade.get('order')

                if order_id not in order_counts:

                    order_counts[order_id] = 0

                order_counts[order_id] += 1

            

            self.logger.info(f"고유 주문 수: {len(order_counts)}")

            self.logger.info(f"주문별 거래 수 예시: {dict(list(order_counts.items())[:5])}")



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

            self.logger.error(f"거래 분석 중 오류 발생: {str(e)}")

            self.logger.error(traceback.format_exc())

            return None



    def _is_valid_trade(self, trade):

        """유효한 거래인지 확인"""

        try:

            if not trade or not isinstance(trade, dict):

                return False



            # 필수 필드 확인

            required_fields = ['info', 'timestamp', 'side', 'price', 'amount']

            if not all(field in trade for field in required_fields):

                return False



            info = trade.get('info', {})

            if not info:

                return False



            # info 필드 내 필수 항목 확인

            required_info_fields = ['execQty', 'closedSize', 'execType']

            if not all(field in info for field in required_info_fields):

                return False



            # 거래량 확인

            exec_qty = float(info.get('execQty', 0))

            closed_size = float(info.get('closedSize', 0))



            if exec_qty <= 0 and closed_size <= 0:

                return False



            # 거래 타입 확인

            exec_type = info.get('execType')

            if exec_type not in ['Trade']:

                return False



            return True



        except Exception as e:

            self.logger.error(f"거래 유효성 검사 중 오류: {str(e)}")

            return False



    def _is_same_position(self, trade1: Dict, trade2: Dict) -> bool:
        """두 거래가 같은 포지션에 속하는지 확인"""
        try:
            # 주문 ID로 비교
            order1 = trade1.get('order')
            order2 = trade2.get('order')
            
            # createType 확인
            create_type1 = trade1['info'].get('createType', '')
            create_type2 = trade2['info'].get('createType', '')
            
            # 같은 주문이면서
            if order1 == order2:
                return True
            
            # 청산 관련 거래인 경우 ('CreateByClosing', 'CreateByLiq' 등)
            if 'Closing' in create_type1 or 'Closing' in create_type2:
                return True
            
            return False
        
        except Exception as e:
            self.logger.error(f"포지션 비교 중 오류: {str(e)}")
            return False

    def _group_trades_by_position(self, trades: List[Dict]) -> List[Position]:
        """거래들을 포지션별로 그룹화"""
        positions = []
        current_position = None
        
        for trade in trades:
            # 첫 거래이거나 이전 포지션과 다른 경우
            if not current_position or not self._is_same_position(trade, current_position.trades[-1]):
                if current_position:
                    positions.append(current_position)
                # 새로운 포지션 생성
                current_position = Position(
                    side=trade['side'],
                    size=float(trade['amount']),
                    entry_price=float(trade['price']),
                    entry_time=trade['timestamp']
                )
                current_position.add_trade(trade)
            else:
                # 기존 포지션에 거래 추가
                current_position.add_trade(trade)
        
        # 마지막 포지션 추가
        if current_position:
            positions.append(current_position)
        
        return positions



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
            create_type = info.get('createType', '')
            trade_time = datetime.fromtimestamp(trade['timestamp']/1000).strftime('%Y-%m-%d %H:%M:%S')
            
            new_position_size = round(exec_qty - closed_size, 3)
            
            # 실제 거래량이 0인 경우 스킵
            if new_position_size <= 0 and not current_position:
                continue
            
            # 새로운 포지션 시작 조건:
            # 1. 첫 거래
            # 2. 이전 포지션이 완전히 청산됨
            # 3. CreateByUser로 새로운 주문 시작
            if (not current_position or 
                current_position['size'] <= 0 or 
                (create_type == 'CreateByUser' and not self._is_same_position(trade, current_position['trades'][-1]))):
                
                position_count += 1
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
                self.logger.info(f"[{trade_time}] 신규 포지션 #{position_count} 생성: {side} {new_position_size}@{price}")
                
            else:
                # 기존 포지션에 추가
                current_position['trades'].append(trade)
                current_position['size'] = round(current_position['size'] + new_position_size, 3)
                current_position['pnl'] += realized_pnl
                
                if new_position_size > 0:
                    self.logger.info(f"[{trade_time}] 포지션 #{current_position['position_number']} 추가: +{new_position_size} (총 {current_position['size']})")
            
            # 포지션이 완전히 청산된 경우
            if current_position and current_position['size'] <= 0:
                self.logger.info(f"[{trade_time}] 포지션 #{current_position['position_number']} 청산 완료")
                current_position['final_pnl'] = current_position['pnl']
                positions.append(current_position)
                current_position = None
            
        # 마지막 포지션 처리
        if current_position:
            current_position['final_pnl'] = current_position['pnl']
            positions.append(current_position)
        
        return {
            'positions': positions,
            'total_positions': len(positions)
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