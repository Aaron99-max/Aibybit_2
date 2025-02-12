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
다음 원칙을 따라 매매 전략을 제시하세요:

1. 응답 형식은 반드시 아래 JSON 형식을 따라야 합니다:
{
    "market_summary": {
        "current_price": 현재가,
        "market_phase": "상승" 또는 "하락" 또는 "횡보",
        "sentiment": "POSITIVE" 또는 "NEGATIVE" 또는 "NEUTRAL",
        "short_term": "POSITIVE" 또는 "NEGATIVE" 또는 "NEUTRAL",
        "volume": "VOLUME_INCREASE" 또는 "VOLUME_DECREASE" 또는 "VOLUME_NEUTRAL",
        "risk": "HIGH" 또는 "MEDIUM" 또는 "LOW",
        "confidence": 0-100 사이 정수
    },
    "trading_signals": {
        "position_suggestion": "BUY" 또는 "SELL" 또는 "HOLD",
        "leverage": 1-10 사이 정수,
        "position_size": 5-20 사이 정수,
        "entry_points": [현재가],
        "stopLoss": 현재가의 -2%,
        "takeProfit": 현재가의 +2%,
        "reason": "매매 사유"
    }
}

2. 매매 원칙:
   • 상승 추세: RSI > 50, MACD > 0, 볼린저 밴드 중앙 이상일 때 매수
   • 하락 추세: RSI < 50, MACD < 0, 볼린저 밴드 중앙 이하일 때 매도
   • 횡보장: 변동성이 낮거나 명확한 신호가 없을 때는 HOLD

3. 리스크 관리:
   - 레버리지는 1-10배 사이로 제한
   - 손절가, 익절가 필수 설정

반드시 위 JSON 형식으로만 응답하세요. 다른 설명이나 텍스트는 포함하지 마세요.

주의사항:
1. HOLD 포지션일 때도 모든 가격 필드는 숫자로 설정해야 합니다
2. entry_points는 항상 현재가를 포함해야 합니다
3. stopLoss와 takeProfit은 문자열이 아닌 숫자여야 합니다."""

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
                    "stop_loss": float(latest['close'] * 0.98),
                    "take_profit1": float(latest['close'] * 1.02),
                    "take_profit2": float(latest['close'] * 1.04),
                    "reason": gpt_analysis['trading_signals']['reason']
                },
                "auto_trading": {"enabled": False, "status": "inactive"},
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
            required_fields = {
                'position': ['position'],
                'entry_price': ['entry_price'],
                'stop_loss': ['stop_loss'],
                'take_profit': ['take_profit'],
                'leverage': ['leverage'],
                'confidence': ['confidence'],
                'reason': ['reason']
            }
            
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

    def _calculate_take_profit(self, df: pd.DataFrame) -> float:
        # Implementation of _calculate_take_profit method
        pass

    def _convert_position(self, position: str) -> Optional[str]:
        """포지션 신호 변환"""
        if position == 'BUY':
            return '매수'
        elif position == 'SELL':
            return '매도'
        return None  # HOLD나 다른 값은 None 반환