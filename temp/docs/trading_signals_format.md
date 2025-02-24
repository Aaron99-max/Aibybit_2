# Trading Signals 표준 형식

```python
trading_signals = {
    'trading_signals': {
        'auto_trading_enabled': bool,  # 자동매매 활성화 여부
        'primary_signal': {
            'action': str,  # '매수' 또는 '매도'
        },
        'entry_price': float,  # 진입가격
        'stop_loss': float,    # 손절가
        'take_profit': float,  # 목표가
        'recommended_leverage': int,   # 레버리지
        'position_size': float  # 포지션 크기
    },
    '신뢰도': float  # 0-100 사이의 신뢰도
} 