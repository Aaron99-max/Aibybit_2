# 메인넷 이전 체크리스트

## 1. 환경 설정 변경
- [x] API 키/시크릿 변경 (테스트넷 -> 메인넷)
  - [x] .env 파일 업데이트
  - [x] 환경변수 확인
- [x] Bybit 클라이언트 설정 변경
  - [x] testnet=False로 설정
  - [x] base URL 변경 (api.bybit.com)
- [ ] 로깅 레벨 조정 (INFO 레벨 권장)

## 2. 거래 제한 설정
- [x] 레버리지 한도 설정
  - [x] 최대 레버리지: 10x
  - [x] 기본 레버리지: 3x
- [x] 포지션 크기 제한
  - [x] 최대 포지션 크기: 30%
  - [ ] 최소 주문 수량: 0.001 BTC
- [ ] 주문 금액 제한
  - [ ] 최소 주문 금액: 1 USDT
  - [ ] 최대 주문 금액: 1000 USDT

## 3. 안전장치 구현
- [ ] 손실 제한
  - [ ] 일일 최대 손실: 5%
  - [ ] 최대 드로우다운: 10%
- [ ] 비상 정지 기능
  - [ ] /stop 명령어
  - [ ] 수동 청산 기능
- [ ] 에러 처리
  - [ ] 주문 실패 시 재시도 로직
  - [ ] API 연결 오류 처리
  - [ ] 잔고 부족 처리

## 4. 자동 분석 시스템
- [ ] 시간대 설정 확인
  - [ ] KST 기준 정시 실행
  - [ ] 4시간봉 분석 시간 (1,5,9,13,17,21시)
- [ ] 분석 결과 처리
  - [ ] 저장 경로 설정
  - [ ] 백업 시스템
- [ ] 실행 조건 검증
  - [ ] 시간 체크 로직
  - [ ] 중복 실행 방지

## 5. 알림 시스템
- [ ] 텔레그램 설정
  - [ ] 봇 토큰 확인
  - [ ] 채팅방 ID 확인 (관리자/단체방)
- [ ] 주요 알림 항목
  - [ ] 포지션 변경
  - [ ] 에러 발생
  - [ ] 일일 실적
  - [ ] 시스템 상태

## 6. 모니터링
- [ ] 시스템 모니터링
  - [ ] CPU/메모리 사용량
  - [ ] 디스크 공간
  - [ ] 네트워크 상태
- [ ] 거래 모니터링
  - [ ] 포지션 상태
  - [ ] 잔고 변화
  - [ ] 주문 실행 상태
- [ ] 로그 모니터링
  - [ ] 에러 로그
  - [ ] 거래 로그
  - [ ] 시스템 로그

## 7. 운영 준비
- [ ] 백업 시스템
  - [ ] 설정 파일 백업
  - [ ] 로그 파일 백업
  - [ ] DB 백업 (필요시)
- [ ] 문서화
  - [ ] 운영 매뉴얼
  - [ ] 문제 해결 가이드
  - [ ] 비상 연락망
- [ ] 테스트
  - [ ] 전체 기능 테스트
  - [ ] 24시간 안정성 테스트
  - [ ] 스트레스 테스트

## 주의사항
1. 초기 운영은 최소 금액으로 시작
2. 모든 기능 정상 확인 후 금액 증가
3. 24/7 모니터링 체계 구축
4. 정기적인 백업 및 로그 검토
5. 문제 발생 시 즉시 중지 및 원인 분석 

src/main.py:
# 환경변수 변경
- api_key = os.getenv('BYBIT_TESTNET_API_KEY')
- api_secret = os.getenv('BYBIT_TESTNET_SECRET_KEY')
+ api_key = os.getenv('BYBIT_MAINNET_API_KEY')
+ api_secret = os.getenv('BYBIT_MAINNET_SECRET_KEY')

# Bybit 클라이언트 초기화 수정
bybit_client = BybitClient(
    api_key=api_key,
    api_secret=api_secret,
-   testnet=True
+   testnet=False
)

src/trade/trade_manager.py:
# 거래 제한 수정 (필요시)
max_leverage = 10  # 메인넷 레버리지 제한 확인
max_position_size = 30  # 메인넷 포지션 크기 제한 확인
min_order_size = 0.001  # 최소 주문 수량 확인

src/services/order_service.py:
# 주문 수량 제한 확인
quantity = round(quantity, 3)  # 메인넷 소수점 자릿수 확인
min_order_value = 1  # USDT 최소 주문 금액 확인

.env 파일 수정:
- BYBIT_TESTNET_API_KEY=xxx
- BYBIT_TESTNET_SECRET_KEY=xxx
+ BYBIT_MAINNET_API_KEY=xxx
+ BYBIT_MAINNET_SECRET_KEY=xxx

추가 고려사항:
거래 수수료 확인 및 조정
레버리지 한도 확인
최소 주문 수량/금액 확인
주문 체결 속도 고려
에러 처리 강화
로깅 레벨 조정 (중요 정보만)
텔레그램 알림 설정 재확인
자동 분석 시간 간격 재설정

안전장치 추가:
# 주문 금액 제한
MAX_ORDER_VALUE = 1000  # USDT
MAX_LEVERAGE = 10
MAX_POSITION_SIZE = 30  # %

# 손실 제한
MAX_DAILY_LOSS = 5  # %
MAX_DRAWDOWN = 10  # %