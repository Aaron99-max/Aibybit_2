# Bybit API 포러블슈팅 가이드

## 1. 포지션 조회 API 트러블슈팅

### 문제 상황
- 빈 문자열 또는 None 값으로 인한 float 변환 오류
- API 응답의 다양한 필드명 불일치
- 포지션 데이터 누락

### 해결 방법

1. **포지션 데이터 파싱**
```python
def get_positions(self, symbol: str = 'BTCUSDT') -> List[Dict]:
    try:
        positions = await self.bybit_client.fetch_positions([symbol])
        active_positions = []
        
        for pos in positions:
            if isinstance(pos, dict):
                # info 필드 확인 (추가 데이터 소스)
                info = pos.get('info', {})
                pos_symbol = pos.get('symbol', '').split(':')[0].replace('/', '')
                
                if pos_symbol == symbol:
                    # 사이즈 계산 (여러 필드 체크)
                    size = float(pos.get('contracts', 0) or pos.get('size', 0) or 
                               info.get('size', 0) or 0)
                    
                    if abs(size) > 0:
                        active_pos = {
                            'side': 'LONG' if size > 0 else 'SHORT',
                            'size': abs(size),
                            'leverage': float(pos.get('leverage', info.get('leverage', 1))),
                            'entryPrice': float(pos.get('entryPrice', info.get('entry_price', 0)) or 0),
                            'liquidationPrice': float(pos.get('liquidationPrice', info.get('liq_price', 0)) or 0),
                            'unrealizedPnl': float(pos.get('unrealizedPnl', info.get('unrealised_pnl', 0)) or 0),
                            'markPrice': float(pos.get('markPrice', info.get('mark_price', 0)) or 0)
                        }
                        active_positions.append(active_pos)
        return active_positions
    except Exception as e:
        logger.error(f"포지션 조회 중 오류: {str(e)}")
        return []
```

2. **안전한 float 변환**
```python
def safe_float(value, default=0):
    try:
        if value == '' or value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default
```

### 주의사항

1. **필드명 대응**
   - `entryPrice` 또는 `entry_price`
   - `liquidationPrice` 또는 `liq_price`
   - `unrealizedPnl` 또는 `unrealised_pnl`
   - `markPrice` 또는 `mark_price`

2. **데이터 검증**
   - 모든 숫자 필드에 대해 빈 문자열과 None 처리
   - 음수 사이즈는 SHORT 포지션을 의미
   - 심볼 형식 통일 (BTCUSDT:USDT -> BTCUSDT)

3. **로깅**
   - API 응답 전체 로깅
   - 파싱된 포지션 데이터 로깅
   - 오류 상황에 대한 상세 로깅

4. **에러 처리**
   - float 변환 실패
   - API 응답 형식 불일치
   - 필수 필드 누락

### 디버깅 팁
1. API 응답 구조 확인
2. 필드 존재 여부 검증
3. 데이터 타입 확인
4. 중간 결과 로깅

이 문서는 지속적으로 업데이트되어야 하며, 새로운 문제와 해결책이 발견될 때마다 추가됩니다.