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
        
    def _create_system_prompt(self) -> str:
        """시스템 프롬프트 생성"""
        return """당신은 월 30% 이상의 수익을 목표로 하는 암호화폐 트레이더입니다.
시장 상황에 따라 유연하게 대응하되, 다음 원칙을 참고하세요:

1. 시장 분석 기준
   - 단기(15m/1h): 모멘텀과 즉각적인 반전 신호
   - 중기(4h): 추세의 방향과 강도
   - 장기(1d): 주요 지지/저항 및 전체 시장 흐름
   
2. 매매 전략 수립
   강세장:
   - 추세가 강할 때는 레버리지 7-10배, 포지션 20-30%까지 공격적 진입
   - 고점 돌파 시 추가 진입, 부분 익절 전략 사용
   
   약세장:
   - 변동성이 높을 때는 레버리지 3-5배, 포지션 10-15%로 보수적 접근
   - 반등 포인트에서 분할 매수 전략 사용
   
   횡보장:
   - 레인지 상단/하단에서 역방향 포지션
   - 브레이크아웃 발생 시 추세 추종으로 전환

3. 리스크 관리
   - 시장 상황에 따라 동적으로 손절폭 조정 (1-3%)
   - 이익 실현은 리스크의 2-3배 이상으로 설정
   - 고변동성 구간에서는 포지션 크기 50% 축소

4. 수익 극대화 전략
   - 추세 초기: 공격적 진입 (큰 포지션, 높은 레버리지)
   - 추세 중기: 부분 익절 및 물량 분할
   - 추세 후기: 보수적 접근 (작은 포지션, 낮은 레버리지)

당신의 역할:
1. 현재 시장 상황을 정확히 파악하고 분류
2. 상황에 맞는 최적의 전략 선택
3. 리스크 대비 수익률 최적화
4. 월 30% 수익 달성을 위한 적극적 기회 포착

각 분석과 판단에는 반드시 명확한 근거를 제시하고, 
현재 시장 상황에 가장 적합한 전략을 선택하세요.
"""

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
