import numpy as np
import pandas as pd
import logging
from typing import Dict, Any, Optional, List, Tuple
import json
import time
from datetime import datetime
import traceback
from .gpt_client import GPTClient
from collections import Counter
from services.market_data_service import MarketDataService
from indicators.technical import TechnicalIndicators
from telegram_bot.formatters.storage_formatter import StorageFormatter
from config.trading_config import trading_config
from pathlib import Path
from services.trade_store import TradeStore
from .gpt_analysis_store import GPTAnalysisStore

# numpy 경고 무시 설정
np.seterr(divide='ignore', invalid='ignore')

logger = logging.getLogger(__name__)

class GPTAnalyzer:
    def __init__(self, bybit_client=None, market_data_service=None):
        """초기화 메서드"""
        self.support_levels = []
        self.resistance_levels = []
        self.analysis_timeout = 60
        self.gpt_client = GPTClient()
        self.bybit_client = bybit_client
        self.market_data_service = market_data_service
        self.technical_indicators = TechnicalIndicators()
        self.storage_formatter = StorageFormatter()
        
        # 새로운 저장소 추가
        self.analysis_store = GPTAnalysisStore()

        if bybit_client:
            self.market_data_service = MarketDataService(bybit_client)

        # 프롬프트 템플릿 수정
        self.SYSTEM_PROMPT = """당신은 1시간 봉을 기준으로 비트코인 선물 거래를 하는 트레이더입니다.

+ *** 매매 포지션별 가격 설정 규칙 ***
+ 
+ 매도(SELL) 포지션:
+ - 원리: 가격이 내려갈 때 수익 발생
+ - 예시) 현재가 50000일 때:
+   • 진입가: 50000
+   • 손절가: 51000 (진입가보다 높게)
+   • 이익실현1: 49000 (진입가보다 낮게)
+   • 이익실현2: 48000 (이익실현1보다 더 낮게)
+ 
+ 매수(BUY) 포지션:
+ - 원리: 가격이 올라갈 때 수익 발생
+ - 예시) 현재가 50000일 때:
+   • 진입가: 50000
+   • 손절가: 49000 (진입가보다 낮게)
+   • 이익실현1: 51000 (진입가보다 높게)
+   • 이익실현2: 52000 (이익실현1보다 더 높게)

응답 형식:
{
    "market_summary": {
        "market_phase": "상승" 또는 "하락" 또는 "횡보",
        "overall_sentiment": "긍정" 또는 "부정" 또는 "중립",
        "short_sentiment": "긍정" 또는 "부정" 또는 "중립",
        "volume_status": "거래량 증가" 또는 "거래량 감소" 또는 "거래량 보통",
        "risk_level": "높음" 또는 "중간" 또는 "낮음",
        "confidence": 0-100 사이 정수
    },
    "trading_signals": {
        "position_suggestion": "BUY" 또는 "SELL" 또는 "HOLD",
        "leverage": 1-10 사이 정수,
        "position_size": 5-20 사이 정수,
        "entry_price": 현재가,
        "stop_loss": 포지션에 맞는 적절한 손절가,
        "take_profit1": 포지션에 맞는 적절한 1차 익절가,
        "take_profit2": 포지션에 맞는 적절한 2차 익절가,
        "reason": "매매 사유"
    }
}

+ 주의사항:
+ 1. 매도(SELL) 포지션에서는 반드시:
+    take_profit2 < take_profit1 < entry_price < stop_loss
+ 2. 매수(BUY) 포지션에서는 반드시:
+    stop_loss < entry_price < take_profit1 < take_profit2
+ 3. 이 순서가 맞지 않으면 주문이 실패합니다.

2. 매매 원칙:
   • 상승 추세: RSI > 50, MACD > 0, 볼린저 밴드 중앙 이상일 때 매수
   • 하락 추세: RSI < 50, MACD < 0, 볼린저 밴드 중앙 이하일 때 매도
   • 횡보장: 변동성이 낮거나 명확한 신호가 없을 때는 HOLD

3. 리스크 관리:
   - 레버리지는 1-10배 사이로 제한
   - 손절가/이익실현가 설정 규칙:
    • 매수(BUY) 포지션:
      - Stop Loss는 진입가보다 낮게 
      - Take Profit은 진입가보다 높게 
    • 매도(SELL) 포지션:
      - Stop Loss는 진입가보다 높게
      - Take Profit은 진입가보다 낮게 

반드시 위 JSON 형식으로만 응답하세요. 다른 설명이나 텍스트는 포함하지 마세요.

주의사항:
1. HOLD 포지션일 때도 모든 가격 필드는 숫자로 설정해야 합니다
2. entry_points는 항상 현재가를 포함해야 합니다
3. stopLoss와 takeProfit은 문자열이 아닌 숫자여야 합니다. 매도포지션의 경우 반듯이 Stop Loss는 진입가보다 높아야하고, Take Profit은 진입가보다 낮아야합니다.

3. 신뢰도(confidence) 판단 기준:
   • 지표들의 일관성 (RSI, MACD, BB가 같은 방향을 가리키는지)
   • 시장 상황의 명확성
   • 거래량 증감과 추세의 일치도
   • 다이버전스 존재 여부
   • 주의: 신뢰도는 기술적 지표의 강도와는 다른 개념이고, 분석이 얼마나 정확한지에 대한 수치입니다.
   • 예시: 
     - 모든 지표가 약하지만 일관된 방향을 가리키면 신뢰도는 높을 수 있음
     - 지표가 강하더라도 서로 상충되면 신뢰도는 낮을 수 있음
"""

        self.ANALYSIS_PROMPT_TEMPLATE = """
현재 시장 데이터를 분석하여 JSON 형식으로만 응답해주세요:

현재 시장 데이터:
- 현재가: ${current_price:,.2f}
- RSI: {rsi:.1f}
- MACD: {macd}
- 볼린저밴드: {bollinger}
- 추세: {trend}
- 추세강도: {trend_strength}/100
- 24시간 변동: {price_change:+.2f}%
- 거래량: {volume:,.0f}
- 자금조달비율: {funding_rate:.4f}%

위 데이터를 분석하여 system prompt에서 지정한 JSON 형식으로만 응답하세요.
다른 설명이나 텍스트는 포함하지 마세요."""

    async def analyze_market(self, timeframe: str, data: pd.DataFrame) -> Dict:
        """시장 분석 수행"""
        try:
            # 기술적 지표 계산
            df_with_indicators = self.technical_indicators.calculate_indicators(data)
            if df_with_indicators is None:
                logger.error("기술적 지표 계산 실패")
                return None
            
            # 시장 데이터 조회
            market_data = await self.market_data_service.get_market_data('BTCUSDT')
            if not market_data:
                logger.error("시장 데이터 조회 실패")
                return None
            
            # 디버깅을 위한 로그 추가
            logger.info(f"계산된 지표: {df_with_indicators.columns.tolist()}")
            logger.info(f"시장 데이터: {market_data}")
            
            # 기술적 분석 결과 가져오기
            technical_analysis = self.technical_indicators.analyze_signals(df_with_indicators)
            if technical_analysis is None:
                logger.error("기술적 분석 결과가 없음")
                return None

            # GPT에 전달할 데이터 구성
            latest = df_with_indicators.iloc[-1]
            analysis_data = {
                'market_data': market_data,
                'indicators': {
                    'rsi': float(latest['rsi']),
                    'macd': float(latest['macd']),
                    'macd_signal': float(latest['macd_signal']),
                    'bb_position': self.technical_indicators._analyze_bollinger(df_with_indicators),
                    'trend': technical_analysis['trend'],
                    'trend_strength': technical_analysis['strength']
                }
            }
            
            # 프롬프트 생성
            system_message = {"role": "system", "content": self.SYSTEM_PROMPT}
            user_message = {"role": "user", "content": self._create_analysis_prompt(df_with_indicators, analysis_data['indicators'], timeframe)}
            
            # GPT API 호출
            response = await self.gpt_client.call_gpt_api([system_message, user_message])
            
            # 응답 처리
            if not response:
                logger.error("GPT API 응답이 없음")
                return None
            
            # 응답 텍스트 추출
            content = response.choices[0].message.content.strip()
            
            # JSON 파싱
            try:
                gpt_analysis = json.loads(content)
            except json.JSONDecodeError:
                logger.error("JSON 파싱 실패")
                logger.error(f"원본 응답: {content}")
                return None
            
            # 최종 분석 결과 구성
            analysis = {
                "market_summary": gpt_analysis['market_summary'],
                "technical_analysis": {
                    "trend": technical_analysis['trend'],
                    "strength": technical_analysis['strength'],
                    "indicators": {
                        "rsi": float(latest['rsi']),
                        "macd": technical_analysis['signals']['macd'],
                        "bollinger": technical_analysis['signals']['bollinger'],
                        "divergence_type": df_with_indicators['divergence_type'].iloc[-1],
                        "divergence_desc": df_with_indicators['divergence_desc'].iloc[-1]
                    }
                },
                "trading_signals": {
                    "position_suggestion": gpt_analysis['trading_signals']['position_suggestion'],
                    "leverage": gpt_analysis['trading_signals']['leverage'],
                    "position_size": gpt_analysis['trading_signals']['position_size'],
                    "entry_price": float(latest['close']),
                    "stop_loss": gpt_analysis['trading_signals']['stop_loss'],
                    "take_profit1": gpt_analysis['trading_signals']['take_profit1'],
                    "take_profit2": gpt_analysis['trading_signals']['take_profit2'],
                    "reason": gpt_analysis['trading_signals']['reason']
                },
                "auto_trading": {
                    "enabled": True,
                    "status": "active"
                },
                "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
                "timestamp": int(time.time() * 1000)
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"시장 분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def _validate_analysis_result(self, result: Dict) -> Dict:
        """분석 결과 검증 및 정규화"""
        try:
            # 기본 필드 검증
            required_fields = {
                'position': ['position'],
                'entry_price': ['entry_price'],
                'stop_loss': ['stop_loss'],
                'take_profit': ['take_profit'],
                'leverage': ['leverage'],
                'confidence': ['confidence'],
                'reason': ['reason']
            }
            
            # 매도 포지션의 가격 설정 검증
            trading_signals = result.get('trading_signals', {})
            if trading_signals.get('position_suggestion') == 'SELL':
                entry_price = float(trading_signals.get('entry_price', 0))
                stop_loss = float(trading_signals.get('stop_loss', 0))
                take_profit1 = float(trading_signals.get('take_profit1', 0))
                take_profit2 = float(trading_signals.get('take_profit2', 0))
                
                # 매도 포지션의 가격 순서 검증
                if not (take_profit2 < take_profit1 < entry_price < stop_loss):
                    logger.warning("매도 포지션의 가격 순서가 잘못되었습니다. 수정합니다.")
                    # 가격 재설정
                    trading_signals['stop_loss'] = entry_price * 1.02
                    trading_signals['take_profit1'] = entry_price * 0.98
                    trading_signals['take_profit2'] = entry_price * 0.96
            
            for section, fields in required_fields.items():
                if section not in result:
                    raise ValueError(f"필수 섹션 누락: {section}")
                    
                for field in fields:
                    if field not in result[section]:
                        raise ValueError(f"필수 필드 누락: {section}.{field}")
                    
            return result
            
        except Exception as e:
            logger.error(f"분석 결과 검증 중 오류: {str(e)}")
            return {}

    def _create_analysis_prompt(self, df: pd.DataFrame, indicators: Dict, timeframe: str) -> str:
        """분석 프롬프트 생성"""
        try:
            # 템플릿에 데이터 적용
            prompt = self.ANALYSIS_PROMPT_TEMPLATE.format(
                current_price=df['close'].iloc[-1],
                rsi=indicators['rsi'],
                macd=indicators['macd'],
                macd_signal=indicators['macd_signal'],
                bollinger=indicators['bb_position'],
                trend=indicators['trend'],
                trend_strength=indicators['trend_strength'],
                price_change=df['price_change_24h'].iloc[-1],
                volume=df['volume'].iloc[-1],
                volume_change=df['volume_change_24h'].iloc[-1],
                funding_rate=0.01  # 기본값 설정
            )
            return prompt
        except Exception as e:
            logger.error(f"프롬프트 생성 중 오류: {str(e)}")
            return None

    def _determine_position(self, df: pd.DataFrame) -> str:
        # Implementation of _determine_position method
        pass

    def _calculate_stop_loss(self, df: pd.DataFrame) -> float:
        # Implementation of _calculate_stop_loss method
        pass

    def _process_analysis_result(self, analysis_result: dict) -> dict:
        """GPT 분석 결과 처리"""
        try:
            # 트레이딩 신호 처리
            trading_signals = analysis_result.get('trading_signals', {})
            position = trading_signals.get('position_suggestion')
            
            return {
                'market_summary': analysis_result.get('market_summary', {}),
                'technical_analysis': analysis_result.get('technical_analysis', {}),
                'trading_signals': {
                    'position_suggestion': position,
                    'leverage': trading_signals.get('leverage', 1),
                    'position_size': trading_signals.get('position_size', 10),
                    'entry_price': trading_signals.get('entry_price'),
                    'stop_loss': trading_signals.get('stop_loss'),
                    'take_profit1': trading_signals.get('take_profit1'),
                    'take_profit2': trading_signals.get('take_profit2'),
                    'reason': trading_signals.get('reason', '')
                }
            }
            
        except Exception as e:
            logger.error(f"분석 결과 처리 중 오류: {str(e)}")
            return {}

    def _convert_position(self, position: str) -> Optional[str]:
        """포지션 신호 변환"""
        if position == 'BUY':
            return '매수'
        elif position == 'SELL':
            return '매도'
        return None  # HOLD나 다른 값은 None 반환