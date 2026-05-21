"""
Master Callback Router -- Routes ALL callback queries to their handlers.
Central validation, logging, and error handling.
"""
import logging
from typing import Dict, Callable, Awaitable, List, Optional
from telegram import Update, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from bot.constants import CB
from bot.config import config
from bot.handlers.betting import (
   handle_match_callback,
   handle_bet_type_callback,
   handle_bet_callback,
   handle_quick_bet_callback,
   handle_room_callback,
   handle_confirm_callback,
   handle_cancel_callback,
   handle_spin_callback,
   handle_page_callback,
)
from bot.handlers.wallet import (
   handle_wallet_callback,
   handle_history_callback,
   handle_withdraw_callback,
   handle_deposit_callback,
   handle_refer_callback,
)
from bot.handlers.admin import handle_admin_callback
logger = logging.getLogger(__name__)
# =======================================
# Internal callback handlers (defined before route map)
# =======================================
async def _handle_menu_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle menu navigation callbacks."""
   action = parts[1] if len(parts) > 1 else "main"
   if action == "main":
     from bot.services.cricket_api import cricket_api
     from bot.database import db
     from bot.keyboards.main_menu import build_main_menu
     matches = await cricket_api.get_current_matches()
     live_count = len([m for m in matches if m.get("status") == "live"])
     active_rooms = await db.get_user_active_rooms(query.from_user.id)
     balance = await db.get_balance(query.from_user.id)
     text = (
       f"? <b>CricBet Arena</b>\n\n"
       f"? Balance: <b>?{balance:,}</b>\n"
       f"? Live Matches: <b>{live_count}</b>\n\n"
       f"What would you like to do? ?"



     )

     try:
       await query.edit_message_text(
          text=text, parse_mode="HTML",
          reply_markup=build_main_menu(
            live_count=live_count,
            has_active_bets=len(active_rooms) > 0,
          ),
       )
     except BadRequest:
       pass
   elif action == "help":
     from bot.keyboards.main_menu import build_help_menu
     text = (
       "? <b>How to Play CricBet Arena</b>\n\n"
       "? <b>1.</b> Browse live & upcoming matches\n"
       "? <b>2.</b> Pick your prediction\n"
       "? <b>3.</b> Choose bet amount (?3 min)\n"
       "?? <b>4.</b> Get matched with opponent\n"
       "? <b>5.</b> Winner takes the prize!\n\n"
       "? <b>Bet Types:</b>\n"
       "- ? Match Winner -- Pick who wins\n"
       "- ? Toss Winner -- Pick toss winner\n\n"
       "? <b>Tips:</b>\n"
       "- Start with ?3 to learn\n"
       "- Daily login = streak bonus\n"
       "- Refer friends = ?5 each\n"
       "- Spin daily for free prizes"
     )
     try:
       await query.edit_message_text(
          text=text, parse_mode="HTML",
          reply_markup=build_help_menu(),
       )
     except BadRequest:
       pass
   elif action.startswith("help_"):
     help_topic = action.replace("help_", "")
     help_texts = {
       "bet": (
          "? <b>How Betting Works</b>\n\n"
          "1. You choose a match and prediction\n"
          "2. You set your entry amount (?3 min)\n"
          "3. Another player takes the opposite bet\n"
          "4. When match ends, winner gets the prize!\n\n"
          "? Example:\n"
          "- You bet ?3 on India winning\n"
          "- Opponent bets ?3 on Pakistan winning\n"
          "- Pool = ?6, Winner gets ?5\n"
          "- Platform fee = ?1 (16.7%)\n\n"
          "[OK] Bets are locked when the match starts\n"
          "[OK] Results are settled automatically\n"
          "[OK] Refunds if match is abandoned"
       ),
       "wallet": (
          "? <b>Deposits & Withdrawals</b>\n\n"
          "? <b>Add Money:</b>\n"
          "- Contact support for UPI deposit\n"
          "- Min deposit: ?10\n\n"
          "? <b>Withdraw:</b>\n"
          "- Min withdrawal: ?50\n"
          "- Via UPI transfer\n"
          "- Processing: 1-24 hours\n\n"
          "? <b>Free Money:</b>\n"
          "- Welcome bonus on signup\n"
          "- Daily bonus for active players\n"
          "- Referral bonus (?5/friend)\n"
          "- Lucky spin (up to ?500)"



       ),
       "lb": (
          "? <b>Leaderboard</b>\n\n"
          "Rankings based on total winnings.\n"
          "Updated in real-time!\n\n"
          "Top 3 players get weekly bonus prizes! ?"
       ),
       "spin": (
          "? <b>Lucky Spin</b>\n\n"
          "Spin once every 24 hours!\n"
          "Prizes range from ?1 to ?500!\n\n"
          "? ?1 (30%) | ? ?2 (25%)\n"
          "? ?5 (20%) | ? ?10 (12%)\n"
          "? ?25 (7%) | ? ?50 (4%)\n"
          "* ?100 (1.5%) | ? ?500 (0.5%)"
       ),
     }
     text = help_texts.get(help_topic, "? Help topic not found")
     keyboard = InlineKeyboardMarkup([[
       InlineKeyboardButton(
          "? Back to Help",
          callback_data=f"{CB.MENU}:help",
       ),
     ]])
     try:
       await query.edit_message_text(
          text=text, parse_mode="HTML",
          reply_markup=keyboard,
       )
     except BadRequest:
       pass
async def _handle_leaderboard_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle leaderboard callbacks."""
   from bot.database import db
   from bot.keyboards.betting import build_post_result_keyboard
   leaders = await db.get_leaderboard(limit=10)
   text = "? <b>TOP PLAYERS</b> ?\n\n"
   medals = ["?", "?", "?"] + ["?"] * 7
   if not leaders:
     text += "No entries yet! Be the first! ?"
   else:
     for i, leader in enumerate(leaders):
       name = leader.get("first_name", "Player")
       winnings = leader.get("total_winnings", 0)
       text += f"{medals[i]} <b>{name}</b> -- ?{winnings:,}\n"
   text += "\n? Play more to climb the ranks!"
   try:
     await query.edit_message_text(
       text=text, parse_mode="HTML",
       reply_markup=build_post_result_keyboard(),
     )
   except BadRequest:
     pass
async def _handle_stats_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,



) -> None:
   """Handle stats callbacks."""
   from bot.database import db
   from bot.keyboards.betting import build_post_result_keyboard
   user_id = query.from_user.id
   stats = await db.get_user_stats(user_id)
   win_rate = stats.get("win_rate", 0)
   filled = int(win_rate / 10)
   bar = "#" * filled + "." * (10 - filled)
   text = (
     f"? <b>Your Statistics</b>\n\n"
     f"? Total Bets: <b>{stats.get('total_bets', 0)}</b>\n"
     f"? Wins: <b>{stats.get('wins', 0)}</b>\n"
     f"? Losses: <b>{stats.get('losses', 0)}</b>\n"
     f"? Win Rate: <b>{win_rate}%</b> [{bar}]\n\n"
     f"? Balance: <b>?{stats.get('balance', 0):,}</b>\n"
     f"? Streak: <b>{stats.get('streak_days', 0)} days</b>"
   )
   try:
     await query.edit_message_text(
       text=text, parse_mode="HTML",
       reply_markup=build_post_result_keyboard(),
     )
   except BadRequest:
     pass
async def _handle_settings_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle settings callbacks."""
   from bot.database import db
   from bot.keyboards.main_menu import build_settings_menu
   action = parts[1] if len(parts) > 1 else "main"
   user_id = query.from_user.id
   if action == "main":
     user = await db.get_user(user_id)
     notif = user.get("notifications_on", True) if user else True
     lang = user.get("language", "en") if user else "en"
     try:
       await query.edit_message_text(
          text="?? <b>Settings</b>\n\nManage your preferences:",
          parse_mode="HTML",
          reply_markup=build_settings_menu(notif, lang),
       )
     except BadRequest:
       pass
   elif action == "notif":
     user = await db.get_user(user_id)
     current = user.get("notifications_on", True) if user else True
     new_val = not current
     await db.update_user(user_id, {"notifications_on": new_val})
     await query.answer(
       f"Notifications: {'ON ?' if new_val else 'OFF ?'}",
       show_alert=True,
     )
     try:
       await query.edit_message_text(
          text="?? <b>Settings</b>", parse_mode="HTML",
          reply_markup=build_settings_menu(new_val),
       )
     except BadRequest:
       pass




   elif action == "terms":
     text = (
       "? <b>Terms & Conditions</b>\n\n"
       "1. Minimum age: 18 years\n"
       "2. Minimum bet: ?3\n"
       "3. Results are final once settled\n"
       "4. Abandoned matches = full refund\n"
       "5. Withdrawals processed in 1-24 hours\n"
       "6. Platform commission: ~16.7%\n"
       "7. Abuse = permanent ban\n"
       "8. Play responsibly\n\n"
       "[!]? <i>Gambling involves risk.</i>"
     )
     try:
       await query.edit_message_text(
          text=text, parse_mode="HTML",
          reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
              "? Settings",
              callback_data=f"{CB.SETTINGS}:main",
            ),
          ]]),
       )
     except BadRequest:
       pass
async def _handle_support_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle support callbacks."""
   text = (
     "? <b>Support</b>\n\n"
     "Having issues? We're here to help!\n\n"
     "? Contact @YourSupportUsername\n"
     "? Response time: Within 2 hours"
   )
   try:
     await query.edit_message_text(
       text=text, parse_mode="HTML",
       reply_markup=InlineKeyboardMarkup([[
          InlineKeyboardButton(
            "? Main Menu",
            callback_data=f"{CB.MENU}:main",
          ),
       ]]),
     )
   except BadRequest:
     pass
async def _handle_noop_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle no-operation buttons."""
   pass
# =======================================
# MASTER HANDLER (called from main.py)
# =======================================
# Route map: prefix -> handler
_CALLBACK_ROUTES: Dict[str, Callable] = {}
def _build_routes() -> Dict[str, Callable]:
   """Build the route map. Called once on import."""



   return {
     CB.MENU: _handle_menu_callback,
     CB.MATCH: handle_match_callback,
     CB.BET_TYPE: handle_bet_type_callback,
     CB.BET: handle_bet_callback,
     CB.QUICK_BET: handle_quick_bet_callback,
     CB.ROOM: handle_room_callback,
     CB.CONFIRM: handle_confirm_callback,
     CB.CANCEL: handle_cancel_callback,
     CB.SPIN: handle_spin_callback,
     CB.PAGE: handle_page_callback,
     CB.WALLET: handle_wallet_callback,
     CB.HISTORY: handle_history_callback,
     CB.WITHDRAW: handle_withdraw_callback,
     CB.DEPOSIT: handle_deposit_callback,
     CB.REFER: handle_refer_callback,
     CB.ADMIN: handle_admin_callback,
     CB.LEADERBOARD: _handle_leaderboard_callback,
     CB.STATS: _handle_stats_callback,
     CB.SETTINGS: _handle_settings_callback,
     CB.SUPPORT: _handle_support_callback,
     CB.NOOP: _handle_noop_callback,
     CB.NOTIFY: _handle_noop_callback,
   }
async def master_callback_handler(
   update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
   """
   MASTER callback handler. Routes ALL inline button presses.
   Registered in main.py as the single CallbackQueryHandler.
   """
   global _CALLBACK_ROUTES
   if not _CALLBACK_ROUTES:
     _CALLBACK_ROUTES = _build_routes()
   query = update.callback_query
   if query is None:
     return
   # Always answer immediately to remove loading spinner
   await query.answer()
   user = query.from_user
   data = query.data
   if not data:
     logger.warning("Empty callback data from user %d", user.id)
     return
   # Parse callback data
   parts = data.split(":")
   prefix = parts[0] if parts else ""
   # Find handler
   handler = _CALLBACK_ROUTES.get(prefix)
   if handler is None:
     logger.warning(
       "Unknown callback prefix '%s' from user %d, data='%s'",
       prefix, user.id, data
     )
     try:
       await query.answer(
          "[!]? Outdated button. Send /start",
          show_alert=True,
       )
     except Exception:
       pass
     return
   # Admin check



   if prefix == CB.ADMIN:
     if user.id not in config.ADMIN_IDS:
       await query.answer("? Admin only!", show_alert=True)
       return
   # Execute handler with error handling
   try:
     await handler(query, parts, context)
   except Exception as e:
     logger.error(
       "Callback error [%s] user %d: %s",
       data, user.id, e, exc_info=True,
     )
     try:
       await query.answer(
          "[!]? Something went wrong. Try /start",
          show_alert=True,
       )
     except Exception:
       pass
