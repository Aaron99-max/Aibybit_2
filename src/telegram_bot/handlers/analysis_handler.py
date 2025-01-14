import os
import json
import logging
import asyncio
from .base_handler import BaseHandler
import traceback
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from typing import Dict, Optional, List
from ..formatters.storage_formatter import StorageFormatter
import time
from ..utils.time_utils import TimeUtils
from datetime import datetime

logger = logging.getLogger(__name__)

class AnalysisHandler(BaseHandler):
    def __init__(self, bot, ai_trader, market_data_service, storage_formatter, analysis_formatter):
        super().__init__(bot)
        self.ai_trader = ai_trader
        self.market_data_service = market_data_service
        self.storage_formatter = storage_formatter
        self.analysis_formatter = analysis_formatter
        self.time_utils = TimeUtils()
        self.analysis_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'analysis_data')
        os.makedirs(self.analysis_dir, exist_ok=True)

    async def handle_analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """분석 명령어 처리"""
        try:
            if not update.effective_chat:
                return
                
            chat_id = update.effective_chat.id
            
            # 파라미터 검증
            if not context.args or len(context.args) < 1:
                await self.show_timeframe_help(chat_id)
                return
            
            timeframe = context.args[0].lower()
            
            # 전체 분석
            if timeframe == 'all':
                await self.handle_analyze_all(chat_id)
                return
            
            # 단일 시간대 분석
            if timeframe in ['15m', '1h', '4h', '1d']:
                await self.handle_analyze_single(timeframe, chat_id)
                return
            
            # Final 분석
            if timeframe == 'final':
                await self.handle_analyze_final(chat_id)
                return
            
            await self.show_timeframe_help(chat_id)
            
        except Exception as e:
            logger.error(f"분석 명령어 처리 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            if update.effective_chat:
                await self.send_message("❌ 분석 중 오류가 발생했습니다", update.effective_chat.id)

    async def handle_last(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """마지막 분석 결과 조회"""
        try:
            if not update.effective_chat:
                return
                
            chat_id = update.effective_chat.id
            
            # 시간프레임 파싱
            timeframe = context.args[0] if context.args else None
            
            if not timeframe:
                await self.show_timeframe_help(chat_id)
                return

            if timeframe == 'all':
                await self.handle_last_all(chat_id)
            elif timeframe in ['15m', '1h', '4h', '1d']:
                await self.handle_last_single(timeframe, chat_id)
            elif timeframe == 'final':
                await self.handle_last_final(chat_id)
            else:
                await self.show_timeframe_help(chat_id)
                
        except Exception as e:
            logger.error(f"마지막 분석 결과 조회 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            if update.effective_chat:
                await self.send_message("❌ 분석 결과 조회 중 오류가 발생했습니다", update.effective_chat.id)

    async def handle_analyze_all(self, chat_id: int):
        """모든 시간대 분석 실행"""
        try:
            # 순서대로 분석 실행: 15m -> 1h -> 4h -> 1d
            timeframes = ['15m', '1h', '4h', '1d']
            for timeframe in timeframes:
                await self.handle_analyze_single(timeframe, chat_id)
                await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"전체 분석 중 오류: {str(e)}")
            await self.send_message("❌ 전체 분석 중 오류가 발생했습니다", chat_id)

    async def handle_analyze_single(self, timeframe: str, chat_id: int):
        """단일 시간대 분석 처리"""
        try:
            # 분석 시작 메시지 전송
            await self.send_message(f"🔄 {timeframe} 시간대 분석 시작...", chat_id)
            
            # OHLCV 데이터 조회
            klines = await self.market_data_service.get_ohlcv('BTCUSDT', timeframe)
            if not klines:
                await self.send_message("❌ 시장 데이터 조회 실패", chat_id)
                return
            
            # 분석 실행
            analysis_result = await self.ai_trader.analyze_market(timeframe, klines)
            if analysis_result:
                # 분석 결과 메시지 전송 (수동분석)
                message = self.analysis_formatter.format_analysis_result(
                    analysis_result, 
                    timeframe,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
                )
                await self.send_message(message, chat_id)
                
                # 4시간봉 분석이 완료되면 final 분석 실행
                if timeframe == '4h':
                    await asyncio.sleep(1)  # 잠시 대기
                    await self.handle_analyze_final(chat_id)
                
            else:
                await self.send_message("❌ 분석 실패", chat_id)
                
        except Exception as e:
            logger.error(f"{timeframe} 분석 중 오류: {str(e)}")
            await self.send_message(f"❌ {timeframe} 분석 중 오류가 발생했습니다", chat_id)

    async def handle_analyze_final(self, chat_id: int):
        """Final 분석 처리"""
        try:
            logger.info("\n=== 수동 Final 분석 시작 ===")
            
            # 저장된 분석 결과 로드
            analyses = {}
            for timeframe in ['15m', '1h', '4h', '1d']:
                analysis_data = self.storage_formatter.load_analysis(timeframe)
                if analysis_data:
                    analyses[timeframe] = analysis_data
                    logger.info(f"{timeframe} 분석 데이터: {json.dumps(analysis_data, indent=2)}")

            # Final 분석 실행
            final_analysis = await self.ai_trader.create_final_analysis(analyses)
            logger.info(f"Final 분석 결과: {json.dumps(final_analysis, indent=2)}")
            
            if final_analysis:
                # 분석 결과 메시지 전송 추가
                message = self.analysis_formatter.format_analysis_result(
                    final_analysis, 
                    'final',
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
                )
                await self.send_message(message, chat_id)
                
                # 자동매매 실행
                trade_result = await self.ai_trader.execute_trade(final_analysis)
                logger.info(f"매매 실행 결과: {trade_result}")

        except Exception as e:
            logger.error(f"Final 분석 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            await self.send_message("❌ Final 분석 중 오류가 발생했습니다", chat_id)

    async def handle_last_all(self, chat_id: int):
        """모든 시간대의 마지막 분석 결과 조회"""
        try:
            for timeframe in ['15m', '1h', '4h', '1d', 'final']:
                analysis = self.storage_formatter.load_analysis(timeframe)
                if analysis:
                    # 분석 결과 메시지 전송 (시간 정보는 format_analysis_result에서 처리)
                    message = self.analysis_formatter.format_analysis_result(analysis, timeframe)
                    await self.send_message(message, chat_id)
                    await asyncio.sleep(0.5)  # 메시지 간 간격 추가
                else:
                    await self.send_message(f"❌ {timeframe} 분석 결과가 없습니다", chat_id)
        except Exception as e:
            logger.error(f"모든 분석 결과 조회 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            await self.send_message("❌ 분석 결과 조회 실패", chat_id)

    async def handle_last_single(self, timeframe: str, chat_id: int):
        """단일 시간대의 마지막 분석 결과 조회"""
        try:
            # 저장된 분석 결과 로드
            analysis = self.storage_formatter.load_analysis(timeframe)
            if not analysis:
                await self.send_message(f"❌ 저장된 {timeframe} 분석 결과가 없습니다", chat_id)
                return

            # 저장 시간 가져오기
            saved_time = self.storage_formatter.get_analysis_time(timeframe)
            
            # 분석 결과 포맷팅 및 전송
            message = self.analysis_formatter.format_analysis_result(
                analysis, timeframe, saved_time
            )
            await self.send_message(message, chat_id)

        except Exception as e:
            logger.error(f"마지막 분석 결과 조회 중 오류: {str(e)}")
            await self.send_message("❌ 분석 결과 조회 중 오류가 발생했습니다", chat_id)

    async def handle_last_final(self, chat_id: int):
        """마지막 Final 분석 결과 조회"""
        try:
            # 저장된 분석 결과 로드
            final_analysis = self.storage_formatter.load_analysis('final')
            if not final_analysis:
                await self.send_message("❌ Final 분석 결과가 없습니다", chat_id)
                return

            # 분석 시간 조회
            saved_time = final_analysis.get('saved_at')
            if not saved_time:
                saved_time = self.storage_formatter.get_analysis_time('final')
            
            # 분석 결과 메시지 전송
            message = self.analysis_formatter.format_analysis_result(final_analysis, 'final', saved_time)
            await self.send_message(message, chat_id)
        except Exception as e:
            logger.error(f"Final 분석 결과 조회 중 오류: {str(e)}")
            logger.error(traceback.format_exc())
            await self.send_message("❌ Final 분석 결과 조회 실패", chat_id)

    async def handle_final_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """최종 분석 결과 처리 및 자동매매 실행"""
        try:
            # 분석 결과 가져오기
            analysis_result = self.analysis_service.get_final_analysis()
            if not analysis_result:
                await update.message.reply_text("최 분석 결과가 없습니다.")
                return

            logger.info(f"Final 분석 결과: {analysis_result}")  # 전체 분석 결과 로깅

            # 방향 결정
            direction = analysis_result.get('direction', '').lower()
            if direction == 'bullish':
                side = 'LONG'
            elif direction == 'bearish':
                side = 'SHORT'
            else:
                await update.message.reply_text(f"못된 분석 방향: {direction}")
                return

            # 레버리지 처리
            try:
                leverage = int(analysis_result.get('leverage', 2))
                if leverage <= 0 or leverage > 100:  # 레버리지 범위 검증
                    logger.error(f"잘못된 레버리지 값: {leverage}")
                    leverage = 2  # 기본값 사용
            except (TypeError, ValueError) as e:
                logger.error(f"레버리지 변환 오류: {e}")
                leverage = 2  # 기본값 사용

            # 매매 신호 생성
            trading_signal = {
                'symbol': 'BTCUSDT',
                'side': side,
                'leverage': leverage,
                'size': float(analysis_result.get('size', 0.001)),
                'entry_price': float(analysis_result.get('entry_price', 0))
            }

            logger.info(f"생성된 매매 신호: {trading_signal}")  # 매매 신호 로깅

            # 필수 값 검증
            if not all([
                trading_signal['leverage'] > 0,
                trading_signal['size'] > 0,
                trading_signal['entry_price'] > 0
            ]):
                await update.message.reply_text("분석 결과에 필요한 매매 정보가 부족합니다.")
                return

            # 포지션 관리 실행
            success = await self.position_service.handle_position_for_signal(trading_signal)
            
            # 결과 메시지 전송
            if success:
                message = "✅ 자동매매 주문이 성공적으로 실행되었습니다.\n"
                message += f"방향: {'롱' if trading_signal['side'] == 'LONG' else '숏'}\n"
                message += f"레버리지: {trading_signal['leverage']}x\n"
                message += f"크기: {trading_signal['size']} BTC\n"
                message += f"진입가격: {trading_signal['entry_price']} USDT"
            else:
                message = "❌ 자동매매 주문 실행 중 오류가 발생했습니다."

            await update.message.reply_text(message)

        except Exception as e:
            logger.error(f"자동매매 처리 중 오류: {str(e)}")
            await update.message.reply_text("자동매매 처리 중 오류가 발생했습니다.")

    async def send_analysis_result(self, analysis: Dict, timeframe: str, chat_id: int):
        try:
            # 저장 시간 포맷 개선
            saved_time = ""
            if timeframe:
                saved_time = self.storage_formatter.get_analysis_time(timeframe)
            
            # 분석 결과가 없는 경우 리턴
            if not analysis:
                await self.send_message(f"❌ {timeframe} 분석 결과가 없습니다", chat_id)
                return
            
            # 분석 결과 포맷팅 전송
            message = self.analysis_formatter.format_analysis_result(
                analysis, timeframe, saved_time
            )
            
            # 긴 메시지 분할 처리
            if len(message) > 4096:
                chunks = [message[i:i+4096] for i in range(0, len(message), 4096)]
                for chunk in chunks:
                    await self.send_message(chunk, chat_id)
            else:
                await self.send_message(message, chat_id)
        except Exception as e:
            logger.error(f"분석 결과 전송 중 오류: {e}")
            await self.send_message("❌ 분석 결과 전송 실패", chat_id)

    async def show_timeframe_help(self, chat_id: int):
        """시간프레임 도움말 표시"""
        help_message = (
            "시간프레임을 지정해주세요:\n"
            "/analyze 15m - 15분 분석\n"
            "/analyze 1h - 1시간봉 분석\n"
            "/analyze 4h - 4시간봉 분석\n"
            "/analyze 1d - 일봉 분석\n"
            "/analyze final - 최종 분석\n"
            "/analyze all - 전체 분석"
        )
        await self.send_message(help_message, chat_id)

    async def handle_analysis(self, timeframe: str, chat_id: int) -> bool:
        """분석 요 처리"""
        try:
            # 분석 실행
            analysis = await self.ai_trader.analyze_market(timeframe)
            if not analysis:
                await self.telegram_bot.send_message("분석 실패", chat_id)
                return False

            # 새로운 포맷으로 분석 결과 전송
            await self.telegram_bot.send_analysis_notification(analysis, timeframe)
            
            # 4시간봉 분석이 완료되면 final 분석 실행
            if timeframe == '4h':
                await asyncio.sleep(1)  # final 분석 전 잠 대기
                await self.handle_analyze_final(chat_id)
            
            return True
            
        except Exception as e:
            logger.error(f"분석 처리 중 오류: {str(e)}")
            await self.telegram_bot.send_message("❌ 분석 처리 중 오류가 발생했습니다", chat_id)
            return False

    async def execute_auto_trading(self, analysis: Dict) -> bool:
        """자동매매 실행"""
        try:
            if not analysis.get('trading_strategy', {}).get('auto_trading', {}).get('enabled'):
                logger.info("자동매매가 비활성화되어 있음")
                return False

            # 거래 실행
            trade_result = await self.ai_trader.execute_trade(analysis)
            if trade_result:
                await self.telegram_bot.send_trade_notification(trade_result, analysis)
                return True
            return False

        except Exception as e:
            logger.error(f"자동매매 실행 중 오류: {str(e)}")
            return False

    def _validate_analysis_response(self, response: Dict) -> bool:
        """GPT 응답 검증"""
        try:
            required_paths = [
                ['market_summary', 'market_phase'],
                ['market_summary', 'confidence'],
                ['trading_strategy', 'position_suggestion'],
                ['trading_strategy', 'auto_trading', 'enabled']
            ]
            
            for path in required_paths:
                current = response
                for key in path:
                    if not isinstance(current, dict) or key not in current:
                        logger.error(f"필수 경로 누락: {' -> '.join(path)}")
                        return False
                    current = current[key]
                    
            return True
            
        except Exception as e:
            logger.error(f"응답 검증 중 오류: {str(e)}")
            return False

    async def handle_auto_analysis(self, timeframe: str):
        """자동 분석 처리"""
        try:
            # OHLCV 데이터 조회
            klines = await self.market_data_service.get_ohlcv('BTCUSDT', timeframe)
            if not klines:
                logger.error("시장 데이터 조회 실패")
                return
            
            # 분석 실행
            analysis = await self.ai_trader.analyze_market(timeframe, klines)
            if analysis:
                # 분석 결과 메시지 전송 (자동분석)
                message = self.analysis_formatter.format_analysis_result(
                    analysis,
                    timeframe,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
                )
                await self.send_message(message, self.config.CHAT_ID)
        except Exception as e:
            logger.error(f"자동 분석 처리 중 오류: {str(e)}")

    async def handle_analysis_result(self, analysis: Dict, timeframe: str, chat_id: Optional[int] = None):
        """분석 결과 통합 처리"""
        try:
            # 1. 분석 결과 저장
            self.storage_formatter.save_analysis(analysis, timeframe)
            
            # 2. 메시지 포맷팅
            message = self.analysis_formatter.format_analysis_result(
                analysis, 
                timeframe,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
            )
            
            # 3. 메시지 전송
            if chat_id:
                await self.send_message(message, chat_id)
            else:
                await self.bot.send_message_to_all(message)
            
            # 4. final 분석인 경우 자동매매 체크
            if timeframe == 'final':
                auto_trading = analysis.get('trading_strategy', {}).get('auto_trading', {})
                if auto_trading.get('enabled'):
                    await self.ai_trader.execute_auto_trading(analysis)
                    logger.info("자동매매 신호 처리 완료")
                else:
                    confidence_data = {
                        'confidence': auto_trading.get('confidence', 0),
                        'strength': auto_trading.get('strength', 0),
                        'reason': auto_trading.get('reason', '조건 미충족')
                    }
                    confidence_message = "🤖 자동매매 비활성화\n" + \
                        f"• 신뢰도: {confidence_data['confidence']}%\n" + \
                        f"• 강도: {confidence_data['strength']}%\n" + \
                        f"• 사유: {confidence_data['reason']}"
                    
                    if chat_id:
                        await self.send_message(confidence_message, chat_id)
                    else:
                        await self.bot.send_message_to_all(confidence_message)
                        
        except Exception as e:
            logger.error(f"분석 결과 처리 중 오류: {str(e)}")

    async def handle_analyze_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """수동 분석 명령어 처리"""
        try:
            # 통합 분석 실행
            final_analysis = await self.bot.ai_trader.run_complete_analysis()
            if final_analysis:
                await self.handle_analysis_result(
                    analysis=final_analysis,
                    timeframe='final',
                    chat_id=update.effective_chat.id
                )
                
        except Exception as e:
            logger.error(f"분석 명령어 처리 중 오류: {str(e)}")

    async def _send_divergence_alert(self, divergence: Dict, timeframe: str, chat_id: Optional[int] = None):
        """다이버전스 알림 전송"""
        try:
            if not divergence or divergence.get('type') == '없음':
                return
            
            # 알림 메시지 생성
            message = (
                f"🔄 다이버전스 감지! ({timeframe})\n"
                f"• 유형: {divergence.get('type')}\n"
                f"• 설명: {divergence.get('description')}"
            )
            
            await self.send_message(message, chat_id)
            
        except Exception as e:
            logger.error(f"다이버전스 알림 전송 중 오류: {str(e)}")

    def _format_analysis_message(self, analysis: Dict, timeframe: str = None) -> str:
        """분석 결과 메시지 포맷팅"""
        try:
            if not analysis:
                return "분석 데이터가 없습니다."

            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
            
            # 시간대 표시
            timeframe_text = f"{timeframe}봉" if timeframe else "Final"
            
            message_parts = [
                f"📊 {timeframe_text} 분석 ({current_time})\n",
                "\n🌍 시장 요약:",
                f"• 시장 단계: {analysis['market_summary']['market_phase']}",
                f"• 전반적 심리: {analysis['market_summary']['overall_sentiment']}",
                f"• 단기 심리: {analysis['market_summary']['short_term_sentiment']}",
                f"• 거래량: {analysis['market_summary']['volume_trend']}",
                f"• 리스크: {analysis['market_summary'].get('risk_level', '정보 없음')}",
                f"• 신뢰도: {analysis['market_summary'].get('confidence', 0)}%",
                
                "\n📈 기술적 분석:",
                f"• 추세: {analysis['technical_analysis']['trend']}",
                f"• 강도: {analysis['technical_analysis']['strength']:.2f}",
                f"• RSI: {analysis['technical_analysis']['indicators']['rsi']:.2f}",
                f"• MACD: {analysis['technical_analysis']['indicators']['macd']}",
                f"• 볼린저밴드: {analysis['technical_analysis']['indicators']['bollinger']}"
            ]

            # 다이버전스 정보가 있는 경우
            if 'divergence' in analysis['technical_analysis']['indicators']:
                div_info = analysis['technical_analysis']['indicators']['divergence']
                if div_info['type'] != '없음':
                    message_parts.extend([
                        "\n🔄 다이버전스:",
                        f"• 유형: {div_info['type']}",
                        f"• 설명: {div_info['description']}"
                    ])

            # 거래 전략
            strategy = analysis['trading_strategy']
            entry_points = strategy.get('entry_points', [])
            take_profits = strategy.get('takeProfit', [])
            
            message_parts.extend([
                "\n💡 거래 전략:",
                f"• 포지션: {strategy.get('position_suggestion', '관망')}",
                f"• 진입가: ${entry_points[0]:,.1f}" if entry_points else "• 진입가: 정보 없음",
                f"• 손절가: ${strategy.get('stopLoss', 0):,.1f}",
                f"• 목표가: {', '.join([f'${tp:,.1f}' for tp in take_profits])}" if take_profits else "• 목표가: 정보 없음",
                f"• 레버리지: {strategy.get('leverage', 0)}x",
                f"• 포지션 크기: {strategy.get('position_size', 0)}%"
            ])

            # 자동매매 상태
            message_parts.extend([
                "\n🤖 자동매매:",
                "• 상태: 비활성화",
                "• 사유: 정보 없음"
            ])

            return "\n".join(message_parts)

        except Exception as e:
            logger.error(f"분석 메시지 포맷팅 중 오류: {str(e)}")
            return "분석 결과 포맷팅 중 오류가 발생했습니다."
