"""
Betting Handlers -- Core betting flow.
Every step minimizes friction and maximizes conversion.
"""
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Optional
from telegram import Update, CallbackQuery
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from bot.database import db
from bot.config import config
from bot.constants import (
   CB, BetType, RoomStatus, TxnType, MatchStatus,
   SPIN_PRIZES, DEFAULT_BET_TIERS
)
from bot.keyboards.betting import (
   build_matches_keyboard,
   build_match_detail_keyboard,
   build_team_pick_keyboard,
   build_amount_keyboard,
   build_open_rooms_keyboard,
   build_active_bets_keyboard,
   build_post_result_keyboard,
)
from bot.keyboards.main_menu import build_main_menu
from bot.services.cricket_api import cricket_api
logger = logging.getLogger(__name__)
async def handle_match_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle match browsing callbacks."""
   action = parts[1] if len(parts) > 1 else "live"
   if action == "live":
     matches = await cricket_api.get_current_matches()
     live = [m for m in matches if m.get("status") == "live"]
     for m in live:
       await db.upsert_match(m)
     db_matches = await db.get_live_matches()
     text = f"? <b>LIVE MATCHES ({len(db_matches)})</b>\n\n"
     if db_matches:
       text += "Tap a match to bet! ?"
     else:
       text += "No live matches right now.\nCheck upcoming matches! ?"
     try:
       await query.edit_message_text(
          text=text,
          parse_mode="HTML",
          reply_markup=build_matches_keyboard(db_matches, "live"),
       )
     except BadRequest as e:
       if "Message is not modified" not in str(e):



          raise

   elif action == "upcoming":
     matches = await cricket_api.get_current_matches()
     upcoming = [m for m in matches if m.get("status") == "upcoming"]
     for m in upcoming[:20]:
       await db.upsert_match(m)
     db_matches = await db.get_upcoming_matches()
     text = f"? <b>UPCOMING MATCHES ({len(db_matches)})</b>\n\n"
     if db_matches:
       text += "Set bets early for faster matching! ?"
     else:
       text += "No upcoming matches scheduled."
     try:
       await query.edit_message_text(
          text=text,
          parse_mode="HTML",
          reply_markup=build_matches_keyboard(db_matches, "upcoming"),
       )
     except BadRequest as e:
       if "Message is not modified" not in str(e):
          raise
   elif action == "sel":
     # Selected a specific match
     match_id = parts[2] if len(parts) > 2 else ""
     if not match_id:
       await query.answer("Invalid match", show_alert=True)
       return
     match = await db.get_match(match_id)
     if not match:
       # Try by api_match_id
       match = await db.get_match_by_api_id(match_id)
     if not match:
       await query.answer("Match not found", show_alert=True)
       return
     # Check if bets are locked
     status = match.get("status", "")
     if status == MatchStatus.COMPLETED.value:
       await query.answer("This match has ended!", show_alert=True)
       return
     team1 = match.get("team1", "Team 1")
     team2 = match.get("team2", "Team 2")
     venue = match.get("venue", "")
     match_type = match.get("match_type", "")
     score = match.get("score_text", "")
     status_badge = "? LIVE" if status == "live" else "? Upcoming"
     score_line = f"\n? <b>Score:</b> {score}" if score else ""
     text = (
       f"? <b>{team1} vs {team2}</b>\n\n"
       f"{status_badge} | {match_type.upper()}\n"
       f"? {venue}\n"
       f"{score_line}\n\n"
       f"Choose your bet type ?"
     )
     # Store match_id in context for the flow
     context.user_data["current_match_id"] = match.get("id", match_id)
     context.user_data["current_match"] = match
     try:
       await query.edit_message_text(
          text=text,
          parse_mode="HTML",
          reply_markup=build_match_detail_keyboard(match),



       )
     except BadRequest as e:
       if "Message is not modified" not in str(e):
          raise

async def handle_bet_type_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle bet type selection."""
   if len(parts) < 3:
     await query.answer("Invalid selection", show_alert=True)
     return
   bet_type = parts[1]
   match_id = parts[2]
   match = await db.get_match(match_id)
   if not match:
     match = await db.get_match_by_api_id(match_id)
   if not match:
     await query.answer("Match not found", show_alert=True)
     return
   # Store in context
   context.user_data["bet_type"] = bet_type
   context.user_data["current_match_id"] = match.get("id", match_id)
   context.user_data["current_match"] = match
   bet_label = {
     "winner": "? Match Winner",
     "toss": "? Toss Winner",
   }.get(bet_type, bet_type)
   team1 = match.get("team1", "Team 1")
   team2 = match.get("team2", "Team 2")
   text = (
     f"? <b>{bet_label}</b>\n\n"
     f"? {team1} vs {team2}\n\n"
     f"Who do you think will win? ?"
   )
   try:
     await query.edit_message_text(
       text=text,
       parse_mode="HTML",
       reply_markup=build_team_pick_keyboard(match, bet_type),
     )
   except BadRequest as e:
     if "Message is not modified" not in str(e):
       raise
async def handle_bet_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle bet flow callbacks."""
   if len(parts) < 2:
     return
   action = parts[1]
   if action == "pick":
     # User picked a team
     if len(parts) < 5:
       await query.answer("Invalid selection", show_alert=True)
       return



     match_id = parts[2]
     bet_type = parts[3]
     team_num = parts[4] # "1" or "2"
     match = await db.get_match(match_id)
     if not match:
       match = await db.get_match_by_api_id(match_id)
     if not match:
       await query.answer("Match not found", show_alert=True)
       return
     team_name = match.get("team1" if team_num == "1" else "team2", "Team")
     # Store pick
     context.user_data["team_pick"] = team_num
     context.user_data["team_name"] = team_name
     context.user_data["bet_type"] = bet_type
     context.user_data["current_match_id"] = match.get("id", match_id)
     # Get bet tiers
     tiers = await db.get_bet_tiers()
     # Get balance for display
     balance = await db.get_balance(query.from_user.id)
     text = (
       f"? <b>Choose Your Entry Amount</b>\n\n"
       f"? Match: <b>{match.get('team1_short', 'T1')} vs "
       f"{match.get('team2_short', 'T2')}</b>\n"
       f"? Your Pick: <b>{team_name}</b>\n"
       f"? Your Balance: <b>?{balance:,}</b>\n\n"
       f"Higher entry = Higher reward! ?"
     )
     try:
       await query.edit_message_text(
          text=text,
          parse_mode="HTML",
          reply_markup=build_amount_keyboard(
            match_id, bet_type, team_num, tiers
          ),
       )
     except BadRequest as e:
       if "Message is not modified" not in str(e):
          raise
   elif action == "amt":
     # Amount selected -- place the bet!
     if len(parts) < 6:
       await query.answer("Invalid selection", show_alert=True)
       return
     match_id = parts[2]
     bet_type = parts[3]
     team_pick = parts[4]
     amount = int(parts[5])
     await _place_bet(
       query, context, match_id, bet_type, team_pick, amount
     )
   elif action == "active":
     # Show active bets
     user_id = query.from_user.id
     rooms = await db.get_user_active_rooms(user_id)
     text = f"? <b>Your Active Bets ({len(rooms)})</b>\n\n"
     if rooms:
       for room in rooms:
          status = room.get("status", "open")
          status_emoji = "?" if status == "open" else "?"
          amount = room.get("bet_amount", 0)
          pick = room.get(



            "creator_pick" if room["creator_id"] == user_id
            else "joiner_pick", ""
          )
          text += (
            f"{status_emoji} ?{amount} on <b>{pick}</b> -- "
            f"{status}\n"
          )
     else:
       text += "No active bets.\nPlace one now! ?"
     try:
       await query.edit_message_text(
          text=text,
          parse_mode="HTML",
          reply_markup=build_active_bets_keyboard(rooms),
       )
     except BadRequest as e:
       if "Message is not modified" not in str(e):
          raise
   elif action == "custom":
     # Custom amount -- ask user to type
     if len(parts) < 5:
       await query.answer("Error", show_alert=True)
       return
     match_id = parts[2]
     bet_type = parts[3]
     team_pick = parts[4]
     context.user_data["pending_custom_bet"] = {
       "match_id": match_id,
       "bet_type": bet_type,
       "team_pick": team_pick,
     }
     balance = await db.get_balance(query.from_user.id)
     text = (
       f"[edit]? <b>Enter Custom Amount</b>\n\n"
       f"? Your balance: ?{balance:,}\n"
       f"? Min: ?{config.MIN_BET_AMOUNT} | "
       f"Max: ?{min(config.MAX_BET_AMOUNT, balance)}\n\n"
       f"Type the amount below ?"
     )
     try:
       await query.edit_message_text(
          text=text,
          parse_mode="HTML",
       )
     except BadRequest:
       pass
async def handle_custom_bet_amount(
   update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
   """Handle custom bet amount from text input."""
   message = update.effective_message
   user = update.effective_user
   if not message or not user:
     return
   pending = context.user_data.get("pending_custom_bet")
   if not pending:
     return # Not in custom bet flow
   text = message.text or ""
   try:
     amount = int(text.strip().replace("?", "").replace(",", ""))
   except (ValueError, AttributeError):
     await message.reply_text(



       "[X] Please enter a valid number.\n"
       f"Example: {config.MIN_BET_AMOUNT}"
     )
     return
   if amount < config.MIN_BET_AMOUNT:
     await message.reply_text(
       f"[X] Minimum bet is ?{config.MIN_BET_AMOUNT}"
     )
     return
   if amount > config.MAX_BET_AMOUNT:
     await message.reply_text(
       f"[X] Maximum bet is ?{config.MAX_BET_AMOUNT:,}"
     )
     return
   balance = await db.get_balance(user.id)
   if amount > balance:
     await message.reply_text(
       f"[X] Insufficient balance!\n"
       f"? You have ?{balance:,} but need ?{amount:,}\n\n"
       f"Top up your wallet! ?"
     )
     return
   # Clear pending state
   match_id = pending["match_id"]
   bet_type = pending["bet_type"]
   team_pick = pending["team_pick"]
   context.user_data.pop("pending_custom_bet", None)
   # Calculate win amount
   commission_pct = config.PLATFORM_COMMISSION_PCT / 100
   pool = amount * 2
   commission = int(pool * commission_pct)
   win_amount = pool - commission
   # Build confirmation
   match = await db.get_match(match_id)
   if not match:
     match = await db.get_match_by_api_id(match_id)
   if not match:
     await message.reply_text("Match not found. Try again from /matches")
     return
   team_name = match.get(
     "team1" if team_pick == "1" else "team2", "Team"
   )
   from telegram import InlineKeyboardButton, InlineKeyboardMarkup
   text = (
     f"? <b>Confirm Your Bet</b>\n\n"
     f"? {match.get('team1', 'T1')} vs {match.get('team2', 'T2')}\n"
     f"? Pick: <b>{team_name}</b>\n"
     f"? Type: <b>{bet_type}</b>\n"
     f"? Entry: <b>?{amount:,}</b>\n"
     f"? Win: <b>?{win_amount:,}</b>\n\n"
     f"? Tap confirm to lock your bet!"
   )
   # Store for confirmation
   context.user_data["confirm_bet"] = {
     "match_id": match.get("id", match_id),
     "bet_type": bet_type,
     "team_pick": team_pick,
     "team_name": team_name,
     "amount": amount,
     "win_amount": win_amount,
   }
   keyboard = InlineKeyboardMarkup([



     [
       InlineKeyboardButton(
          f"[OK] Confirm ?{amount:,} Bet",
          callback_data=f"{CB.CONFIRM}:bet:{amount}",
       ),
     ],
     [
       InlineKeyboardButton(
          "[X] Cancel",
          callback_data=f"{CB.CANCEL}:bet",
       ),
     ],
   ])
   await message.reply_text(
     text=text,
     parse_mode="HTML",
     reply_markup=keyboard,
   )
async def _place_bet(
   query: CallbackQuery,
   context: ContextTypes.DEFAULT_TYPE,
   match_id: str,
   bet_type: str,
   team_pick: str,
   amount: int,
) -> None:
   """Core bet placement logic."""
   user_id = query.from_user.id
   # 1. Validate balance
   balance = await db.get_balance(user_id)
   if balance < amount:
     await query.answer(
       f"[X] Not enough balance! You have ?{balance:,}",
       show_alert=True,
     )
     return
   # 2. Get match
   match = await db.get_match(match_id)
   if not match:
     match = await db.get_match_by_api_id(match_id)
   if not match:
     await query.answer("Match not found", show_alert=True)
     return
   # 3. Check match status
   if match.get("status") == MatchStatus.COMPLETED.value:
     await query.answer("This match has ended!", show_alert=True)
     return
   # 4. Check bet lock time
   match_start = match.get("match_start", "")
   if match_start:
     try:
       start_time = datetime.fromisoformat(
          match_start.replace("Z", "+00:00")
       )
       lock_time = start_time - timedelta(
          minutes=config.BET_LOCK_BEFORE_MATCH_MINS
       )
       if datetime.now(timezone.utc) > lock_time:
          if match.get("status") != "live":
            # For live matches, still allow toss bets if toss not done
            pass
     except (ValueError, TypeError):
       pass
   # 5. Calculate win amount
   commission_pct = config.PLATFORM_COMMISSION_PCT / 100



   pool = amount * 2
   commission = int(pool * commission_pct)
   win_amount = pool - commission
   team_name = match.get(
     "team1" if team_pick == "1" else "team2", "Team"
   )
   # 6. Check for existing open room to join
   opposite_pick = "2" if team_pick == "1" else "1"
   open_rooms = await db.get_open_rooms(
     match.get("id", match_id),
     bet_type=bet_type,
     exclude_user=user_id,
   )
   # Find matching room (same amount, opposite pick)
   matching_room = None
   for room in open_rooms:
     if (room["bet_amount"] == amount and
       room["creator_pick"] != team_name):
       matching_room = room
       break
   if matching_room:
     # JOIN existing room
     # Debit user
     success, new_bal = await db.debit_wallet(
       user_id, amount, TxnType.BET_PLACED,
       f"Bet on {match.get('name', 'match')}",
       reference_id=matching_room["id"],
     )
     if not success:
       await query.answer("[X] Transaction failed", show_alert=True)
       return
     joined = await db.join_room(
       matching_room["id"],
       user_id,
       team_name,
     )
     if not joined:
       # Refund
       await db.credit_wallet(
          user_id, amount, TxnType.BET_REFUND,
          "Room join failed -- refund",
       )
       await query.answer("Room filled. Try again!", show_alert=True)
       return
     # Notify both players
     text = (
       f"?? <b>GAME ON!</b>\n\n"
       f"You joined a ?{amount} bet!\n\n"
       f"? {match.get('name', 'Match')}\n"
       f"? Your pick: <b>{team_name}</b>\n"
       f"? Prize pool: <b>?{pool}</b>\n"
       f"? Winner gets: <b>?{win_amount}</b>\n\n"
       f"? <i>Sit back and watch! "
       f"We'll settle automatically!</i>"
     )
     try:
       await query.edit_message_text(
          text=text,
          parse_mode="HTML",
          reply_markup=build_post_result_keyboard(),
       )
     except BadRequest:
       pass
     # Notify room creator
     try:



       creator_id = matching_room["creator_id"]
       await context.bot.send_message(
          chat_id=creator_id,
          text=(
            f"?? <b>Opponent Found!</b>\n\n"
            f"Someone joined your ?{amount} bet!\n\n"
            f"? {match.get('name', 'Match')}\n"
            f"? Your pick: <b>{matching_room['creator_pick']}</b>\n"
            f"? Opponent: <b>{team_name}</b>\n"
            f"? Prize pool: <b>?{pool}</b>\n"
            f"? Winner gets: <b>?{win_amount}</b>\n\n"
            f"? <i>Game is locked! Result coming soon!</i>"
          ),
          parse_mode="HTML",
          reply_markup=build_post_result_keyboard(),
       )
     except Exception as e:
       logger.error("Failed to notify creator: %s", e)
   else:
     # CREATE new room
     success, new_bal = await db.debit_wallet(
       user_id, amount, TxnType.BET_PLACED,
       f"Bet on {match.get('name', 'match')}",
     )
     if not success:
       await query.answer("[X] Transaction failed", show_alert=True)
       return
     room = await db.create_room(
       match_id=match.get("id", match_id),
       creator_id=user_id,
       bet_type=bet_type,
       bet_amount=amount,
       win_amount=win_amount,
       creator_pick=team_name,
     )
     if not room:
       # Refund
       await db.credit_wallet(
          user_id, amount, TxnType.BET_REFUND,
          "Room creation failed -- refund",
       )
       await query.answer("[X] Error creating room", show_alert=True)
       return
     text = (
       f"[OK] <b>Bet Placed!</b>\n\n"
       f"? {match.get('name', 'Match')}\n"
       f"? Your Pick: <b>{team_name}</b>\n"
       f"? Entry: <b>?{amount}</b>\n"
       f"? Win: <b>?{win_amount}</b>\n\n"
       f"? <b>Waiting for opponent...</b>\n\n"
       f"? <i>We'll notify you the moment "
       f"someone accepts!</i>\n\n"
       f"? <i>Share with friends to get matched faster!</i>"
     )
     try:
       await query.edit_message_text(
          text=text,
          parse_mode="HTML",
          reply_markup=build_active_bets_keyboard([room]),
       )
     except BadRequest:
       pass
async def handle_quick_bet_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:



   """Handle quick one-click bets (friction minimizer)."""
   if len(parts) == 2:
     # Generic quick bet -- show live matches
     amount = parts[1]
     context.user_data["quick_bet_amount"] = int(amount)
     await handle_match_callback(query, [CB.MATCH, "live"], context)
     return
   if len(parts) < 6:
     await query.answer("Invalid quick bet", show_alert=True)
     return
   # Full quick bet: qb:w:match_id:team:amount
   bet_type = "winner" if parts[1] == "w" else parts[1]
   match_id = parts[2]
   team_pick = parts[3]
   amount = int(parts[4])
   await _place_bet(query, context, match_id, bet_type, team_pick, amount)
async def handle_room_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle room-related callbacks."""
   if len(parts) < 3:
     return
   action = parts[1]
   if action == "list":
     match_id = parts[2]
     rooms = await db.get_open_rooms(
       match_id, exclude_user=query.from_user.id
     )
     text = f"? <b>Open Rooms ({len(rooms)})</b>\n\n"
     if rooms:
       text += "Join a room or create your own! ?"
     else:
       text += "No open rooms. Be the first to create one! ?"
     try:
       await query.edit_message_text(
          text=text,
          parse_mode="HTML",
          reply_markup=build_open_rooms_keyboard(rooms, match_id),
       )
     except BadRequest as e:
       if "Message is not modified" not in str(e):
          raise
   elif action == "join":
     room_id = parts[2]
     room = await db.get_room(room_id)
     if not room:
       await query.answer("Room not found", show_alert=True)
       return
     if room["status"] != RoomStatus.OPEN.value:
       await query.answer("Room is no longer open", show_alert=True)
       return
     if room["creator_id"] == query.from_user.id:
       await query.answer(
          "You can't join your own room!", show_alert=True
       )
       return
     # Determine opposite pick
     match = await db.get_match(room["match_id"])



     if not match:
       await query.answer("Match not found", show_alert=True)
       return
     creator_pick = room["creator_pick"]
     team1 = match.get("team1", "Team 1")
     team2 = match.get("team2", "Team 2")
     if creator_pick == team1:
       joiner_pick = team2
     else:
       joiner_pick = team1
     # Place the bet (joins room)
     amount = room["bet_amount"]
     match_id = room["match_id"]
     await _place_bet(
       query, context, match_id,
       room["bet_type"],
       "2" if creator_pick == team1 else "1",
       amount,
     )
   elif action == "view":
     room_id = parts[2]
     room = await db.get_room(room_id)
     if not room:
       await query.answer("Room not found", show_alert=True)
       return
     status = room.get("status", "open")
     amount = room.get("bet_amount", 0)
     win = room.get("win_amount", 0)
     pick = room.get("creator_pick", "")
     text = (
       f"? <b>Room Details</b>\n\n"
       f"? Entry: ?{amount}\n"
       f"? Prize: ?{win}\n"
       f"? Your pick: {pick}\n"
       f"? Status: {status.upper()}\n"
     )
     if status == "open":
       text += "\n? Waiting for opponent..."
     elif status == "locked":
       text += "\n? Match in progress..."
     from telegram import InlineKeyboardButton, InlineKeyboardMarkup
     keyboard = InlineKeyboardMarkup([
       [InlineKeyboardButton(
          "? Back",
          callback_data=f"{CB.BET}:active",
       )],
     ])
     try:
       await query.edit_message_text(
          text=text,
          parse_mode="HTML",
          reply_markup=keyboard,
       )
     except BadRequest:
       pass
async def handle_confirm_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle confirmation callbacks."""



   if len(parts) < 2:
     return
   action = parts[1]

   if action == "bet":
     confirm_data = context.user_data.get("confirm_bet")
     if not confirm_data:
       await query.answer("Session expired. Start over.", show_alert=True)
       return
     match_id = confirm_data["match_id"]
     bet_type = confirm_data["bet_type"]
     team_pick = confirm_data["team_pick"]
     amount = confirm_data["amount"]
     context.user_data.pop("confirm_bet", None)
     await _place_bet(
       query, context, match_id, bet_type, team_pick, amount
     )

async def handle_cancel_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle cancellation callbacks."""
   context.user_data.pop("confirm_bet", None)
   context.user_data.pop("pending_custom_bet", None)
   try:
     await query.edit_message_text(
       text="[X] Cancelled.\n\n? /start to go back to menu",
       parse_mode="HTML",
       reply_markup=build_main_menu(),
     )
   except BadRequest:
     pass
async def handle_spin_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle lucky spin -- Variable reward psychology."""
   user_id = query.from_user.id
   # Check cooldown
   can_spin = await db.can_spin(user_id)
   if not can_spin:
     await query.answer(
       "? You already spun today! Come back tomorrow!",
       show_alert=True,
     )
     return
   # Weighted random prize
   prizes = SPIN_PRIZES
   weights = [p["weight"] for p in prizes]
   winner = random.choices(prizes, weights=weights, k=1)[0]
   prize_amount = winner["amount"]
   emoji = winner["emoji"]
   # Record spin and credit
   await db.record_spin(user_id, prize_amount)
   await db.credit_wallet(
     user_id, prize_amount,
     TxnType.SPIN_WIN,
     f"Lucky spin prize: ?{prize_amount}",
   )




   balance = await db.get_balance(user_id)
   # Build dramatic reveal
   text = (
     f"? <b>LUCKY SPIN!</b> ?\n\n"
     f"???????????\n"
     f" {emoji} {emoji} {emoji}\n"
     f"???????????\n\n"
     f"? You won <b>?{prize_amount}!</b>\n\n"
     f"? New Balance: <b>?{balance:,}</b>\n\n"
     f"? Next spin available in 24 hours!\n\n"
     f"? <i>Use your winnings on the next match!</i>"
   )
   try:
     await query.edit_message_text(
       text=text,
       parse_mode="HTML",
       reply_markup=build_post_result_keyboard(),
     )
   except BadRequest:
     pass
async def handle_page_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle pagination callbacks."""
   if len(parts) < 3:
     return
   match_type = parts[1]
   page = int(parts[2])
   if match_type == "live":
     db_matches = await db.get_live_matches()
   else:
     db_matches = await db.get_upcoming_matches()
   try:
     await query.edit_message_text(
       text=f"{'? LIVE' if match_type == 'live' else '? UPCOMING'} "
          f"MATCHES -- Page {page + 1}",
       parse_mode="HTML",
       reply_markup=build_matches_keyboard(
          db_matches, match_type, page
       ),
     )
   except BadRequest:
     pass
