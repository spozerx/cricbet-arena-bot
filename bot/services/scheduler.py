"""
Scheduler Service -- Background jobs for match syncing,
settlement, room expiry, and engagement notifications.
"""
import logging
from datetime import datetime, timezone
from bot.database import db
from bot.services.cricket_api import cricket_api
from bot.services.settlement import settlement_engine
from bot.constants import MatchStatus
logger = logging.getLogger(__name__)
async def sync_matches_job(context) -> None:
   """
   Sync matches from CricAPI every 2 minutes.
   Updates match status and scores in database.
   """
   try:
     matches = await cricket_api.get_current_matches()
     synced = 0
     completed = []
     for match_data in matches:
       try:
          await db.upsert_match(match_data)
          synced += 1
          # Check for newly completed matches
          if match_data.get("status") == MatchStatus.COMPLETED.value:
            completed.append(match_data["api_match_id"])
       except Exception as e:
          logger.error(
            "Error syncing match %s: %s",
            match_data.get("api_match_id"), e
          )
     logger.info("Synced %d matches, %d completed", synced, len(completed))
     # Settle completed matches
     for api_match_id in completed:
       try:
          report = await settlement_engine.process_match_result(
            api_match_id, bot=context.bot
          )
          if report["settled"] > 0 or report["refunded"] > 0:
            logger.info(
              "Settlement report for %s: %s",
              api_match_id, report
            )
       except Exception as e:
          logger.error(
            "Error settling match %s: %s",
            api_match_id, e
          )
   except Exception as e:
     logger.error("sync_matches_job error: %s", e, exc_info=True)




async def expire_rooms_job(context) -> None:
   """Expire stale rooms every 5 minutes."""
   try:
     count = await settlement_engine.process_expired_rooms(
       bot=context.bot
     )
     if count > 0:
       logger.info("Expired %d stale rooms", count)
   except Exception as e:
     logger.error("expire_rooms_job error: %s", e)
async def engagement_notifications_job(context) -> None:
   """
   Send re-engagement notifications to inactive users.
   Runs every 6 hours.
   """
   try:
     from bot.config import config
     # Get users inactive for 24+ hours
     import datetime as dt
     now = datetime.now(timezone.utc)
     # 24h inactive users
     cutoff_24h = (now - dt.timedelta(hours=24)).isoformat()
     cutoff_72h = (now - dt.timedelta(hours=72)).isoformat()
     cutoff_7d = (now - dt.timedelta(days=7)).isoformat()
     if config.ENGAGEMENT_24H:
       try:
          result = await (
            db.client.table("users")
            .select("telegram_id, first_name")
            .eq("is_banned", False)
            .eq("has_blocked_bot", False)
            .eq("notifications_on", True)
            .lt("last_seen", cutoff_24h)
            .gte("last_seen", cutoff_72h)
            .limit(50)
            .execute()
          )
          for user in (result.data or []):
            try:
              live = await cricket_api.get_current_matches()
              live_count = len([
                 m for m in live
                 if m.get("status") == MatchStatus.LIVE.value
              ])
              await context.bot.send_message(
                 chat_id=user["telegram_id"],
                 text=(
                   f"? Hey {user['first_name']}! "
                   f"You're missing out!\n\n"
                   f"? <b>{live_count}</b> matches live now!\n"
                   f"? Players are winning big today!\n\n"
                   f"? /start to jump back in!"
                 ),
                 parse_mode="HTML",
              )
            except Exception:
              # User blocked bot
              await db.update_user(
                 user["telegram_id"],
                 {"has_blocked_bot": True}
              )
       except Exception as e:
          logger.error("24h engagement error: %s", e)
   except Exception as e:
     logger.error("engagement_notifications_job error: %s", e)



async def daily_bonus_job(context) -> None:
   """
   Give daily free bet to active users.
   Runs once per day at 9 AM IST.
   """
   try:
     from bot.constants import TxnType
     result = await (
       db.client.table("users")
       .select("telegram_id, first_name, streak_days")
       .eq("is_banned", False)
       .eq("has_blocked_bot", False)
       .eq("notifications_on", True)
       .limit(100)
       .execute()
     )
     for user in (result.data or []):
       try:
          from bot.config import config
          amount = config.DAILY_FREE_BET_AMOUNT
          streak = user.get("streak_days", 0)
          # Streak bonus
          bonus_mult = min(
            streak * config.STREAK_BONUS_MULTIPLIER,
            config.MAX_STREAK_BONUS,
          )
          bonus = int(amount * bonus_mult)
          total = amount + bonus
          if total > 0:
            await db.credit_wallet(
              user["telegram_id"],
              total,
              TxnType.DAILY_BONUS,
              f"Daily bonus (streak: {streak} days)",
            )
            streak_text = ""
            if streak > 1:
              streak_text = (
                 f"\n? Streak Bonus: +?{bonus} "
                 f"({streak} day streak!)"
              )
            await context.bot.send_message(
              chat_id=user["telegram_id"],
              text=(
                 f"?? <b>Good Morning, "
                 f"{user['first_name']}!</b>\n\n"
                 f"? Daily Bonus: <b>?{amount}</b> added!"
                 f"{streak_text}\n\n"
                 f"? Use it on today's matches!\n"
                 f"? /matches to see what's playing!"
              ),
              parse_mode="HTML",
            )
       except Exception:
          pass
   except Exception as e:
     logger.error("daily_bonus_job error: %s", e)
async def leaderboard_announcement_job(context) -> None:
   """Announce top 3 winners weekly. Runs Sunday evening."""
   try:
     leaders = await db.get_leaderboard(limit=3)
     if not leaders:
       return



     text = "? <b>WEEKLY LEADERBOARD</b> ?\n\n"
     medals = ["?", "?", "?"]
     for i, leader in enumerate(leaders):
       name = leader.get("first_name", "Player")
       winnings = leader.get("total_winnings", 0)
       text += f"{medals[i]} <b>{name}</b> -- ?{winnings:,}\n"
     text += (
       "\n? <i>Play more to climb the leaderboard!</i>\n"
       "? /leaderboard for full rankings"
     )
     # Send to all active users
     user_ids = await db.get_all_active_user_ids()
     for uid in user_ids[:200]:
       try:
          await context.bot.send_message(
            chat_id=uid,
            text=text,
            parse_mode="HTML",
          )
       except Exception:
          pass
   except Exception as e:
     logger.error("leaderboard_announcement error: %s", e)
