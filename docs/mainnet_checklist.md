# 메인넷 이전 체크리스트

## 1. 거래 안전성 체크
- [ ] 레버리지 한도 설정 (최대 100x)
- [ ] 포지션 크기 한도 설정 (계좌 크기 대비 %)
- [ ] 손절가/익절가 필수 설정 확인
- [ ] 주문 실패 시 재시도 로직 확인
- [ ] 에러 발생 시 알림 기능 확인

## 2. 자동매매 로직 검증
- [ ] 포지션 방향 변경 시 청산 후 재진입
- [ ] 같은 방향 시 레버리지/크기 조정
- [ ] 포지션 크기 누적 방지
- [ ] 자동매매 활성화/비활성화 기능
- [ ] 4시간봉 분석 시간 정확성 (1, 5, 9, 13, 17, 21시)

## 3. 설정 파일 점검
- [ ] API 키/시크릿 환경변수 설정
- [ ] 텔레그램 봇 토큰 설정
- [ ] 채팅방 ID 설정 (관리자/알림방)
- [ ] 거래 설정 (심볼, 레버리지 등)
- [ ] 로깅 레벨 및 경로 설정

## 4. 모니터링 시스템
- [ ] 에러 로깅 시스템 확인
- [ ] 텔레그램 알림 기능 검증
- [ ] 포지션/잔고 모니터링
- [ ] 서버 상태 모니터링
- [ ] 자동 재시작 기능

## 5. 비상 시나리오 대비
- [ ] 긴급 중지 명령어 (/stop)
- [ ] 수동 청산 기능
- [ ] API 연결 끊김 대응
- [ ] 서버 다운 시 복구 절차
- [ ] 백업 시스템 구축

## 6. 최종 테스트
- [ ] 전체 시나리오 테스트 완료
  - [ ] 새 포지션 진입
  - [ ] 포지션 크기 증가/감소
  - [ ] 레버리지 변경
  - [ ] 청산 및 재진입
- [ ] 24시간 안정성 테스트
- [ ] 스트레스 테스트 (급격한 가격 변동 시)

## 7. 문서화
- [ ] API 키 백업
- [ ] 설정 파일 백업
- [ ] 실행/정지 절차 문서화
- [ ] 문제 해결 가이드
- [ ] 연락처 및 비상 연락망

## 8. 운영 준비
- [ ] 서버 자원 확인 (CPU, 메모리, 디스크)
- [ ] 네트워크 안정성 확인
- [ ] 백업 서버 준비 (선택사항)
- [ ] 모니터링 도구 설정
- [ ] 알림 설정 최종 확인

## 주의사항
1. 초기에는 작은 금액으로 시작
2. 단계적으로 거래 크기 증가
3. 24시간 모니터링 가능한 상태에서 시작
4. 문제 발생 시 즉시 중지 가능하도록 준비
5. 정기적인 로그 확인 및 백업 실행 