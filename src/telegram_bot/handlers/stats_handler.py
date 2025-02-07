import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from datetime import datetime, timedelta
from typing import List, Dict
from services.trade_history_service import TradeHistoryService
from telegram_bot.formatters.stats_formatter import StatsFormatter
from telegram_bot.handlers.base_handler import BaseHandler

logger = logging.getLogger(__name__)

class StatsHandler(BaseHandler):
    def __init__(self, bot):
        super().__init__(bot)
        self.trade_history_service = bot.trade_history_service
        self.formatter = StatsFormatter()

    async def daily_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """일일 거래 통계 조회"""
        try:
            # 오늘 날짜의 포지션 조회
            today = datetime.now().strftime('%Y%m%d')
            positions = self.trade_history_service.get_daily_positions(today)
            
            # 통계 메시지 생성
            message = self.formatter.format_daily_stats(positions)
            
            # 메시지 전송
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"일일 통계 조회 중 오류: {str(e)}")
            await update.message.reply_text("통계 조회 중 오류가 발생했습니다.")

    async def monthly_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """월간 거래 통계 조회"""
        try:
            # 이번 달 포지션 조회
            current_month = datetime.now().strftime('%Y%m')
            positions = self.trade_history_service.get_monthly_positions(current_month)
            
            # 통계 메시지 생성
            message = self.formatter.format_monthly_stats(positions)
            
            # 메시지 전송
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"월간 통계 조회 중 오류: {str(e)}")
            await update.message.reply_text("통계 조회 중 오류가 발생했습니다.")

    def get_handlers(self):
        """핸들러 리스트 반환"""
        return [
            CommandHandler('daily', self.daily_stats),
            CommandHandler('monthly', self.monthly_stats)
        ]

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """통계 명령어 처리"""
        if not await self.check_admin(update):
            return
            
        try:
            # 기본값 90일
            days = 90
            
            # 인자가 있으면 파싱
            if context.args:
                try:
                    days = int(context.args[0])
                    if days <= 0 or days > 90:
                        await self.send_message("1-90일 사이의 기간을 입력해주세요 (예: /stats 30)", update.effective_chat.id)
                        return
                except ValueError:
                    await self.send_message("올바른 일수를 입력해주세요 (예: /stats 30)", update.effective_chat.id)
                    return

            # 날짜 계산
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # 해당 기간의 포지션 조회
            positions = self.trade_history_service.get_positions_by_date_range(
                start_date.strftime('%Y%m%d'),
                end_date.strftime('%Y%m%d')
            )
            
            if not positions:
                # 데이터가 있는 기간 확인
                all_positions = self.trade_history_service.get_positions_by_date_range(
                    "20241101",  # 데이터 시작일
                    end_date.strftime('%Y%m%d')
                )
                if all_positions:
                    first_date = datetime.fromtimestamp(min(p['timestamp'] for p in all_positions)/1000)
                    last_date = datetime.fromtimestamp(max(p['timestamp'] for p in all_positions)/1000)
                    await self.send_message(
                        f"요청하신 기간의 거래 내역이 없습니다.\n"
                        f"데이터 보유 기간: {first_date.strftime('%Y-%m-%d')} ~ {last_date.strftime('%Y-%m-%d')}", 
                        update.effective_chat.id
                    )
                else:
                    await self.send_message("거래 내역이 없습니다.", update.effective_chat.id)
                return

            # 포지션 데이터 검증 및 중복 제거
            unique_positions = {}
            for p in positions:
                position_id = p['id']
                if position_id not in unique_positions:
                    unique_positions[position_id] = p

            positions = list(unique_positions.values())
            
            # 롱/숏 분석 (개선된 버전)
            long_positions = [p for p in positions if p.get('position_side') == 'Long']
            short_positions = [p for p in positions if p.get('position_side') == 'Short']
            
            long_pnl = sum(float(p['pnl']) for p in long_positions)
            short_pnl = sum(float(p['pnl']) for p in short_positions)
            
            # 상세 통계 계산
            long_wins = len([p for p in long_positions if float(p['pnl']) > 0])
            short_wins = len([p for p in short_positions if float(p['pnl']) > 0])
            
            long_win_rate = (long_wins / len(long_positions) * 100) if long_positions else 0
            short_win_rate = (short_wins / len(short_positions) * 100) if short_positions else 0
            
            # 디버그 로그 추가
            logger.info("=== 포지션 분석 시작 ===")
            logger.info(f"원본 데이터 수: {len(positions)}")
            logger.info(f"중복 제거 후: {len(unique_positions)}")
            logger.info(f"롱 포지션: {len(long_positions)}")  # 이제 117개가 나와야 함
            logger.info(f"숏 포지션: {len(short_positions)}")  # 이제 12개가 나와야 함
            logger.info("=== 포지션 샘플 ===")
            if positions:
                sample = positions[0]
                logger.info(f"ID: {sample['id']}")
                logger.info(f"Side: {sample['side']}")
                logger.info(f"Entry: {sample['entry_price']}")
                logger.info(f"Exit: {sample['exit_price']}")
                logger.info(f"PNL: {sample['pnl']}")
            logger.info("==================")
            
            # 통계 계산
            total_pnl = sum(float(p['pnl']) for p in positions)
            win_trades = len([p for p in positions if float(p['pnl']) > 0])
            total_trades = len(positions)
            win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0
            
            # 최대 수익/손실 계산
            max_profit = max((float(p['pnl']) for p in positions), default=0)
            max_loss = min((float(p['pnl']) for p in positions), default=0)
            
            # 연속 손익
            max_win_streak = 0
            max_loss_streak = 0
            current_win_streak = 0
            current_loss_streak = 0
            
            sorted_positions = sorted(positions, key=lambda x: x['timestamp'])
            for position in sorted_positions:
                pnl = float(position['pnl'])
                if pnl > 0:
                    current_win_streak += 1
                    current_loss_streak = 0
                    max_win_streak = max(max_win_streak, current_win_streak)
                else:
                    current_loss_streak += 1
                    current_win_streak = 0
                    max_loss_streak = max(max_loss_streak, current_loss_streak)

            # 레버리지별 분석
            leverage_stats = {}
            for position in positions:
                lev = str(position['leverage']) + 'x'
                if lev not in leverage_stats:
                    leverage_stats[lev] = {'count': 0, 'pnl': 0}
                leverage_stats[lev]['count'] += 1
                leverage_stats[lev]['pnl'] += float(position['pnl'])

            # 일별 수익 계산
            daily_pnl = {}
            for position in positions:
                date = datetime.fromtimestamp(int(position['timestamp'])/1000).strftime('%Y-%m-%d')
                daily_pnl[date] = daily_pnl.get(date, 0) + float(position['pnl'])

            message = (
                f"📊 최근 {days}일 거래 통계\n"
                f"({start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')})\n\n"
                f"💰 총 손익: {total_pnl:.2f} USDT\n"
                f"📈 전체 승률: {win_rate:.1f}% ({win_trades}/{total_trades})\n\n"
                f"📊 포지션 분석:\n"
                f"• 롱: {len(long_positions)}건, 승률 {long_win_rate:.1f}%\n"
                f"  수익: {long_pnl:.2f} USDT\n"
                f"• 숏: {len(short_positions)}건, 승률 {short_win_rate:.1f}%\n"
                f"  수익: {short_pnl:.2f} USDT\n"
                f"🔥 최대 연승: {max_win_streak}회\n"
                f"💧 최대 연패: {max_loss_streak}회\n\n"
                f"📊 포지션 분석:\n"
                f"• 롱: {len(long_positions)}건 ({long_pnl:.2f} USDT)\n"
                f"• 숏: {len(short_positions)}건 ({short_pnl:.2f} USDT)\n\n"
                f"💎 수익/손실:\n"
                f"• 최대 수익: {max_profit:.2f} USDT\n"
                f"• 최대 손실: {max_loss:.2f} USDT\n"
                f"• 평균 수익: {total_pnl/total_trades:.2f} USDT\n\n"
                f"⚡ 레버리지 분석:\n"
            )

            # 레버리지별 통계 추가
            for lev, stats in sorted(leverage_stats.items()):
                message += f"• {lev}: {stats['count']}건 ({stats['pnl']:.2f} USDT)\n"

            message += f"\n📊 일평균 거래량: {total_trades/days:.1f}회\n\n"
            message += "📅 일별 손익 (최근 7일):\n"

            # 최근 7일 손익 추가
            recent_days = sorted(daily_pnl.items())[-7:]
            for date, pnl in recent_days:
                emoji = "📈" if pnl > 0 else "📉"
                message += f"{emoji} {date}: {pnl:.2f} USDT\n"

            await self.send_message(message, update.effective_chat.id)

        except Exception as e:
            logger.error(f"통계 처리 중 오류: {str(e)}")
            await self.send_message("통계 조회 중 오류가 발생했습니다.", update.effective_chat.id) 