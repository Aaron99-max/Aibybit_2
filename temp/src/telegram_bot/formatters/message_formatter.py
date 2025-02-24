import logging
from typing import Dict, List, Union
from decimal import Decimal
from .base_formatter import BaseFormatter
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class MessageFormatter(BaseFormatter):
    """메시지 포맷팅을 위한 클래스"""

    # 이모지 매핑
    EMOJIS = {
        'bot': '🤖',
        'balance': '💰',
        'position': '📊',
        'usdt': '📈',
        'btc': '₿',
        'analysis': '📊',
        'help': '❓',
        'settings': '⚙️',
        'error': '❌',
        'success': '✅',
        'warning': '⚠️',
        'bullish': '🟢',
        'bearish': '🔴',
        'neutral': '⚪'
    }

    # 메시지 템플릿
    TEMPLATES = {
        'balance_header': "{emoji} 계정 잔고\n\n",
        'usdt_balance': "{emoji} USDT:\n- 총 자산: ${total:,.2f}\n- 사용 중: ${used:,.2f}\n- 사용 가능: ${free:,.2f}\n\n",
        'btc_balance': "{emoji} BTC:\n- 총 자산: {total:.8f}\n- 사용 중: {used:.8f}\n- 사용 가능: {free:.8f}",
        'position_header': "{emoji} 현재 포지션\n\n",
        'no_position': "현재 열린 포지션이 없습니다.",
        'help_header': "{emoji} 바이빗 트레이딩 봇 명령어 안내\n\n",
        'error_format': "{emoji} {message}"
    }

    def __init__(self):
        """초기화 메서드"""
        self.translations = {
            # Trading signals
            "BUY": "매수",
            "SELL": "매도",
            "HOLD": "관망",
            # Status
            "RUNNING": "실행 중",
            "STOPPED": "중지됨",
            # Risk levels
            "HIGH": "높음",
            "MEDIUM": "중간",
            "LOW": "낮음",
            # Market trends
            "BULLISH": "상승",
            "BEARISH": "하락",
            "NEUTRAL": "횡보",
            # Market phases
            "UPTREND": "상승",
            "DOWNTREND": "하락",
            "SIDEWAYS": "횡보",
            # Sentiments
            "POSITIVE": "긍정적",
            "NEGATIVE": "부정적",
            "NEUTRAL": "중립"
        }

    def validate_balance_data(self, balance_data: Dict) -> bool:
        """잔고 데이터 검증"""
        try:
            if not isinstance(balance_data, dict):
                logger.error(f"잘못된 balance_data 타입: {type(balance_data)}")
                return False

            required_fields = {'timestamp', 'currencies'}
            missing_fields = [field for field in required_fields if field not in balance_data]
            
            if missing_fields:
                logger.error(f"필수 필드 누락: {missing_fields}")
                return False

            currencies = balance_data.get('currencies', {})
            if not currencies:
                logger.error("통화 정보가 없습니다")
                return False

            for currency, data in currencies.items():
                required_currency_fields = {'total_equity', 'used_margin', 'available_balance'}
                missing_currency_fields = [field for field in required_currency_fields if field not in data]
                
                if missing_currency_fields:
                    logger.error(f"{currency} 통화의 필수 필드 누락: {missing_currency_fields}")
                    return False

            return True
        except Exception as e:
            logger.error(f"잔고 데이터 검증 중 오류: {str(e)}")
            return False

    def validate_position_data(self, position: Dict) -> bool:
        """포지션 데이터 유효성 검사"""
        try:
            required_fields = ['side', 'size', 'entry_price', 'leverage']
            return all(position.get(field) is not None for field in required_fields)
        except Exception as e:
            logger.error(f"포지션 데이터 검증 실패: {str(e)}")
            return False

    def format_number(self, number: Union[str, float, int], decimals: int = 2) -> str:
        """숫자 포맷팅

        Args:
            number: 포맷팅할 숫자
            decimals (int): 소수점 자리수

        Returns:
            str: 포맷팅된 숫자 문자열
        """
        try:
            if isinstance(number, str):
                number = number.replace(',', '')
            number_decimal = Decimal(str(number))
            format_str = f"{{:,.{decimals}f}}"
            return format_str.format(float(number_decimal))
        except (ValueError, TypeError, decimal.InvalidOperation):
            logger.error(f"숫자 포맷팅 실패: {number}")
            return "-"

    def get_side_emoji(self, side: str) -> str:
        """포지션 방향에 따른 이모지 반환

        Args:
            side (str): 포지션 방향

        Returns:
            str: 해당하는 이모지
        """
        side = side.upper()
        if side == 'BUY':
            return self.EMOJIS['bullish']
        elif side == 'SELL':
            return self.EMOJIS['bearish']
        return self.EMOJIS['neutral']

    def format_status(self, market_data: Dict, bot_status: Dict) -> str:
        """상태 정보 포맷팅"""
        try:
            last_price = float(market_data.get('last_price', 0))
            bid = float(market_data.get('bid', 0))
            ask = float(market_data.get('ask', 0))
            
            auto_analyzer = "✅ 실행 중" if bot_status.get('auto_analyzer') else "❌ 중지됨"
            profit_monitor = "✅ 실행 중" if bot_status.get('profit_monitor') else "❌ 중지됨"
            
            return f"""
📊 시스템 상태

💹 시장 정보 (BTCUSDT):
• 현재가: ${last_price:,.2f}
• 매수호가: ${bid:,.2f}
• 매도호가: ${ask:,.2f}

🤖 봇 상태:
• 자동 분석: {auto_analyzer}
• 수익 모니터링: {profit_monitor}
"""
        except Exception as e:
            logger.error(f"상태 포맷팅 중 오류: {str(e)}")
            return "❌ 상태 정보 포맷팅 실패"

    def format_balance(self, balance: Dict) -> str:
        """잔고 정보 포맷팅"""
        try:
            currencies = balance.get('currencies', {})
            
            # USDT 잔고
            usdt = currencies.get('USDT', {})
            usdt_total = float(usdt.get('total_equity', 0))
            usdt_used = float(usdt.get('used_margin', 0))
            usdt_free = float(usdt.get('available_balance', 0))
            
            # BTC 잔고
            btc = currencies.get('BTC', {})
            btc_total = float(btc.get('total_equity', 0))
            btc_used = float(btc.get('used_margin', 0))
            btc_free = float(btc.get('available_balance', 0))
            
            message = f"""
💰 계정 잔고 정보

USDT:
• 총 자산: ${usdt_total:,.2f}
• 사용 중: ${usdt_used:,.2f}
• 사용 가능: ${usdt_free:,.2f}

BTC:
• 총 자산: {btc_total:.8f}
• 사용 중: {btc_used:.8f}
• 사용 가능: {btc_free:.8f}
"""
            return message
            
        except Exception as e:
            logger.error(f"잔고 포맷팅 중 오류: {str(e)}")
            return "❌ 잔고 정보 포맷팅 실패"

    def format_position(self, position: Dict) -> str:
        """포지션 정보 포맷팅"""
        if not position:
            return "📊 현재 활성화된 포지션이 없습니다."
            
        return f"""
💼 현재 포지션 정보:

• 볼: {position.get('symbol', 'N/A')}
• 방향: {position.get('side', 'N/A')}
• 크기: {position.get('size', position.get('contracts', 'N/A'))}
• 레버리지: {position.get('leverage', 'N/A')}x
• 진입가: ${float(position.get('entryPrice', 0)):,.2f}
• 마크가격: ${float(position.get('markPrice', 0)):,.2f}
• 미실현 손익: ${float(position.get('unrealizedPnl', 0)):,.2f}
"""

    def translate(self, text: str) -> str:
        """영어 텍스트를 한글로 변환

        Args:
            text (str): 변환할 텍스트

        Returns:
            str: 변환된 텍스트
        """
        if not text:
            return "-"
        return self.translations.get(text.upper(), text)

    @staticmethod
    def format_help() -> str:
        """도움말 메시지 포맷팅

        Returns:
            str: 포맷팅된 도움말 메시지
        """
        return (
            f"{MessageFormatter.EMOJIS['help']} 바이빗 트레이딩 봇 명령어 안내\n\n"
            f"{MessageFormatter.EMOJIS['analysis']} 분석 명령어:\n"
            "/analyze [timeframe] - 시장 분석 실행\n"
            "  - 15m, 1h, 4h, 1d, all\n"
            "/last [timeframe] - 마지막 분석 결과 확인\n"
            "  - timeframe 생략시 전체 결과 표시\n\n"
            f"{MessageFormatter.EMOJIS['balance']} 거래 정보:\n"
            "/status - 현재 시장 상태\n"
            "/balance - 계정 잔고\n"
            "/position - 현재 포지션\n\n"
            f"{MessageFormatter.EMOJIS['settings']} 기타 명령어:\n"
            "/help - 도움말\n"
            "/stop - 봇 종료"
        )

    @staticmethod
    def format_timeframe_help(cmd: str) -> str:
        """시간프레임 도움말 포맷팅

        Args:
            cmd (str): 명령어

        Returns:
            str: 포맷팅된 시간프레임 도움말
        """
        return (
            f"{MessageFormatter.EMOJIS['help']} 시간프레임을 지정해주세요:\n"
            f"/{cmd} 15m - 15분봉 분석\n"
            f"/{cmd} 1h - 1시간봉 분석\n"
            f"/{cmd} 4h - 4시간봉 분석\n"
            f"/{cmd} 1d - 일봉 분석\n"
            f"/{cmd} final - 자동매매 신호\n"
            f"/{cmd} all - 전체 분석"
        )

    def format_trade_execution(self, order: Dict, analysis: Dict) -> str:
        try:
            message = f"""
🎯 자동매매 실행

📊 거래 정보:
• 방향: {'매수' if order['side'] == 'buy' else '매도'}
• 진입가: {order['price']}
• 수량: {order['amount']}
• 레버리지: {order.get('leverage', '미설정')}x

💰 리스크 관리:
• 절가: {order.get('stopLoss', '미설정')}
• 목표가: {order.get('takeProfit', '미설정')}
• 예상 손실: {abs((order.get('stopLoss', order['price']) - order['price']) / order['price'] * 100):.2f}%
• 예상 수익: {abs((order.get('takeProfit', order['price']) - order['price']) / order['price'] * 100):.2f}%

📈 분석 근거:
• 시장 단계: {analysis['market_summary']['market_phase']}
• 신뢰도: {analysis['market_summary']['confidence']}%
• 추세 강도: {analysis['technical_analysis']['strength']}%
• RSI: {analysis['technical_analysis']['indicators']['rsi_signal']}
• MACD: {analysis['technical_analysis']['indicators']['macd_signal']}
"""
            return message
            
        except Exception as e:
            logger.error(f"거래 실행 메시지 포맷팅 중 오류: {str(e)}")
            return "거래 실행 메시지 포맷팅 실패"

    def format_position_message(self, positions: List[Dict]) -> str:
        """포지션 정보 포맷팅"""
        try:
            if not positions:
                return "📊 활성화된 포지션이 없습니다."
            
            messages = ["📊 현재 포지션 상태"]
            for pos in positions:
                side = "롱" if pos['side'].upper() == 'BUY' else "숏"
                size = float(pos['size'])
                entry_price = float(pos['entry_price'])
                leverage = pos['leverage']
                unrealized_pnl = float(pos.get('unrealized_pnl', 0))
                
                message = f"""
• {pos['symbol']} {side} x{leverage}
  크기: {size:.3f} BTC
  진입가: ${entry_price:,.2f}
  미실현 손익: ${unrealized_pnl:,.2f}
"""
                messages.append(message)
            
            return "\n".join(messages)
            
        except Exception as e:
            logger.error(f"포지션 메시지 포맷팅 중 오류: {str(e)}")
            return "포지션 정보 조회 중 오류가 발생했습니다."

    def format_analysis_message(self, analysis: Dict, timeframe: str) -> str:
        """분석 결과 포맷팅"""
        try:
            # 시간 포맷팅
            timestamp = analysis.get('timestamp', '')
            if timestamp:
                dt = datetime.fromtimestamp(timestamp / 1000)
                kst_time = dt.astimezone(timezone('Asia/Seoul'))
                time_str = kst_time.strftime('%Y-%m-%d %H:%M:%S %Z')
            else:
                time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')

            # 자동매매 상태 확인 (4시간봉만 자동매매 대상)
            auto_trading = {
                'status': '활성화' if timeframe == '4h' else '비활성화',
                'reason': '4시간봉만 자동매매 대상' if timeframe != '4h' else ''
            }

            message = f"""
📊 {timeframe} 분석 ({time_str})

🌍 시장 요약:
• 시장 단계: {analysis['market_summary']['market_phase']}
...
🤖 자동매매:
• 상태: {auto_trading['status']}
• 사유: {auto_trading['reason']}
"""
            return message

        except Exception as e:
            logger.error(f"분석 메시지 포맷팅 중 오류: {str(e)}")
            return "분석 결과 포맷팅 실패"