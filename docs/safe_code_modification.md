# 안전한 코드 수정 가이드라인

## 1. 수정 전 준비사항
- 현재 작동하는 코드의 상태 확인
- 수정 전에 현재 작동하는 코드의 동작 방식을 정확히 파악하고 필요한 부분 명확히 수정
- 수정이 다른 기능에 미치는 영향을 미리 검토
- 영향을 받을 수 있는 연관 코드 식별

## 2. 단계별 수정 프로세스
1. **백업**
   ```python
   # 기존 코드 주석으로 백업
   """
   original_code = ...
   """
   # 새 코드 추가
   new_code = ...
   ```

2. **격리된 수정**
   ```python
   class MessageFormatter:
       def format_new_message(self):
           # 새로운 포맷 메서드 추가
           pass
           
       def format_old_message(self):
           # 기존 메서드 유지
           pass
   ```

3. **점진적 적용**
   ```python
   try:
       result = new_method()
   except Exception:
       logger.error("새 메서드 실패, 기존 메서드로 폴백")
       result = old_method()
   ```

## 3. 테스트 전략
1. 기존 기능 테스트
2. 새 기능 단위 테스트
3. 통합 테스트
4. 롤백 계획 준비

## 4. 실제 적용 예시
```python
class TradingHandler:
    async def handle_balance(self, update, context):
        try:
            # 1. 새로운 포맷터 시도
            message = self.message_formatter.format_new_balance()
            
            # 2. 실패시 기존 포맷 사용
            if not message:
                message = self._format_old_balance()
                
            await self.send_message(message)
            
        except Exception as e:
            logger.error(f"잔고 조회 중 오류: {e}")
            # 3. 기본 에러 처리 유지
```

## 5. 주의사항
- 한 번에 하나의 기능만 수정
- 각 단계마다 테스트 수행
- 로그 메시지 상세히 기록
- 롤백 포인트 유지 