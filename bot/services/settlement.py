"""
Settlement Engine -- Automatically settles bets when match results arrive.
The brain of the betting system. Handles payouts, refunds, and edge cases.
"""
import logging
from typing import Dict, Any, List, Optional
from bot.database import db
from bot.constants import RoomStatus, TxnType, MatchStatus
from bot.services.cricket_api import cricket_api
from bot.config import config
logger = logging.getLogger(__name__)
class SettlementEngine:
   """Processes match results and settles all related rooms."""

   async def process_match_result(
     self,
     match_id: str,
     bot: Any = None,
   ) -> Dict[str, Any]:
     """
     Process a completed match and settle all rooms.
     Returns settlement report.
     """
     report = {
       "match_id": match_id,
       "settled": 0,
       "refunded": 0,
       "errors": 0,
       "total_payout": 0,
       "total_commission": 0,
     }
     try:
       # Get match data
       match = await db.get_match_by_api_id(match_id)
       if not match:
          logger.warning("Match %s not found in DB", match_id)
          return report
       # Get latest data from API
       api_data = await cricket_api.get_match_info(match_id)
       if not api_data:
          logger.warning("Could not fetch API data for match %s", match_id)
          return report
       # Update match in DB
       api_data["status"] = MatchStatus.COMPLETED.value
       await db.upsert_match(api_data)
       # Get all locked rooms for this match
       db_match = await db.get_match_by_api_id(match_id)
       if not db_match:
          return report
       rooms = await db.get_rooms_for_match(db_match["id"])
       logger.info(
          "Processing %d rooms for match %s",
          len(rooms), match_id
       )




       for room in rooms:
          try:
            await self._settle_room(room, api_data, bot, report)
          except Exception as e:
            logger.error(
              "Error settling room %s: %s",
              room.get("id"), e,
              exc_info=True,
            )
            report["errors"] += 1
       logger.info(
          "Settlement complete for match %s: %s",
          match_id, report
       )
     except Exception as e:
       logger.error(
          "Settlement engine error for match %s: %s",
          match_id, e, exc_info=True,
       )
     return report
   async def _settle_room(
     self,
     room: Dict[str, Any],
     match_data: Dict[str, Any],
     bot: Any,
     report: Dict[str, Any],
   ) -> None:
     """Settle a single room."""
     room_id = room["id"]
     creator_id = room["creator_id"]
     joiner_id = room.get("joiner_id")
     bet_type = room["bet_type"]
     bet_amount = room["bet_amount"]
     win_amount = room["win_amount"]
     creator_pick = room["creator_pick"]
     joiner_pick = room.get("joiner_pick", "")
     # If no joiner, refund creator
     if not joiner_id:
       await self._refund_room(room, "No opponent joined", bot)
       report["refunded"] += 1
       return
     # Determine winner
     creator_won = cricket_api.determine_winner(
       match_data, bet_type, creator_pick
     )
     if creator_won is None:
       # Can't determine -- check if match was abandoned
       status_text = match_data.get("match_status_text", "").lower()
       if "abandon" in status_text or "no result" in status_text:
          await self._refund_room(room, "Match abandoned", bot)
          report["refunded"] += 1
          return
       else:
          logger.warning(
            "Cannot determine winner for room %s, "
            "bet_type=%s, pick=%s",
            room_id, bet_type, creator_pick
          )
          return
     # Determine winner and loser
     if creator_won:
       winner_id = creator_id
       loser_id = joiner_id
     else:



       winner_id = joiner_id
       loser_id = creator_id
     result_text = match_data.get("match_status_text", "Match completed")

     # Settle the room in DB
     settled = await db.settle_room(room_id, winner_id, result_text)
     if not settled:
       logger.error("Failed to settle room %s in DB", room_id)
       report["errors"] += 1
       return
     # Pay the winner
     success, new_balance = await db.credit_wallet(
       winner_id,
       win_amount,
       TxnType.BET_WON,
       f"Won bet on {match_data.get('name', 'match')}",
       reference_id=room_id,
     )
     if not success:
       logger.critical(
          "CRITICAL: Failed to pay winner %d for room %s!",
          winner_id, room_id
       )
       report["errors"] += 1
       return
     # Update winner stats
     user = await db.get_user(winner_id)
     if user:
       await db.update_user(winner_id, {
          "wins_count": user.get("wins_count", 0) + 1,
          "total_winnings": user.get("total_winnings", 0) + win_amount,
       })
     # Calculate commission
     pool = bet_amount * 2
     commission = pool - win_amount
     report["total_commission"] += commission
     report["total_payout"] += win_amount
     report["settled"] += 1
     # Notify players via bot
     if bot:
       await self._notify_settlement(
          bot, winner_id, loser_id,
          match_data, room, win_amount,
          result_text, new_balance,
       )
   async def _refund_room(
     self,
     room: Dict[str, Any],
     reason: str,
     bot: Any,
   ) -> None:
     """Refund all participants in a room."""
     room_id = room["id"]
     creator_id = room["creator_id"]
     joiner_id = room.get("joiner_id")
     bet_amount = room["bet_amount"]
     # Cancel the room
     await db.cancel_room(room_id, reason)
     # Refund creator
     await db.credit_wallet(
       creator_id,
       bet_amount,
       TxnType.BET_REFUND,
       f"Refund: {reason}",



       reference_id=room_id,
     )
     # Refund joiner if exists
     if joiner_id:
       await db.credit_wallet(
          joiner_id,
          bet_amount,
          TxnType.BET_REFUND,
          f"Refund: {reason}",
          reference_id=room_id,
       )
     # Notify via bot
     if bot:
       try:
          await bot.send_message(
            chat_id=creator_id,
            text=(
              f"? <b>Bet Refunded</b>\n\n"
              f"? ?{bet_amount} has been returned to your wallet.\n"
              f"? Reason: {reason}\n\n"
              f"? <i>Try another match!</i>"
            ),
            parse_mode="HTML",
          )
       except Exception:
          pass
       if joiner_id:
          try:
            await bot.send_message(
              chat_id=joiner_id,
              text=(
                 f"? <b>Bet Refunded</b>\n\n"
                 f"? ?{bet_amount} has been returned to your wallet.\n"
                 f"? Reason: {reason}\n\n"
                 f"? <i>Try another match!</i>"
              ),
              parse_mode="HTML",
            )
          except Exception:
            pass
   async def _notify_settlement(
     self,
     bot: Any,
     winner_id: int,
     loser_id: int,
     match_data: Dict[str, Any],
     room: Dict[str, Any],
     win_amount: int,
     result_text: str,
     winner_balance: int,
   ) -> None:
     """Notify winner and loser about settlement."""
     from bot.keyboards.betting import build_post_result_keyboard
     match_name = match_data.get("name", "Cricket Match")
     # Notify winner
     try:
       winner_user = await db.get_user(winner_id)
       streak = winner_user.get("wins_count", 0) if winner_user else 0
       await bot.send_message(
          chat_id=winner_id,
          text=(
            f"??? <b>YOU WON!</b> ???\n\n"
            f"? Match: <b>{match_name}</b>\n"
            f"[OK] Result: <b>{result_text}</b>\n"
            f"? You won: <b>?{win_amount}</b>\n\n"
            f"? New Balance: <b>?{winner_balance}</b>\n"



            f"? Total Wins: <b>{streak}</b>\n\n"
            f"? <i>Winners play again! "
            f"Bet now while you're hot!</i> ?"
          ),
          parse_mode="HTML",
          reply_markup=build_post_result_keyboard(),
       )
     except Exception as e:
       logger.error("Failed to notify winner %d: %s", winner_id, e)
     # Notify loser
     try:
       loser_balance = await db.get_balance(loser_id)
       await bot.send_message(
          chat_id=loser_id,
          text=(
            f"? <b>Better luck next time!</b>\n\n"
            f"? Match: <b>{match_name}</b>\n"
            f"[X] Result: <b>{result_text}</b>\n"
            f"? Lost: <b>?{room['bet_amount']}</b>\n\n"
            f"? Balance: <b>?{loser_balance}</b>\n\n"
            f"? <i>Top players lose sometimes too -- "
            f"the comeback is always stronger! ?</i>\n\n"
            f"? <i>Spin the wheel for a free boost!</i>"
          ),
          parse_mode="HTML",
          reply_markup=build_post_result_keyboard(show_spin=True),
       )
     except Exception as e:
       logger.error("Failed to notify loser %d: %s", loser_id, e)
   async def process_expired_rooms(self, bot: Any = None) -> int:
     """Expire stale rooms and refund creators."""
     try:
       expired = await db.expire_stale_rooms(
          config.AUTO_CLOSE_ROOM_MINS
       )
       for room in expired:
          await db.credit_wallet(
            room["creator_id"],
            room["bet_amount"],
            TxnType.BET_REFUND,
            "Room expired -- no opponent",
            reference_id=room["id"],
          )
          if bot:
            try:
              await bot.send_message(
                 chat_id=room["creator_id"],
                 text=(
                   f"? <b>Room Expired</b>\n\n"
                   f"No one joined your ?{room['bet_amount']} bet.\n"
                   f"? ?{room['bet_amount']} refunded to your wallet.\n\n"
                   f"? <i>Try a different match or lower amount "
                   f"for faster matching!</i>"
                 ),
                 parse_mode="HTML",
              )
            except Exception:
              pass
       return len(expired)
     except Exception as e:
       logger.error("process_expired_rooms error: %s", e)
       return 0
# Singleton
settlement_engine = SettlementEngine()
