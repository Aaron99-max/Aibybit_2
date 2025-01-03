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
            logger.info("=== 자동매매 신호 실행 ===")
            
            if not analysis or not isinstance(analysis, dict):
                logger.error("유효하지 않은 분석 데이터")
                return False
            
            strategy = analysis.get('trading_strategy', {})
            if not strategy:
                logger.error("거래 전략 정보 없음")
                return False
            
            # 필수 필드 검증
            required_fields = ['position_suggestion', 'entry_points', 'leverage', 'position_size']
            for field in required_fields:
                if field not in strategy:
                    logger.error(f"필수 필드 누락: {field}")
                    return False

            # 방향 변환
            side = self._convert_side(strategy['position_suggestion'])
            
            # 자동매매 설정 확인
            auto_trading = analysis.get('trading_strategy', {}).get('auto_trading', {})
            if not auto_trading.get('enabled', False):
                return False
            
            # 기본 조건
            confidence = float(auto_trading.get('confidence', 0))
            trend_strength = float(auto_trading.get('strength', 0))
            
            rules = self.auto_trading_rules
            
            # 신뢰도에 따른 최소 추세 강도 결정
            min_strength = rules['trend_strength']['levels']['default']
            if confidence >= 85:
                min_strength = rules['trend_strength']['levels']['confidence_85']
            elif confidence >= 80:
                min_strength = rules['trend_strength']['levels']['confidence_80']
            elif confidence >= 75:
                min_strength = rules['trend_strength']['levels']['confidence_75']
            
            # 신뢰도와 추세 강도 체크
            if confidence < rules['confidence']['min']:
                logger.info(f"신뢰도가 너무 낮음: {confidence}%")
                return False
            
            if trend_strength < min_strength:
                logger.info(f"추세 강도 부족: {trend_strength}% (필요 강도: {min_strength}%, 신뢰도: {confidence}%)")
                return False
            
            logger.info(f"거래 조건 충족 - 추세 강도: {trend_strength}%, 신뢰도: {confidence}%")
            return True

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
            current_side = position['side'].title()
            current_leverage = int(position['leverage'])
            target_percent = float(strategy['position_size'])
            current_size = float(position['size'])  # BTC 단위
            
            # 잔고 조회 (현재 퍼센트 계산용)
            balance = await self.balance_service.get_balance()
            if balance:
                current_percent = (current_size * float(position['entry_price'])) / (balance * float(current_leverage)) * 100
                logger.info(f"\n=== 포지션 조정 시작 ===\n"
                           f"현재: {current_side} {current_size} BTC ({current_percent:.1f}%) {current_leverage}x\n"
                           f"목표: {new_side} {target_percent}% {new_leverage}x\n"
                           f"방향: {'유지' if current_side.upper() == new_side.upper() else '전환'}")
            
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