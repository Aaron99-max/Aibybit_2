import logging
import traceback
from typing import Dict, TYPE_CHECKING
from config.trading_config import trading_config

if TYPE_CHECKING:
    from services.order_service import OrderService

logger = logging.getLogger('trade_manager')

class TradeManager:
    def __init__(self, order_service: 'OrderService'):
        self.order_service = order_service
        self.symbol = trading_config.symbol

    async def execute_trade(self, analysis: Dict) -> bool:
        """분석 결과에 따른 매매 실행"""
        try:
            if not analysis or 'trading_signals' not in analysis:
                logger.error("매매 신호 없음")
                return False
                
            signals = analysis['trading_signals']
            
            # 자동매매 활성화 여부 체크
            if not trading_config.auto_trading['enabled']:
                logger.info("자동매매 기능이 비활성화 상태입니다")
                return False
                
            # 신뢰도 체크
            confidence = analysis.get('market_summary', {}).get('confidence', 0)
            if confidence < trading_config.min_confidence:
                logger.info(f"신뢰도 부족 (현재: {confidence}%, 최소: {trading_config.min_confidence}%)")
                return False
            
            # 주문 파라미터 설정
            order_params = {
                'symbol': 'BTCUSDT',
                'side': 'Buy' if signals['position_suggestion'] == 'BUY' else 'Sell',
                'position_size': signals['position_size'],
                'leverage': signals['leverage'],
                'entry_price': signals['entry_price'],
                'stop_loss': signals['stop_loss'],
                'take_profit': signals['take_profit1'],  # take_profit1을 take_profit으로 매핑
                'take_profit2': signals.get('take_profit2')  # 옵션
            }
            
            # 주문 실행
            result = await self.order_service.place_order(order_params)
            return result
                
        except Exception as e:
            logger.error(f"매매 실행 중 오류: {str(e)}")
            return False

    def _should_execute_trade(self, analysis: Dict) -> bool:
        """자동매매 실행 여부 결정"""
        try:
            signals = analysis.get('trading_signals', {})
            
            # HOLD 체크
            if signals.get('position_suggestion') == 'HOLD':
                logger.info("관망 신호")
                return False
                
            # 자동매매 활성화 체크
            if not trading_config.auto_trading['enabled']:
                logger.info("자동매매 기능이 비활성화 상태입니다")
                return False

            # 신뢰도 체크
            confidence = analysis.get('market_summary', {}).get('confidence', 0)
            if confidence < trading_config.min_confidence:
                logger.info(f"신뢰도 부족 (현재: {confidence}%, 최소: {trading_config.min_confidence}%)")
                return False

            return True
            
        except Exception as e:
            logger.error(f"자동매매 조건 체크 중 오류: {str(e)}")
            return False
