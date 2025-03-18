from typing import Dict, List, Optional, Union
import logging
from decimal import Decimal, InvalidOperation
import json
from .base_formatter import BaseFormatter
from ..utils.time_utils import TimeUtils
from datetime import datetime
import pytz
import traceback

logger = logging.getLogger(__name__)

class AnalysisFormatter(BaseFormatter):
    """분석 결과 포맷팅을 위한 클래스"""

    # 이모지 매핑
    EMOJIS = {
        'analysis': '📊',
        'market': '🌍',
        'technical': '📈',
        'strategy': '💡',
        'error': '❌',
        'bullish': '🟢',
        'bearish': '🔴',
        'neutral': '⚪',
        'divergence': '🔄',
        'volume_up': '📈',
        'volume_down': '📉',
        'volume_neutral': '➖'
    }

    def __init__(self):
        """초기화 메서드"""
        self.time_utils = TimeUtils()
        self.translations = {
            # Market phases
            "BULLISH": "상승",
            "BEARISH": "하락",
            # Sentiments
            "POSITIVE": "긍정적",
            "NEGATIVE": "부정적",
            # Volume
            "VOLUME_INCREASE": "거래량 증가",
            "VOLUME_DECREASE": "거래량 감소",
            "VOLUME_NEUTRAL": "거래량 보통",
            # RSI signals
            "OVERBOUGHT": "과매수",
            "OVERSOLD": "과매도",
            "NEUTRAL": "중립",
            # Trading signals
            "BUY": "매수",
            "SELL": "매도",
            "HOLD": "관망"
        }

    def validate_analysis_data(self, analysis_result: Dict) -> bool:
        """분석 데이터 유효성 검사

        Args:
            analysis_result (Dict): 검증할 분석 결과 데이터

        Returns:
            bool: 유효성 검사 통과 여부
        """
        try:
            required_keys = ['market_summary', 'technical_analysis']
            if not all(key in analysis_result for key in required_keys):
                logger.error(f"필수 키 누락: {required_keys}")
                return False

            market_summary = analysis_result.get('market_summary', {})
            if not isinstance(market_summary, dict):
                logger.error("market_summary가 딕셔너리가 아님")
                return False

            technical_analysis = analysis_result.get('technical_analysis', {})
            if not isinstance(technical_analysis, dict):
                logger.error("technical_analysis가 딕셔너리가 아님")
                return False

            return True
        except Exception as e:
            logger.error(f"분석 데이터 검증 중 오류 발생: {str(e)}")
            return False

    def format_price(self, price: Union[str, float, int, None]) -> str:
        """가격 포맷팅

        Args:
            price: 포맷팅할 가격

        Returns:
            str: 포맷팅된 가격 문자열
        """
        try:
            if price is None:
                return '-'
            if isinstance(price, str):
                price = price.replace('$', '').replace(',', '')
            price_decimal = Decimal(str(price))
            return f"${price_decimal:,.2f}"
        except (ValueError, TypeError, InvalidOperation):
            logger.error(f"가격 포맷팅 실패: {price}")
            return '-'

    def get_market_emoji(self, phase: str) -> str:
        """시장 상태에 따른 이모지 반환

        Args:
            phase (str): 시장 상태

        Returns:
            str: 해당하는 이모지
        """
        phase = phase.upper()
        if phase == 'BULLISH':
            return self.EMOJIS['bullish']
        elif phase == 'BEARISH':
            return self.EMOJIS['bearish']
        return self.EMOJIS['neutral']

    def get_volume_emoji(self, volume: str) -> str:
        """거래량 상태에 따른 이모지 반환

        Args:
            volume (str): 거래량 상태

        Returns:
            str: 해당하는 이모지
        """
        volume = volume.upper()
        if 'INCREASE' in volume:
            return self.EMOJIS['volume_up']
        elif 'DECREASE' in volume:
            return self.EMOJIS['volume_down']
        return self.EMOJIS['volume_neutral']

    def format_analysis(self, analysis_result: Dict, auto_trading_status: str = None) -> str:
        """분석 결과 포맷팅"""
        try:
            if not analysis_result:
                return "❌ 분석 결과 없음"

            market = analysis_result.get('market_summary', {})
            technical = analysis_result.get('technical_analysis', {})
            signals = analysis_result.get('trading_signals', {})

            # 현재 시간을 KST로 변환
            kst = pytz.timezone('Asia/Seoul')
            current_time = datetime.now(kst).strftime('%Y-%m-%d %H:%M:%S KST')

            # 포지션 방향 결정
            position = signals.get('position_suggestion', '관망')
            position_side = '숏' if position.upper() == 'SELL' else '롱' if position.upper() == 'BUY' else '관망'
            position_emoji = "🔴" if position.upper() == "SELL" else "🟢" if position.upper() == "BUY" else "⚪"

            lines = [
                f"📊 1h 분석 ({current_time})\n",
                
                # 자동매매 상태
                f"⚙️ {auto_trading_status}\n" if auto_trading_status else "",
                
                "🌍 시장 요약:",
                f"• 시장 단계: {self.translate(market.get('market_phase', '-'))}",
                f"• 전반적 심리: {self.translate(market.get('overall_sentiment', '-'))}",
                f"• 단기 심리: {self.translate(market.get('short_sentiment', '-'))}",
                f"• 거래량: {self.translate(market.get('volume_status', '-'))}",
                f"• 리스크: {self.translate(market.get('risk_level', '-'))}",
                f"• 신뢰도: {market.get('confidence', 0)}%\n",

                "📈 기술적 분석:",
                f"• 추세: {self.translate(technical.get('trend', '-'))}",
                f"• 강도: {technical.get('strength', 0)}",
                f"• RSI: {technical.get('indicators', {}).get('rsi', 0):.2f}",
                f"• MACD: {technical.get('indicators', {}).get('macd', '-')}",
                f"• 볼린저밴드: {technical.get('indicators', {}).get('bollinger', '-')}",
                f"• 다이버전스: {technical.get('divergence', {}).get('type', '없음')}",
                f"• 설명: {technical.get('divergence', {}).get('description', '현재 다이버전스 없음')}\n",

                "💡 매매 신호:",
                f"• 포지션: {position_emoji} {position_side}",
                f"• 진입가: ${float(signals.get('entry_price', 0)):,.1f}",
                f"• 손절가: ${float(signals.get('stop_loss', 0)):,.1f}",
                f"• 목표가: ${float(signals.get('take_profit1', 0)):,.1f}, ${float(signals.get('take_profit2', 0)):,.1f}",
                f"• 레버리지: {signals.get('leverage', 1)}x",
                f"• 포지션 크기: {signals.get('position_size', 10)}%",
                f"• 사유: {signals.get('reason', '알 수 없음')}"
            ]

            return "\n".join(line for line in lines if line)

        except Exception as e:
            logger.error(f"분석 결과 포맷팅 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return "❌ 분석 결과 포맷팅 실패"

    def format_balance(self, balance_data: Dict) -> str:
        """잔고 정보를 포맷팅"""
        try:
            if not isinstance(balance_data, dict):
                logger.error(f"잘못된 balance_data 타입: {type(balance_data)}")
                return "잔고 데이터 형식 오류"

            total_equity = balance_data.get('total_equity', 0)
            available_balance = balance_data.get('available_balance', 0)
            used_margin = balance_data.get('used_margin', 0)

            return (
                f"💰 계좌 정보\n"
                f"총자산: ${total_equity:,.2f}\n"
                f"가용잔고: ${available_balance:,.2f}\n"
                f"사용중인 증거금: ${used_margin:,.2f}"
            )
        except Exception as e:
            logger.error(f"잔고 포맷팅 중 오류: {str(e)}")
            return "잔고 포맷팅 오류"

    def format_position(self, position_data: Dict) -> str:
        """포지션 정보를 포맷팅"""
        try:
            if not isinstance(position_data, dict):
                logger.error(f"잘못된 position_data 타입: {type(position_data)}")
                return "포지션 데이터 형식 오류"

            symbol = position_data.get('symbol', '')
            side = position_data.get('side', '')
            size = position_data.get('size', 0)
            entry_price = position_data.get('entry_price', 0)
            leverage = position_data.get('leverage', 1)
            unrealized_pnl = position_data.get('unrealized_pnl', 0)
            
            position_emoji = "🔴" if side.lower() == "sell" else "🟢"
            
            return (
                f"{position_emoji} {symbol} 포지션\n"
                f"방향: {side}\n"
                f"크기: {size}\n"
                f"진입가: ${entry_price:,.2f}\n"
                f"레버리지: {leverage}x\n"
                f"미실현 수익: ${unrealized_pnl:,.2f}"
            )
        except Exception as e:
            logger.error(f"포지션 포맷팅 중 오류: {str(e)}")
            return "포지션 포맷팅 오류"

    def format_status(self, status_data: Dict) -> str:
        """상태 정보를 포맷팅"""
        try:
            if not isinstance(status_data, dict):
                logger.error(f"잘못된 status_data 타입: {type(status_data)}")
                return "상태 데이터 형식 오류"

            mode = status_data.get('mode', 'unknown')
            last_update = status_data.get('last_update', '')
            error = status_data.get('error', '')

            status_text = (
                f"📊 시스템 상태\n"
                f"모드: {mode}\n"
                f"마지막 업데이트: {last_update}"
            )

            if error:
                status_text += f"\n⚠️ 오류: {error}"

            return status_text

        except Exception as e:
            logger.error(f"상태 포맷팅 중 오류: {str(e)}")
            return "상태 포맷팅 오류"

    def translate(self, text: str) -> str:
        """번역 처리"""
        translations = {
            # Trading signals
            "position_suggestion": "포지션",
            "BUY": "매수",
            "SELL": "매도",
            "HOLD": "관망",
            
            # Market phase & trends
            "SIDEWAYS": "횡보",
            "UPTREND": "상승",
            "DOWNTREND": "하락",
            
            # Sentiment
            "NEUTRAL": "중립",
            "POSITIVE": "긍정",
            "NEGATIVE": "부정",
            
            # Volume
            "VOLUME_INCREASE": "거래량 증가",
            "VOLUME_DECREASE": "거래량 감소",
            "VOLUME_NEUTRAL": "거래량 보통",
            
            # Risk
            "HIGH": "높음",
            "MEDIUM": "보통",
            "LOW": "낮음",
            
            # Technical indicators
            "STRONG_BULLISH": "매우 강세",
            "BULLISH": "강세",
            "STRONG_BEARISH": "매우 약세",
            "BEARISH": "약세",
            "OVERBOUGHT": "과매수",
            "OVERSOLD": "과매도",
            
            # Bollinger Bands
            "UPPER_BREAK": "상단 돌파",
            "LOWER_BREAK": "하단 돌파",
            "ABOVE_MIDDLE": "중앙선 위",
            "BELOW_MIDDLE": "중앙선 아래",
            
            # ... 기존 코드 ...
        }
        return translations.get(text, text)

    def _translate_macd(self, macd_signal: str) -> str:
        """MACD 신호 번역"""
        translations = {
            'STRONG_BULLISH': '매우 강한 상승',
            'BULLISH': '상승',
            'NEUTRAL': '중립',
            'BEARISH': '하락',
            'STRONG_BEARISH': '매우 강한 하락'
        }
        return translations.get(macd_signal, macd_signal)

    def _translate_bollinger(self, bb_signal: str) -> str:
        """볼린저밴드 신호 번역"""
        translations = {
            'ABOVE_UPPER': '상단 돌파',
            'ABOVE_MIDDLE': '중앙선 상향',
            'BELOW_MIDDLE': '중앙선 하향',
            'BELOW_LOWER': '하단 돌파',
            'MIDDLE': '중앙'
        }
        return translations.get(bb_signal, bb_signal)