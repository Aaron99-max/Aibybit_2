# src/gpt_client.py
import httpx
import os
import json
import asyncio
from typing import Optional, Dict, Any, List
import logging
from datetime import datetime
from openai import AsyncOpenAI
import re
import time
from config.trading_config import trading_config
import traceback

logger = logging.getLogger(__name__)

class GPTClient:
    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.client = AsyncOpenAI(api_key=self.api_key)
        self.max_retries = 3
        self.timeout = 30
        self.last_call_time = 0
        self.cache = {}
        self.cache_duration = 60

    async def call_gpt_api(self, messages: List[Dict], use_cache: bool = False) -> Optional[Dict[str, Any]]:
        """GPT API 호출"""
        try:
            logger.info(f"GPT API 호출 시작 (캐시 사용: {use_cache})")
            
            if not use_cache:
                logger.info("캐시 사용하지 않음 - 실제 API 호출")
                return await self._make_api_call(messages)

            cache_key = hash(str(messages))
            if cache_key in self.cache:
                cached_data, cached_time = self.cache[cache_key]
                if time.time() - cached_time < self.cache_duration:
                    logger.info(f"캐시된 응답 사용 (저장된 지 {time.time() - cached_time:.0f}초)")
                    return cached_data

            # 실제 API 호출
            response = await self._make_api_call(messages)
            
            # 캐시 저장
            if use_cache and response:
                self.cache[cache_key] = (response, time.time())
            
            return response

        except Exception as e:
            logger.error(f"GPT API 호출 중 오류: {str(e)}")
            return {}

    async def _make_api_call(self, messages: List[Dict]) -> Optional[Dict[str, Any]]:
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
                messages=messages,
                temperature=0.2,
                max_tokens=2000
            )
            
            self.last_call_time = time.time()
            return response
            
        except Exception as e:
            logger.error(f"API 호출 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            return None
