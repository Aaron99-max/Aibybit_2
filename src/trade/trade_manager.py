import logging
import traceback
from typing import Dict

logger = logging.getLogger('trade_manager')

class TradeManager:
    def __init__(self, bybit_client, order_service, position_service, balance_service, telegram_bot=None):
        """
        Args:
            bybit_client: 하위 호환성을 위해 유지
            order_service: 주문 서비스
            position_service: 포지션 서비스
            balance_service: 잔고 서비스 추가
            telegram_bot: 하위 호환성을 위해 유지
        """
        self.order_service = order_service
        self.position_service = position_service
        self.balance_service = balance_service
        self.symbol = 'BTCUSDT'
        
    async def execute_trade_signal(self, analysis: Dict) -> bool:
        """거래 신호 실행"""
        try:
            logger.info("=== 거래 신호 실행 ===")
            
            # position_service를 통해 포지션 조회
            position = await self.position_service.get_current_position()
            logger.info(f"현재 포지션 상태: {position}")
            
            # 포지션이 있는 경우
            if position and float(position.get('size', 0)) > 0:
                logger.info(f"""
=== 기존 포지션 처리 ===
심볼: {position.get('symbol')}
방향: {position.get('side')}
크기: {position.get('size')} BTC
레버리지: {position.get('leverage')}x
진입가: {position.get('entry_price')}
""")
                return await self._handle_existing_position(position, analysis)
            
            # 포지션이 없는 경우
            else:
                logger.info("새 포지션 진입")
                return await self._open_new_position(analysis)
            
        except Exception as e:
            logger.error(f"거래 신호 실행 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def _handle_existing_position(self, position: Dict, analysis: Dict) -> bool:
        """기존 포지션 처리"""
        try:
            strategy = analysis.get('trading_strategy', {})
            new_side = 'Buy' if strategy['position_suggestion'] == '매수' else 'Sell'
            new_leverage = int(strategy['leverage'])
            target_size = float(strategy['position_size'])

            current_side = position['side'].title()
            current_leverage = int(position['leverage'])
            current_size = float(position['size'])

            logger.info(f"""
=== 포지션 조정 시작 ===
현재: {current_side} {current_size} BTC ({current_leverage}x)
목표: {new_side} {target_size}% ({new_leverage}x)
""")

            # 방향 비교 시 대소문자 무시
            if current_side.upper() != new_side.upper():
                logger.info("포지션 방향이 다름 - 청산 후 재진입")
                if await self._close_position(position):
                    return await self._open_new_position(analysis)
                return False

            # 2. 레버리지가 다른 경우 - 청산 후 새 진입
            if current_leverage != new_leverage:
                logger.info(f"레버리지 변경 필요 - 청산 후 재진입 ({current_leverage}x -> {new_leverage}x)")
                if await self._close_position(position):  # 청산은 BTC 단위 사용
                    return await self._open_new_position(analysis)  # 새 진입은 퍼센트 단위 사용
                return False

            # 3. 같은 방향, 같은 레버리지인 경우 - 크기 차이만큼만 조정
            if current_size != target_size:
                # balance_service를 사용하여 잔고 조회
                balance_info = await self.balance_service.get_balance()
                if not balance_info:
                    logger.error("잔고 조회 실패")
                    return False
                
                available_balance = balance_info['currencies']['USDT']['available_balance']
                position_value = available_balance * (target_size / 100) * current_leverage
                target_btc_size = position_value / float(position['entry_price'])
                target_btc_size = round(target_btc_size, 3)  # 소수점 3자리로 반올림
                
                size_diff = target_btc_size - current_size
                size_diff = round(size_diff, 3)  # 차이도 소수점 3자리로 반올림
                
                logger.info(f"""
=== 포지션 크기 조정 ===
잔고: {available_balance} USDT
현재 크기: {current_size} BTC
목표 크기: {target_btc_size} BTC (잔고의 {target_size}%)
차이: {size_diff} BTC
""")
                
                if abs(size_diff) > 0.001:  # 최소 변경 크기
                    order_params = {
                        'symbol': self.symbol,
                        'side': current_side if size_diff > 0 else ('Sell' if current_side == 'Buy' else 'Buy'),
                        'position_size': abs(size_diff),  # 이미 반올림된 값 사용
                        'leverage': current_leverage,
                        'entry_price': float(position['entry_price']),
                        'reduceOnly': size_diff < 0,
                        'is_btc_unit': True
                    }
                    
                    action = "증가" if size_diff > 0 else "감소"
                    logger.info(f"포지션 {action} 주문: {abs(size_diff)} BTC ({order_params['side']})")
                    
                    result = await self.order_service.create_order(**order_params)
                    return result is not None

            return True

        except Exception as e:
            logger.error(f"포지션 처리 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def _close_position(self, position: Dict) -> bool:
        """포지션 청산"""
        try:
            # 롱 포지션은 Sell로 청산, 숏 포지션은 Buy로 청산
            close_side = 'Sell' if position['side'].upper() == 'BUY' else 'Buy'
            
            logger.info(f"포지션 청산 시도: {position['side']} {position['size']} BTC {position['leverage']}x -> {close_side}")
            
            order_params = {
                'symbol': self.symbol,
                'side': close_side,
                'position_size': float(position['size']),
                'leverage': int(position['leverage']),
                'entry_price': float(position['entry_price']),
                'reduceOnly': True,
                'is_btc_unit': True  # 청산은 항상 BTC 단위 사용
            }
            
            result = await self.order_service.create_order(**order_params)
            return result is not None

        except Exception as e:
            logger.error(f"포지션 청산 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def _open_new_position(self, analysis: Dict) -> bool:
        """새 포지션 진입"""
        try:
            strategy = analysis.get('trading_strategy', {})
            order_params = {
                'symbol': self.symbol,
                'side': 'Buy' if strategy['position_suggestion'] == '매수' else 'Sell',
                'position_size': float(strategy['position_size']),  # GPT가 준 퍼센트 값
                'leverage': int(strategy['leverage']),
                'entry_price': float(strategy['entry_points'][0]),
                'stop_loss': float(strategy['stop_loss']),
                'take_profit': float(strategy['take_profit'][0]),
                'is_btc_unit': False  # 퍼센트 단위 사용
            }
            
            logger.info(f"새 포지션 진입 시도: {order_params['side']} {order_params['position_size']}% {order_params['leverage']}x")
            result = await self.order_service.create_order(**order_params)
            return result is not None

        except Exception as e:
            logger.error(f"새 포지션 진입 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False