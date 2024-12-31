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
        return """당신은 전문 암호화폐 시장 분석가입니다.
월 30% 이상의 수익률을 목표로 하되, 안전한 매매 전략을 제시해주세요.

매매 전략 가이드라인:
1. 시장이 불안정할 때는 보수적으로 접근하세요
2. 레버리지는 변동성과 리스크를 고려하여 신중하게 설정하세요:
   - 최대 레버리지: 10배
   - 리스크 높음: 1-3배
   - 리스크 중간: 3-7배
   - 리스크 낮음: 7-10배
3. 포지션 크기는 리스크에 따라 조절하세요:
   - 리스크 높음: 5-10%
   - 리스크 중간: 10-20%
   - 리스크 낮음: 20-30%
4. 손절가와 익절가는 레버리지를 고려하여 설정하세요:
   - 레버리지가 높을수록 더 타이트하게 설정
   - 변동성이 높을수록 더 넓게 설정

중요: 응답은 반드시 다음 JSON 구조의 모든 필드를 포함해야 합니다:

{
    "market_summary": {  # 필수
        "market_phase": "상승/하락/축적/분배",  # 필수
        "overall_sentiment": "긍정적/부정적/중립",  # 필수
        "short_term_sentiment": "긍정적/부정적/중립",  # 필수
        "risk_level": "높음/중간/낮음",  # 필수
        "volume_trend": "증가/감소/중립",  # 필수
        "confidence": 0-100  # 필수 (신뢰도)
    },
    "technical_analysis": {  # 필수
        "trend": "상승/하락/중립",  # 필수
        "strength": 0-100,  # 필수 (추세 강도)
        "indicators": {  # 필수
            "rsi": 0-100,  # 필수
            "macd": "상승/하락",  # 필수
            "bollinger": "상단/중단/하단",  # 필수
            "divergence": {  # 필수
                "type": "없음/상승/하락",  # 필수
                "description": "다이버전스 설명",  # 필수
                "timeframe": "현재 시간대"  # 필수
            }
        }
    },
    "trading_strategy": {  # 필수
        "position": "매수/매도/관망",  # 필수 (포지션)
        "entry_points": [숫자],  # 필수 (진입가격)
        "targets": [숫자, 숫자],  # 필수 (목표가)
        "stop_loss": 숫자,  # 필수 (손절가)
        "leverage": 1-10,  # 필수 (레버리지, 최대 10배)
        "position_size": 5-30  # 필수 (포지션 크기, %)
    }
}

추가 요구사항:
1. 모든 숫자는 콤마 없이 작성 (예: 105200)
2. 모든 가격은 정수로 표현
3. 모든 퍼센트 값은 소수점 한 자리까지만 표현
4. 모든 필드는 필수이며 누락하면 안 됨
5. 추가 필드는 무시됨

이 형식을 정확히 따르지 않으면 분석이 실패하니 주의하세요."""

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
            response = await self.client.chat.completions.create(
                model="gpt-4-1106-preview",
                messages=[
                    {"role": "system", "content": "You are a professional cryptocurrency market analyst."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"GPT API 호출 중 오류: {str(e)}")
            return None

    def _process_response(self, response) -> Dict:
        """GPT API 응답 처리"""
        try:
            content = response.choices[0].message.content
            content = content.strip()
            
            # 여러 개의 JSON 객체가 있는 경우 마지막 객체만 사용
            json_objects = []
            current_object = ""
            brace_count = 0
            
            for char in content:
                if char == '{':
                    if brace_count == 0:
                        current_object = '{'
                    else:
                        current_object += char
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    current_object += '}'
                    if brace_count == 0:
                        try:
                            # 현재 JSON 객체 파싱 시도
                            json_obj = json.loads(current_object)
                            json_objects.append(json_obj)
                        except json.JSONDecodeError:
                            pass
                        current_object = ""
                elif brace_count > 0:
                    current_object += char
            
            # 마지막 유효한 JSON 객체 사용
            if not json_objects:
                raise json.JSONDecodeError("No valid JSON objects found", content, 0)
            
            analysis = json_objects[-1]  # 마지막 JSON 객체 사용
            
            # 응답 형식 맞추기
            if 'trading_strategy' in analysis:
                # position -> position_suggestion 변환
                if 'position' in analysis['trading_strategy']:
                    analysis['trading_strategy']['position_suggestion'] = analysis['trading_strategy'].pop('position')
                
                # targets -> take_profit 변환
                if 'targets' in analysis['trading_strategy']:
                    analysis['trading_strategy']['take_profit'] = analysis['trading_strategy'].pop('targets')
            
            # 저장 시간 추가
            analysis['saved_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
            
            return analysis
            
        except json.JSONDecodeError as e:
            logger.error(f"GPT 응답 JSON 파싱 실패: {str(e)}")
            logger.error(f"원본 응답: {content if 'content' in locals() else response}")
            return {}
        except Exception as e:
            logger.error(f"응답 처리 중 오류: {str(e)}")
            return {}
