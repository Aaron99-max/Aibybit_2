import asyncio
import json
import logging
import ssl
import time
import hmac
import hashlib
import certifi
import websockets
from typing import Dict, List, Optional, Callable
from config.bybit_config import BybitConfig

logger = logging.getLogger(__name__)

class BybitWebsocketClient:
    def __init__(self, config: BybitConfig = None):
        """
        Args:
            config: Bybit 설정
        """
        self.config = config or BybitConfig()
        self.ws = None
        self.is_connected = False
        self.callbacks = {
            'order': [],
            'position': [],
            'execution': []
        }
        
        # SSL 컨텍스트 설정
        self.ssl_context = ssl.create_default_context(cafile=certifi.where())
        
        # 웹소켓 URL 설정
        self.ws_url = "wss://stream-testnet.bybit.com/v5/private" if self.config.testnet else "wss://stream.bybit.com/v5/private"

    def _generate_signature(self, expires: str) -> str:
        """서명 생성
        
        Args:
            expires: 만료 시간 (Unix timestamp)
            
        Returns:
            생성된 서명
        """
        data = f"GET/realtime{expires}"
        return hmac.new(
            self.config.api_secret.encode('utf-8'),
            data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    async def connect(self):
        """웹소켓 연결"""
        try:
            self.ws = await websockets.connect(
                self.ws_url,
                ssl=self.ssl_context
            )
            self.is_connected = True
            logger.info("웹소켓 연결 성공")
            
            # 인증
            await self._authenticate()
            
            # 구독 시작
            await self._subscribe()
            
        except Exception as e:
            logger.error(f"웹소켓 연결 실패: {str(e)}")
            self.is_connected = False

    async def _authenticate(self):
        """웹소켓 인증"""
        try:
            expires = str(int(time.time() * 1000) + 10000)  # 현재 시간 + 10초
            signature = self._generate_signature(expires)
            
            auth_message = {
                "op": "auth",
                "args": [
                    self.config.api_key,
                    expires,
                    signature
                ]
            }
            await self.ws.send(json.dumps(auth_message))
            response = await self.ws.recv()
            logger.info(f"웹소켓 인증 응답: {response}")
            
        except Exception as e:
            logger.error(f"웹소켓 인증 실패: {str(e)}")
            raise

    async def _subscribe(self):
        """토픽 구독"""
        try:
            subscribe_message = {
                "op": "subscribe",
                "args": [
                    "order",           # 주문 업데이트
                    "position",        # 포지션 업데이트
                    "execution"        # 체결 업데이트
                ]
            }
            await self.ws.send(json.dumps(subscribe_message))
            response = await self.ws.recv()
            logger.info(f"구독 응답: {response}")
            
        except Exception as e:
            logger.error(f"구독 실패: {str(e)}")
            raise

    def add_callback(self, topic: str, callback: Callable):
        """콜백 함수 등록"""
        if topic in self.callbacks:
            self.callbacks[topic].append(callback)

    async def _handle_order_update(self, data: Dict):
        """주문 업데이트 처리"""
        for callback in self.callbacks['order']:
            await callback(data)

    async def _handle_position_update(self, data: Dict):
        """포지션 업데이트 처리"""
        for callback in self.callbacks['position']:
            await callback(data)

    async def _handle_execution_update(self, data: Dict):
        """체결 업데이트 처리"""
        for callback in self.callbacks['execution']:
            await callback(data)

    async def start_monitoring(self):
        """실시간 모니터링 시작"""
        while True:
            try:
                if not self.is_connected:
                    await self.connect()
                
                message = await self.ws.recv()
                data = json.loads(message)
                
                # 토픽별 처리
                if 'topic' in data:
                    if data['topic'] == 'order':
                        await self._handle_order_update(data)
                    elif data['topic'] == 'position':
                        await self._handle_position_update(data)
                    elif data['topic'] == 'execution':
                        await self._handle_execution_update(data)
                
            except websockets.ConnectionClosed:
                logger.warning("웹소켓 연결 끊김, 재연결 시도...")
                self.is_connected = False
                await asyncio.sleep(5)  # 5초 후 재시도
                
            except Exception as e:
                logger.error(f"모니터링 중 오류 발생: {str(e)}")
                await asyncio.sleep(5)  # 5초 후 재시도

    async def stop(self):
        """웹소켓 연결 종료"""
        try:
            if self.ws:
                logger.info("웹소켓 연결 종료 중...")
                await self.ws.close()
                self.ws = None
                self.is_connected = False
                logger.info("웹소켓 연결이 종료되었습니다.")
        except Exception as e:
            logger.error(f"웹소켓 연결 종료 중 오류: {str(e)}")
