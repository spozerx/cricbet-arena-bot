"""
Start & Core Command Handlers.
First impression = 90% of retention. Every word is optimized.
"""
import logging
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from bot.database import db
from bot.config import config
from bot.constants import CB, TxnType, MSG
from bot.keyboards.main_menu import build_main_menu, build_help_menu
from bot.services.cricket_api import cricket_api
logger = logging.getLogger(__name__)

async def start_command(
   update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
   """
   /start handler -- The most important handler in the entire bot.
   First contact = determines lifetime value of user.
   """
   user = update.effective_user
   if not user:
     return
   message = update.effective_message
   if not message:
     return
   try:
     # Check for referral code: /start ref_ABCDEF
     referral_code: Optional[str] = None
     if context.args and len(context.args) > 0:
       arg = context.args[0]
       if arg.startswith("ref_"):
          referral_code = arg[4:]
     # Get or create user
     db_user = await db.get_user(user.id)
     is_new = db_user is None
     # Upsert user data
     db_user = await db.upsert_user(
       telegram_id=user.id,
       username=user.username,
       first_name=user.first_name or "Player",
       last_name=user.last_name,
       language_code=user.language_code,
     )
     if is_new:
       # --- NEW USER FLOW ---
       # 1. Grant welcome bonus (Reciprocity principle)
       bonus = config.FREE_CREDITS_ON_SIGNUP
       if bonus > 0:
          await db.credit_wallet(
            user.id,
            bonus,



            TxnType.SIGNUP_BONUS,
            "Welcome bonus for joining!",
          )
       # 2. Process referral
       if referral_code:
          referrer_id = await db.process_referral(
            user.id, referral_code
          )
          if referrer_id:
            # Notify referrer
            try:
              await context.bot.send_message(
                 chat_id=referrer_id,
                 text=(
                   f"? <b>Referral Bonus!</b>\n\n"
                   f"Your friend <b>{user.first_name}</b> "
                   f"just joined using your link!\n"
                   f"? <b>?{config.REFERRAL_BONUS}</b> "
                   f"added to your wallet!\n\n"
                   f"Keep inviting to earn more! ?"
                 ),
                 parse_mode="HTML",
              )
            except Exception:
              pass
       # 3. Get user count for social proof
       user_count = await db.get_user_count()
       # 4. Get live matches count
       live_matches = await cricket_api.get_current_matches()
       live_count = len([
          m for m in live_matches
          if m.get("status") == "live"
       ])
       # 5. Send welcome message (optimized for conversion)
       text = MSG["welcome_new"].format(
          name=user.first_name or "Champion",
          user_count=max(user_count, 1000), # Social proof floor
          bonus=bonus,
       )
       keyboard = build_main_menu(
          live_count=live_count,
          has_active_bets=False,
       )
       await message.reply_text(
          text=text,
          parse_mode="HTML",
          reply_markup=keyboard,
       )
       # 6. Notify admin about new user
       if config.ADMIN_CHAT_ID:
          try:
            await context.bot.send_message(
              chat_id=config.ADMIN_CHAT_ID,
              text=(
                 f"? New user joined!\n"
                 f"Name: {user.first_name} "
                 f"(@{user.username or 'none'})\n"
                 f"ID: {user.id}\n"
                 f"Referral: {referral_code or 'organic'}\n"
                 f"Total users: {user_count + 1}"
              ),
            )
          except Exception:
            pass
     else:



       # --- RETURNING USER FLOW ---
       # Update streak
       streak = await db.update_streak(user.id)
       balance = await db.get_balance(user.id)
       stats = await db.get_user_stats(user.id)
       # Get live data
       live_matches = await cricket_api.get_current_matches()
       live_count = len([
          m for m in live_matches
          if m.get("status") == "live"
       ])
       upcoming_count = len([
          m for m in live_matches
          if m.get("status") == "upcoming"
       ])
       # Active bets
       active_rooms = await db.get_user_active_rooms(user.id)
       has_active = len(active_rooms) > 0
       win_rate = stats.get("win_rate", 0)
       text = MSG["welcome_back"].format(
          name=user.first_name or "Champion",
          balance=balance,
          win_rate=win_rate,
          streak=streak,
          live_count=live_count,
          upcoming_count=upcoming_count,
       )
       keyboard = build_main_menu(
          live_count=live_count,
          has_active_bets=has_active,
       )
       await message.reply_text(
          text=text,
          parse_mode="HTML",
          reply_markup=keyboard,
       )
   except Exception as e:
     logger.error("start_command error for user %d: %s", user.id, e, exc_info=True)
     await message.reply_text(
       "? Welcome to CricBet Arena!\n\n"
       "Something went wrong loading your profile. "
       "Please try /start again in a moment."
     )
async def help_command(
   update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
   """/help handler."""
   message = update.effective_message
   if not message:
     return
   text = (
     "? <b>How to Play CricBet Arena</b>\n\n"
     "? <b>Step 1:</b> Browse live & upcoming matches\n"
     "? <b>Step 2:</b> Pick your prediction (Match Winner, "
     "Toss Winner, etc.)\n"
     "? <b>Step 3:</b> Choose your bet amount (?3 to ?10,000)\n"
     "?? <b>Step 4:</b> Get matched with an opponent\n"
     "? <b>Step 5:</b> Winner takes the prize!\n\n"
     "? <b>Tips:</b>\n"
     "- Start small with ?3 bets to learn\n"
     "- Use Quick Bet for instant action\n"
     "- Daily login = bonus credits\n"
     "- Refer friends = ?5 per friend\n"



     "- Spin the wheel daily for free prizes\n\n"
     "? Need help? Contact /support"
   )
   await message.reply_text(
     text=text,
     parse_mode="HTML",
     reply_markup=build_help_menu(),
   )
async def matches_command(
   update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
   """/matches handler -- Show live matches."""
   from bot.keyboards.betting import build_matches_keyboard
   message = update.effective_message
   if not message:
     return
   try:
     matches = await cricket_api.get_current_matches()
     live = [m for m in matches if m.get("status") == "live"]
     if live:
       # Store in DB
       for m in live:
          await db.upsert_match(m)
       # Get matches from DB with IDs
       db_matches = await db.get_live_matches()
       text = (
          f"? <b>LIVE MATCHES ({len(db_matches)})</b>\n\n"
          f"Tap a match to place your bet! ?"
       )
       keyboard = build_matches_keyboard(db_matches, "live")
     else:
       # Show upcoming instead
       upcoming = [m for m in matches if m.get("status") == "upcoming"]
       for m in upcoming[:20]:
          await db.upsert_match(m)
       db_matches = await db.get_upcoming_matches()
       text = (
          "? <b>No live matches right now</b>\n\n"
          f"? <b>{len(db_matches)}</b> upcoming matches:\n"
          "Set up your bets early to get matched faster! ?"
       )
       keyboard = build_matches_keyboard(db_matches, "upcoming")
     await message.reply_text(
       text=text,
       parse_mode="HTML",
       reply_markup=keyboard,
     )
   except Exception as e:
     logger.error("matches_command error: %s", e, exc_info=True)
     await message.reply_text(
       "? Couldn't load matches right now. Try again in a moment!\n"
       "? /start to go back to menu"
     )
async def wallet_command(
   update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
   """/wallet handler."""
   from bot.keyboards.main_menu import build_wallet_menu
   message = update.effective_message
   user = update.effective_user



   if not message or not user:
     return
   try:
     balance = await db.get_balance(user.id)
     stats = await db.get_user_stats(user.id)
     text = (
       f"? <b>Your Wallet</b>\n\n"
       f"? Balance: <b>?{balance:,}</b>\n"
       f"? Total Bets: <b>{stats.get('total_bets', 0)}</b>\n"
       f"? Wins: <b>{stats.get('wins', 0)}</b>\n"
       f"? Win Rate: <b>{stats.get('win_rate', 0)}%</b>\n"
       f"? Total Winnings: "
       f"<b>?{stats.get('total_winnings', 0):,}</b>\n"
     )
     await message.reply_text(
       text=text,
       parse_mode="HTML",
       reply_markup=build_wallet_menu(balance),
     )
   except Exception as e:
     logger.error("wallet_command error: %s", e)
     await message.reply_text(
       "Couldn't load wallet. Try /start"
     )
async def stats_command(
   update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
   """/stats handler."""
   message = update.effective_message
   user = update.effective_user
   if not message or not user:
     return
   try:
     stats = await db.get_user_stats(user.id)
     if not stats:
       await message.reply_text("No stats yet! Place your first bet ?")
       return
     # Win rate visualization
     win_rate = stats.get("win_rate", 0)
     filled = int(win_rate / 10)
     bar = "#" * filled + "." * (10 - filled)
     text = (
       f"? <b>Your Statistics</b>\n\n"
       f"? Player: <b>{user.first_name}</b>\n"
       f"? ID: <code>{user.id}</code>\n\n"
       f"? <b>Betting Stats:</b>\n"
       f"|- Total Bets: <b>{stats.get('total_bets', 0)}</b>\n"
       f"|- Wins: <b>{stats.get('wins', 0)}</b> [OK]\n"
       f"|- Losses: <b>{stats.get('losses', 0)}</b> [X]\n"
       f"\- Win Rate: <b>{win_rate}%</b> [{bar}]\n\n"
       f"? <b>Financial:</b>\n"
       f"|- Balance: <b>?{stats.get('balance', 0):,}</b>\n"
       f"|- Total Won: <b>?{stats.get('total_winnings', 0):,}</b>\n"
       f"\- Streak: <b>{stats.get('streak_days', 0)} days</b> ?\n\n"
       f"? <i>Keep playing to improve your stats!</i>"
     )
     from bot.keyboards.betting import build_post_result_keyboard
     await message.reply_text(
       text=text,
       parse_mode="HTML",
       reply_markup=build_post_result_keyboard(),
     )
   except Exception as e:



     logger.error("stats_command error: %s", e)
     await message.reply_text("Couldn't load stats. Try again!")

async def leaderboard_command(
   update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
   """/leaderboard handler."""
   message = update.effective_message
   if not message:
     return
   try:
     leaders = await db.get_leaderboard(limit=10)
     if not leaders:
       await message.reply_text(
          "? <b>Leaderboard</b>\n\n"
          "No entries yet! Be the first to win! ?",
          parse_mode="HTML",
       )
       return
     text = "? <b>TOP PLAYERS LEADERBOARD</b> ?\n\n"
     medals = ["?", "?", "?"] + ["?"] * 7
     for i, leader in enumerate(leaders):
       name = leader.get("first_name", "Player")
       winnings = leader.get("total_winnings", 0)
       wins = leader.get("wins_count", 0)
       streak = leader.get("streak_days", 0)
       text += (
          f"{medals[i]} <b>{name}</b>\n"
          f" ? ?{winnings:,} won | "
          f"? {wins} wins | ? {streak}d streak\n\n"
       )
     text += (
       "???????????????????\n"
       "? <i>Play more to climb the leaderboard!</i>"
     )
     from bot.keyboards.betting import build_post_result_keyboard
     await message.reply_text(
       text=text,
       parse_mode="HTML",
       reply_markup=build_post_result_keyboard(),
     )
   except Exception as e:
     logger.error("leaderboard_command error: %s", e)
     await message.reply_text("Couldn't load leaderboard. Try again!")
