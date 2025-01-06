import logging
import traceback
from typing import Dict
import json
from config.trading_config import trading_config

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
        self.symbol = trading_config.symbol
        
        # 핵심 거래 제한 설정
        self.MAX_LEVERAGE = trading_config.max_leverage
        self.MAX_POSITION_SIZE = trading_config.max_position_size
        self.MAX_DAILY_LOSS = trading_config.max_daily_loss
        
        # 자동매매 실행 조건
        self.auto_trading_rules = trading_config.auto_trading

        # position_service에 order_service 설정
        self.position_service.set_order_service(order_service)

    def _convert_side(self, side: str) -> str:
        """포지션 방향 통일"""
        side = str(side).upper()
        if side in ['LONG', 'BUY', '매수']:
            return 'Buy'
        elif side in ['SHORT', 'SELL', '매도']:
            return 'Sell'
        else:
            raise ValueError(f"잘못된 포지션 방향: {side}")

    async def execute_trade_signal(self, analysis: Dict) -> bool:
        """거래 신호 실행"""
        try:
            strategy = analysis.get('trading_strategy', analysis)
            
            # 필요한 모든 필드 매핑
            signal = {
                'side': 'Buy' if strategy['position_suggestion'] == '매수' else 'Sell',
                'size': float(strategy['position_size']),
                'leverage': int(strategy['leverage']),
                'entry_price': float(strategy['entry_points'][0]),
                'symbol': self.symbol
            }
            
            # 현재 포지션 확인
            current_position = await self.position_service.get_current_position()
            
            # 포지션 처리 전 로깅
            logger.info(f"현재 포지션: {current_position}")
            logger.info(f"신규 신호: {signal}")

            # position_service로 전달
            result = await self.position_service.handle_position_for_signal(signal)

            # 결과 로깅
            logger.info(f"포지션 처리 결과: {result}")

            return result

        except Exception as e:
            logger.error(f"거래 신호 실행 중 오류: {str(e)}")
            return False

    async def _handle_existing_position(self, position: Dict, analysis: Dict) -> bool:
        """기존 포지션 처리"""
        try:
            strategy = analysis.get('trading_strategy', {})
            new_side = 'Buy' if strategy['position_suggestion'] == '매수' else 'Sell'
            new_leverage = int(strategy['leverage'])
            current_side = position['side'].title()
            current_leverage = int(position['leverage'])
            target_percent = float(strategy['position_size'])
            current_size = float(position['size'])
            
            # 방향과 레버리지가 같을 때만 크기 조정
            if (current_side.upper() == new_side.upper() and 
                current_leverage == new_leverage):
                
                # 주문 실행 (크기 계산은 order_service에서)
                order_params = {
                    'symbol': self.symbol,
                    'side': new_side,
                    'position_size': target_percent,  # 퍼센트로 전달
                    'leverage': new_leverage,
                    'entry_price': float(position['entry_price']),
                    'is_btc_unit': False
                }
                
                result = await self.order_service.create_order(**order_params)
                if result:
                    logger.info(f"포지션 크기 조정 성공: {target_percent}%")
                return result is not None

            # 방향이나 레버리지가 다르면 청산 후 재진입
            logger.info("포지션 청산 후 재진입 필요")
            if await self._close_position(position):
                return await self._open_new_position(analysis)
            return False

        except Exception as e:
            logger.error(f"포지션 처리 중 오류: {str(e)}")
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
            strategy = analysis
            
            order_params = {
                'symbol': self.symbol,
                'side': 'Buy' if strategy['position_suggestion'] == '매수' else 'Sell',
                'position_size': float(strategy['position_size']),
                'leverage': int(strategy['leverage']),
                'entry_price': float(strategy['entry_points'][0]),
                'stop_loss': float(strategy['stop_loss']),
                'take_profit': float(strategy['take_profit'][0]),
                'is_btc_unit': False
            }
            
            logger.info("=== 새 포지션 진입 시도 ===")
            logger.info(f"전략: {json.dumps(strategy, indent=2)}")
            logger.info(f"주문 파라미터: {json.dumps(order_params, indent=2)}")
            
            result = await self.order_service.create_order(**order_params)
            logger.info(f"주문 생성 결과: {result}")
            
            return result is not None

        except Exception as e:
            logger.error(f"새 포지션 진입 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def execute_auto_trade(self, analysis_result):
        """자동매매 실행"""
        try:
            logger.info("\n=== 자동매매 신호 실행 ===")
            logger.info(f"분석 결과: {json.dumps(analysis_result, indent=2)}")
            
            # 1. 자동매매 조건 검증
            auto_trading = analysis_result.get('trading_strategy', {}).get('auto_trading', {})
            confidence = auto_trading.get('confidence', 0)
            strength = auto_trading.get('strength', 0)
            
            # 신뢰도와 추세 강도 체크
            if strength < self.trading_config.auto_trading['trend_strength']['min']:
                logger.info(f"추세 강도 부족: {strength}% (필요 강도: {self.trading_config.auto_trading['trend_strength']['min']}%, 신뢰도: {confidence}%)")
                return False
            
            # 2. /trade 방식과 동일하게 처리
            if 'trading_strategy' not in analysis_result:
                analysis_result['trading_strategy'] = {}
            if 'auto_trading' not in analysis_result['trading_strategy']:
                analysis_result['trading_strategy']['auto_trading'] = {}
            
            analysis_result['trading_strategy']['auto_trading'].update({
                'enabled': True,
                'confidence': confidence,
                'strength': strength,
                'reason': '자동매매 실행'
            })

            # 3. 거래 실행 (/trade와 동일한 경로)
            return await self.execute_trade_signal(analysis_result['trading_strategy'])
            
        except Exception as e:
            logger.error(f"자동매매 실행 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def execute_trading_strategy(self, trading_strategy: Dict) -> bool:
        try:
            logger.info(f"=== 새 포지션 진입 시도 ===")
            logger.info(f"전략: {json.dumps(trading_strategy, indent=2, ensure_ascii=False)}")
            
            # position_suggestion을 side로 변환
            signal = {
                'side': 'Buy' if trading_strategy['position_suggestion'] == '매수' else 'Sell',
                'leverage': trading_strategy['leverage'],
                'size': trading_strategy['position_size'],
                'entry_price': trading_strategy['entry_points'][0],
                'symbol': self.symbol
            }
            
            result = await self.position_service.handle_position_for_signal(signal)
            
            logger.info(f"주문 생성 결과: {result}")
            return result

        except Exception as e:
            logger.error(f"포지션 진입 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return False