from typing import Dict, List, Optional, Union
import logging
from decimal import Decimal
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
        except (ValueError, TypeError, decimal.InvalidOperation):
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

    def format_market_summary(self, market: Dict) -> str:
        """시장 요약 정보 포맷팅

        Args:
            market (Dict): 시장 요약 데이터

        Returns:
            str: 포맷팅된 시장 요약 문자열
        """
        message = f"{self.EMOJIS['market']} 시장 요약:\n"
        
        market_phase = market.get('market_phase', '-')
        message += f"• 시장 단계: {self.translate(market_phase)}\n"
        
        if 'overall_sentiment' in market:
            message += f"• 전반적 심리: {self.translate(market.get('overall_sentiment', '-'))}\n"
        message += f"• 단기 심리: {self.translate(market.get('short_term_sentiment', '-'))}\n"
        
        volume = market.get('volume_analysis', market.get('volume_trend', '-'))
        message += f"• 거래량: {self.translate(volume)}\n"
        
        if 'risk_level' in market:
            message += f"• 리스크: {self.translate(market.get('risk_level', '-'))}\n"
        
        confidence = market.get('confidence')
        if isinstance(confidence, (int, float)):
            message += f"• 신뢰도: {confidence:.1f}%\n"
        
        return message

    def format_technical_analysis(self, ta: Dict, timeframe: str = None) -> str:
        """기술적 분석 결과 포맷팅"""
        message = f"{self.EMOJIS['technical']} 기술적 분석:\n"
        
        trend = ta.get('trend', '-')
        message += f"• 추세: {self.translate(trend)}\n"
        message += f"• 강도: {ta.get('strength', '-')}\n"
        
        # indicators 섹션
        indicators = ta.get('indicators', {})
        if indicators:
            message += f"• RSI: {indicators.get('rsi', '-')}\n"
            message += f"• MACD: {indicators.get('macd', '-')}\n"
            message += f"• 볼린저: {indicators.get('bollinger', '-')}\n"
            
            # final이 아닐 때만 다이버전스 정보 포함
            if timeframe != 'final' and 'divergence' in indicators:
                divergence = indicators['divergence']
                if divergence.get('type') != '없음':
                    message += f"\n🔄 다이버전스:\n"
                    message += f"• 유형: {divergence.get('type')}\n"
                    message += f"• 설명: {divergence.get('description')}\n"
        
        return message

    def format_trading_strategy(self, trading: Dict) -> str:
        """거래 전략 포맷팅

        Args:
            trading (Dict): 거래 전략 데이터

        Returns:
            str: 포맷팅된 거래 전략 문자열
        """
        if not trading:
            return ""
            
        message = f"{self.EMOJIS['strategy']} 거래 전략:\n"
        
        # 자동매매 상태 표시
        auto_trading = trading.get('auto_trading_enabled', False)
        message += f"• 자동매매: {'활성화' if auto_trading else '비활성화'}\n"
        
        position = trading.get('position_suggestion', '-')
        message += f"• 포지션: {self.translate(position)}\n"
        
        # 현재가 표시
        current_price = trading.get('current_price')
        if current_price:
            message += f"• 현재가: {self.format_price(current_price)}\n"
        
        # HOLD가 아닐 때만 진입가 표시
        if position.upper() != 'HOLD':
            entry_points = trading.get('entry_points', [])
            if entry_points and len(entry_points) > 0:
                message += f"• 진입가: {self.format_price(entry_points[0])}\n"
            
            stop = trading.get('stop_loss')
            if stop:
                message += f"• 손절가: {self.format_price(stop)}\n"
            
            targets = trading.get('take_profit', [])
            if targets:
                formatted_targets = [self.format_price(price) for price in targets]
                message += f"• 목표가: {', '.join(formatted_targets)}\n"
        else:
            # HOLD일 때 이유나 조건 설명 추가
            reason = trading.get('hold_reason', '시장 상황이 불안정하여 관망 추천')
            message += f"• 사유: {reason}\n"
            
            # 다음 진입 조건이 있다면 표시
            entry_condition = trading.get('entry_condition')
            if entry_condition:
                message += f"• 진입 조건: {entry_condition}\n"
        
        leverage = trading.get('leverage')
        if leverage:
            message += f"• 레버리지: {leverage}x\n"
        
        position_size = trading.get('position_size')
        if position_size:
            message += f"• 포지션 크기: {position_size}%\n"
        
        return message

    def format_analysis(self, analysis: Dict, analysis_type: str = 'final') -> str:
        """분석 결과 포맷팅"""
        try:
            # 시간대별 제목 설정
            title_map = {
                '15m': '15분봉',
                '1h': '1시간봉',
                '4h': '4시간봉',
                '1d': '일봉',
                'final': '최종'
            }
            title = f"📊 {title_map.get(analysis_type, '기타')} 분석"
            
            # 저장 시간
            saved_at = analysis.get('saved_at', datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"))
            
            # 메시지 구성
            message = [
                f"{title} ({saved_at})\n",
                self._format_market_summary(analysis),
                self._format_technical_analysis(analysis),
                self._format_trading_signals(analysis)
            ]
            
            return "\n".join(filter(None, message))
            
        except Exception as e:
            logger.error(f"분석 결과 포맷팅 중 오류: {str(e)}")
            return "❌ 포맷팅 오류"

    def format_final_analysis(self, analysis: Dict) -> str:
        """Final 분석 결과 포맷팅"""
        return self.format_analysis(analysis, "Final")

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

    def format_analysis_result(self, analysis: Dict, timeframe: str) -> str:
        """분석 결과 포맷팅"""
        try:
            if not analysis:
                return "❌ 분석 결과가 없습니다."

            # 저장된 시간 사용
            time_str = analysis.get('saved_at', 
                datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S KST')
            )

            message = [
                f"📊 {timeframe} 분석 ({time_str})\n",
                
                "🌍 시장 요약:",
                f"• 시장 단계: {self.translate(analysis.get('market_summary', {}).get('market_phase', '알 수 없음'))}",
                f"• 전반적 심리: {self.translate(analysis.get('market_summary', {}).get('sentiment', '알 수 없음'))}",
                f"• 단기 심리: {self.translate(analysis.get('market_summary', {}).get('short_term', '알 수 없음'))}",
                f"• 거래량: {self.translate(analysis.get('market_summary', {}).get('volume', '보통'))}",
                f"• 리스크: {self.translate(analysis.get('market_summary', {}).get('risk', '보통'))}",
                f"• 신뢰도: {analysis.get('market_summary', {}).get('confidence', 0)}%\n",

                "📈 기술적 분석:",
                f"• 추세: {self.translate(analysis.get('technical_analysis', {}).get('trend', '알 수 없음'))}",
                f"• 강도: {analysis.get('technical_analysis', {}).get('strength', 0):.1f}",
                f"• RSI: {analysis.get('technical_analysis', {}).get('indicators', {}).get('rsi', 0):.2f}",
                f"• MACD: {self._translate_macd(analysis.get('technical_analysis', {}).get('indicators', {}).get('macd', 'NEUTRAL'))}",
                f"• 볼린저밴드: {self._translate_bollinger(analysis.get('technical_analysis', {}).get('indicators', {}).get('bollinger', 'MIDDLE'))}",
                f"• 다이버전스: {analysis.get('technical_analysis', {}).get('indicators', {}).get('divergence_type', '없음')}",
                f"• 설명: {analysis.get('technical_analysis', {}).get('indicators', {}).get('divergence_desc', '정보 없음')}\n",

                "⚠️ 주요 알림:" if analysis.get('alerts') else "",
                "\n".join([f"• {alert}" for alert in analysis.get('alerts', [])]) + "\n" if analysis.get('alerts') else "",

                "💡 매매 신호:",
                f"• 포지션: {self.translate(analysis.get('trading_signals', {}).get('position_suggestion', '관망'))}",
                f"• 진입가: ${float(analysis.get('trading_signals', {}).get('entry_price', 0)):,.1f}",
                f"• 손절가: ${float(analysis.get('trading_signals', {}).get('stop_loss', 0)):,.1f}",
                f"• 목표가: ${float(analysis.get('trading_signals', {}).get('take_profit1', 0)):,.1f}, ${float(analysis.get('trading_signals', {}).get('take_profit2', 0)):,.1f}",
                f"• 레버리지: {analysis.get('trading_signals', {}).get('leverage', 1)}x",
                f"• 포지션 크기: {analysis.get('trading_signals', {}).get('size', 10)}%",
                f"• 사유: {analysis.get('trading_signals', {}).get('reason', '알 수 없음')}\n",

                "🤖 자동매매:",
                f"• 상태: {'활성화' if analysis.get('auto_trading', {}).get('enabled', False) else '비활성화'}",
                f"• 사유: {analysis.get('trading_signals', {}).get('reason', '알 수 없음')}"
            ]

            return "\n".join(filter(None, message))

        except Exception as e:
            logger.error(f"분석 결과 포맷팅 중 오류: {str(e)}")
            return "❌ 포맷팅 오류"

    def _format_market_summary(self, analysis: Dict) -> str:
        """시장 요약 포맷팅"""
        try:
            market_summary = analysis.get('market_summary', {})
            if not market_summary:
                return ""
            
            message = [
                "🌍 시장 요약:",
                f"• 현재가: ${market_summary.get('current_price', 0):,.2f}",
                f"• 추세: {self.translate(market_summary.get('trend', '정보 없음'))}",
                f"• 강도: {market_summary.get('strength', 0)}%",
                f"• 신뢰도: {market_summary.get('confidence', 0)}%"
            ]
            
            return "\n".join(message)
            
        except Exception as e:
            logger.error(f"시장 요약 포맷팅 중 오류: {str(e)}")
            return ""

    def _format_technical_analysis(self, analysis: Dict) -> str:
        """기술적 분석 포맷팅"""
        try:
            technical = analysis.get('technical_analysis', {})
            if not technical:
                return ""
            
            message = [
                "\n📈 기술적 분석:",
                f"• RSI: {technical.get('rsi', 0)}",
                f"• MACD: {self._translate_macd(technical.get('macd', 'NEUTRAL'))}",
                f"• 볼린저: {self._translate_bollinger(technical.get('bollinger', 'MIDDLE'))}",
                f"• 다이버전스: {technical.get('divergence_type', '없음')}",
                f"• 설명: {technical.get('divergence_desc', '정보 없음')}"
            ]
            
            return "\n".join(message)
            
        except Exception as e:
            logger.error(f"기술적 분석 포맷팅 중 오류: {str(e)}")
            return ""

    def _format_trading_signals(self, analysis: Dict) -> str:
        """거래 전략 포맷팅"""
        try:
            trading = analysis.get('trading_signals', {})
            if not trading:
                return ""
            
            message = [
                "\n💡 매매 신호:",
                f"• 포지션: {self.translate(trading.get('position_suggestion', '관망'))}",
                f"• 진입가: ${trading.get('entry_price', 0):,.2f}",
                f"• 손절가: ${trading.get('stop_loss', 0):,.2f}",
                f"• 익절가: ${trading.get('take_profit', 0):,.2f}",
                f"• 레버리지: {trading.get('leverage', 1)}x",
                f"• 사유: {trading.get('reason', '정보 없음')}"
            ]
            
            return "\n".join(message)
            
        except Exception as e:
            logger.error(f"매매 신호 포맷팅 중 오류: {str(e)}")
            return ""

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