# src/gpt_client.py
import httpx
import os
import json
import asyncio
from typing import Optional, Dict, Any
import logging
from datetime import datetime
from openai import AsyncOpenAI
import re
import time
from config.trading_config import trading_config
import traceback

logger = logging.getLogger(__name__)

class GPTClient:
    def __init__(self, max_retries: int = 3, timeout: int = 30):
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.client = AsyncOpenAI(api_key=self.api_key)
        self.max_retries = max_retries
        self.timeout = timeout
        self.last_call_time = 0
        self.cache = {}  # 캐시 저장소
        self.cache_duration = 60  # 캐시 유효 시간 (초)
        
        # 시스템 프롬프트 수정 (1시간 분석 중심)
        self.SYSTEM_PROMPT = """당신은 1시간 봉을 기준으로 비트코인 선물 거래를 하는 트레이더입니다.
다음 원칙을 따라 매매 전략을 제시하세요:

1. 분석 기준
   - 1시간 봉의 기술적 지표를 중심으로 분석
   - 현재 시장 상황(거래량, 자금조달비율 등) 고려
   - 단기 모멘텀과 반전 신호에 집중

2. 매매 원칙
   • 상승 추세
     - 기술적 지표가 강세를 보일 때 매수
     - RSI > 50, MACD > 0, 볼린저 밴드 중앙 이상
   
   • 하락 추세
     - 기술적 지표가 약세를 보일 때 매도
     - RSI < 50, MACD < 0, 볼린저 밴드 중앙 이하
   
   • 횡보장
     - 변동성이 낮을 때는 관망
     - 명확한 신호가 없으면 포지션 진입 자제

3. 리스크 관리
   - 레버리지는 1-10배 사이로 제한
   - 손절가, 익절가 필수

각 분석과 판단에는 반드시 명확한 근거를 제시하고,
현재 시장 상황에 가장 적합한 전략을 선택하세요."""
        
        # 분석 프롬프트 템플릿 수정
        self.ANALYSIS_PROMPT_TEMPLATE = """
        다음 비트코인 1시간 차트 데이터를 바탕으로 매매 전략을 제시해주세요.
        
        [1시간 차트 분석]
        • 현재가: ${current_price:,.2f}
        • RSI: {rsi:.1f}
        • MACD: {macd}
        • 볼린저밴드: {bollinger}
        • 추세: {trend}
        • 추세강도: {trend_strength}/100
        
        [시장 상태]
        • 24시간 변동: {price_change:+.2f}%
        • 거래량(24h): {volume:,.0f}
        • 자금조달비율: {funding_rate:.4f}%
        
        반드시 다음 JSON 형식으로만 응답하세요:
        {{
            "position": "매수" 또는 "매도" 또는 "관망",
            "entry_price": 진입가격(숫자),
            "stop_loss": 손절가(숫자),
            "take_profit": 익절가(숫자),
            "leverage": 1-5 사이의 숫자,
            "confidence": 0-100 사이의 숫자,
            "reason": "진입 이유"
        }}
        """

    def _create_system_prompt(self) -> str:
        """시스템 프롬프트 생성"""
        return self.SYSTEM_PROMPT

    async def call_gpt_api(self, request_text: str, use_cache: bool = False) -> Optional[Dict[str, Any]]:
        """GPT API 호출"""
        try:
            logger.info(f"GPT API 호출 시작 (캐시 사용: {use_cache})")
            
            if not use_cache:
                logger.info("캐시 사용하지 않음 - 실제 API 호출")
                return await self._make_api_call(request_text)

            cache_key = hash(request_text)
            if cache_key in self.cache:
                cached_data, cached_time = self.cache[cache_key]
                if time.time() - cached_time < self.cache_duration:
                    logger.info(f"캐시된 응답 사용 (저장된 지 {time.time() - cached_time:.0f}초)")
                    return cached_data

            # 실제 API 호출
            response = await self._make_api_call(request_text)
            
            # 캐시 저장
            if use_cache and response:
                self.cache[cache_key] = (response, time.time())
            
            return response

        except Exception as e:
            logger.error(f"GPT API 호출 중 오류: {str(e)}")
            return {}

    async def _make_api_call(self, request_text: str) -> Optional[Dict[str, Any]]:
        """실제 GPT API 호출 수행"""
        try:
            # Rate limit 관리
            current_time = time.time()
            time_since_last_call = current_time - self.last_call_time
            if time_since_last_call < 20:  # 최소 20초 간격
                await asyncio.sleep(20 - time_since_last_call)
            
            # API 호출
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": self._create_system_prompt()},
                    {"role": "user", "content": request_text}
                ],
                temperature=0.2,
                max_tokens=2000
            )
            
            self.last_call_time = time.time()
            return self._process_response(response)
            
        except Exception as e:
            logger.error(f"API 호출 중 오류: {str(e)}")
            return None

    @staticmethod
    def validate_analysis(analysis: Dict) -> bool:
        """분석 결과 유효성 검증"""
        required_fields = [
            'market_summary',
            'technical_analysis',
            'trading_strategy',
            'risk_management'
        ]
        
        return all(field in analysis for field in required_fields)

    async def generate(self, prompt: str) -> str:
        """GPT API 호출"""
        try:
            logger.info("GPT API 호출 시작")
            response = await self.client.chat.completions.create(
                model="gpt-4-1106-preview",
                messages=[
                    {"role": "system", "content": self._create_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            result = response.choices[0].message.content
            logger.info("GPT API 응답 수신 완료")
            return result
            
        except Exception as e:
            logger.error(f"GPT API 호출 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def _process_response(self, response) -> Dict:
        """GPT API 응답 처리"""
        try:
            content = response.choices[0].message.content.strip()
            
            # 새로 구현한 JSON 파싱 메서드 사용
            analysis = self._parse_json_response(content)
            if not analysis:
                logger.error("JSON 파싱 실패")
                return {}
            
            # 응답 형식 맞추기
            if 'trading_strategy' in analysis:
                if 'position' in analysis['trading_strategy']:
                    analysis['trading_strategy']['position_suggestion'] = analysis['trading_strategy'].pop('position')
                
                if 'targets' in analysis['trading_strategy']:
                    analysis['trading_strategy']['takeProfit'] = analysis['trading_strategy'].pop('targets')
                if 'stop_loss' in analysis['trading_strategy']:
                    analysis['trading_strategy']['stopLoss'] = analysis['trading_strategy'].pop('stop_loss')
                if 'take_profit' in analysis['trading_strategy']:
                    analysis['trading_strategy']['takeProfit'] = analysis['trading_strategy'].pop('take_profit')
            
            # 저장 시간 추가
            analysis['saved_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
            
            # GPT 응답 처리시 trading_config의 설정값 참조
            if 'trading_strategy' in analysis:
                strategy = analysis['trading_strategy']
                if 'leverage' not in strategy:
                    strategy['leverage'] = trading_config.gpt_settings['default_leverage']
                if 'position_size' not in strategy:
                    strategy['position_size'] = trading_config.gpt_settings['max_position_size']
            
            return analysis
            
        except Exception as e:
            logger.error(f"GPT 응답 처리 중 오류: {str(e)}")
            logger.error(f"원본 응답: {content if 'content' in locals() else response}")
            return {}

    def _clean_json_string(self, json_str: str) -> str:
        """JSON 문자열 정리"""
        try:
            # 마지막 항목의 콤마 제거
            json_str = re.sub(r',(\s*})', r'\1', json_str)
            json_str = re.sub(r',(\s*])', r'\1', json_str)
            return json_str
        except Exception as e:
            logger.error(f"JSON 문자열 정리 중 오류: {str(e)}")
            return json_str

    def _parse_json_response(self, response: str) -> Dict:
        """GPT 응답에서 JSON 추출 및 파싱"""
        try:
            logger.debug(f"원본 응답: {response}")
            # JSON 문자열 정리
            cleaned_response = self._clean_json_string(response)
            logger.debug(f"정리된 응답: {cleaned_response}")
            
            # JSON 파싱 시도
            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError as e:
                logger.error(f"첫 번째 JSON 파싱 시도 실패: {str(e)}")
                # JSON 형식이 아닌 경우, JSON 부분만 추출 시도
                json_match = re.search(r'{.*}', cleaned_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    cleaned_json = self._clean_json_string(json_str)
                    logger.debug(f"추출된 JSON: {cleaned_json}")
                    return json.loads(cleaned_json)
                raise
            
        except Exception as e:
            logger.error(f"JSON 파싱 중 오류: {str(e)}")
            logger.error(f"원본 응답: {response}")
            return None

    async def get_analysis(self, prompt: str) -> Optional[str]:
        """GPT API를 통해 분석 요청"""
        try:
            # API 호출
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": self._create_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            # 응답 추출
            if response and response.choices:
                return response.choices[0].message.content
            return None
            
        except Exception as e:
            logger.error(f"GPT 분석 요청 중 오류: {str(e)}")
            return None
