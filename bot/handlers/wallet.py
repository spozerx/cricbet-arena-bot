"""
Wallet Handlers -- Deposits, withdrawals, transaction history.
"""
import logging
import re
from telegram import Update, CallbackQuery
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from bot.database import db
from bot.config import config
from bot.constants import CB, TxnType
from bot.keyboards.main_menu import build_wallet_menu, build_main_menu
logger = logging.getLogger(__name__)

async def handle_wallet_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle wallet callbacks."""
   action = parts[1] if len(parts) > 1 else "main"
   user_id = query.from_user.id
   if action == "main":
     balance = await db.get_balance(user_id)
     stats = await db.get_user_stats(user_id)
     text = (
       f"? <b>Your Wallet</b>\n\n"
       f"? Balance: <b>?{balance:,}</b>\n"
       f"? Total Bets: <b>{stats.get('total_bets', 0)}</b>\n"
       f"? Wins: <b>{stats.get('wins', 0)}</b>\n"
       f"? Win Rate: <b>{stats.get('win_rate', 0)}%</b>\n"
       f"? Total Won: <b>?{stats.get('total_winnings', 0):,}</b>\n"
     )
     try:
       await query.edit_message_text(
          text=text, parse_mode="HTML",
          reply_markup=build_wallet_menu(balance),
       )
     except BadRequest:
       pass
async def handle_history_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle transaction history callbacks."""
   if len(parts) < 3:
     return
   history_type = parts[1] # "txn" or "bets"
   page = int(parts[2]) if len(parts) > 2 else 0
   user_id = query.from_user.id
   if history_type == "txn":



     per_page = 10
     transactions = await db.get_transactions(
       user_id, limit=per_page, offset=page * per_page
     )
     if not transactions:
       text = "? <b>Transaction History</b>\n\nNo transactions yet."
     else:
       text = "? <b>Transaction History</b>\n\n"
       for txn in transactions:
          direction = txn.get("direction", "")
          amount = txn.get("amount", 0)
          txn_type = txn.get("txn_type", "")
          created = txn.get("created_at", "")[:16]
          emoji = "?" if direction == "credit" else "?"
          sign = "+" if direction == "credit" else "-"
          # Pretty type names
          type_labels = {
            "deposit": "Deposit",
            "withdrawal": "Withdrawal",
            "bet_placed": "Bet Placed",
            "bet_won": "Bet Won! ?",
            "bet_refund": "Refund",
            "signup_bonus": "Welcome Bonus",
            "referral_bonus": "Referral Bonus",
            "daily_bonus": "Daily Bonus",
            "streak_bonus": "Streak Bonus",
            "spin_win": "Lucky Spin ?",
            "commission": "Commission",
            "admin_credit": "Admin Credit",
            "admin_debit": "Admin Debit",
          }
          label = type_labels.get(txn_type, txn_type)
          text += (
            f"{emoji} {sign}?{amount} -- {label}\n"
            f"  <i>{created}</i>\n\n"
          )
     from telegram import InlineKeyboardButton, InlineKeyboardMarkup
     nav = []
     if page > 0:
       nav.append(InlineKeyboardButton(
          "<? Prev",
          callback_data=f"{CB.HISTORY}:txn:{page-1}",
       ))
     if len(transactions) == 10:
       nav.append(InlineKeyboardButton(
          "Next >?",
          callback_data=f"{CB.HISTORY}:txn:{page+1}",
       ))
     keyboard = []
     if nav:
       keyboard.append(nav)
     keyboard.append([
       InlineKeyboardButton(
          "? Wallet",
          callback_data=f"{CB.WALLET}:main",
       ),
     ])
     try:
       await query.edit_message_text(
          text=text, parse_mode="HTML",
          reply_markup=InlineKeyboardMarkup(keyboard),
       )
     except BadRequest:
       pass
   elif history_type == "bets":



     per_page = 10
     bets = await db.get_user_bet_history(
       user_id, limit=per_page, offset=page * per_page
     )
     if not bets:
       text = "? <b>Bet History</b>\n\nNo bets yet. Place your first!"
     else:
       text = "? <b>Bet History</b>\n\n"
       for bet in bets:
          amount = bet.get("bet_amount", 0)
          status = bet.get("status", "open")
          pick = bet.get("creator_pick", bet.get("joiner_pick", ""))
          winner_id = bet.get("winner_id")
          if status == "settled":
            if winner_id == user_id:
              emoji = "?"
              result = f"Won ?{bet.get('win_amount', 0)}"
            else:
              emoji = "?"
              result = f"Lost ?{amount}"
          elif status == "open":
            emoji = "?"
            result = "Waiting..."
          elif status == "locked":
            emoji = "?"
            result = "In progress"
          elif status in ("cancelled", "expired"):
            emoji = "??"
            result = "Refunded"
          else:
            emoji = "?"
            result = status
          text += f"{emoji} ?{amount} on {pick} -- {result}\n"
     from telegram import InlineKeyboardButton, InlineKeyboardMarkup
     keyboard = [[
       InlineKeyboardButton(
          "? Wallet",
          callback_data=f"{CB.WALLET}:main",
       ),
     ]]
     try:
       await query.edit_message_text(
          text=text, parse_mode="HTML",
          reply_markup=InlineKeyboardMarkup(keyboard),
       )
     except BadRequest:
       pass
async def handle_withdraw_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle withdrawal flow."""
   action = parts[1] if len(parts) > 1 else "start"
   if action == "start":
     balance = await db.get_balance(query.from_user.id)
     if balance < config.MIN_WITHDRAWAL:
       await query.answer(
          f"[X] Minimum withdrawal is ?{config.MIN_WITHDRAWAL}. "
          f"You have ?{balance}.",
          show_alert=True,
       )
       return



     context.user_data["withdraw_flow"] = True

     text = (
       f"? <b>Withdraw Funds</b>\n\n"
       f"? Available: <b>?{balance:,}</b>\n"
       f"? Min withdrawal: ?{config.MIN_WITHDRAWAL}\n\n"
       f"Enter the amount to withdraw ?"
     )
     try:
       await query.edit_message_text(text=text, parse_mode="HTML")
     except BadRequest:
       pass
async def handle_withdraw_text(
   update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
   """Handle withdrawal text inputs (amount and UPI)."""
   message = update.effective_message
   user = update.effective_user
   if not message or not user:
     return
   text = (message.text or "").strip()
   if context.user_data.get("withdraw_flow"):
     # Step 1: Amount
     if not context.user_data.get("withdraw_amount"):
       try:
          amount = int(text.replace("?", "").replace(",", ""))
       except ValueError:
          await message.reply_text("[X] Enter a valid number.")
          return
       balance = await db.get_balance(user.id)
       if amount < config.MIN_WITHDRAWAL:
          await message.reply_text(
            f"[X] Min withdrawal: ?{config.MIN_WITHDRAWAL}"
          )
          return
       if amount > balance:
          await message.reply_text(
            f"[X] Insufficient balance. You have ?{balance:,}"
          )
          return
       context.user_data["withdraw_amount"] = amount
       await message.reply_text(
          f"? Withdraw <b>?{amount:,}</b>\n\n"
          f"Enter your UPI ID:\n"
          f"(e.g., <code>name@upi</code>)",
          parse_mode="HTML",
       )
       return
     # Step 2: UPI ID
     upi_id = text
     # Basic UPI validation
     if not re.match(r'^[\w.\-]+@[\w]+$', upi_id):
       await message.reply_text(
          "[X] Invalid UPI ID format.\n"
          "Example: <code>yourname@paytm</code>",
          parse_mode="HTML",
       )
       return
     amount = context.user_data["withdraw_amount"]
     # Debit wallet
     success, new_bal = await db.debit_wallet(
       user.id, amount,
       TxnType.WITHDRAWAL,



       f"Withdrawal to {upi_id}",
     )
     if not success:
       await message.reply_text("[X] Withdrawal failed. Try again.")
       context.user_data.pop("withdraw_flow", None)
       context.user_data.pop("withdraw_amount", None)
       return
     # Create withdrawal request
     wd = await db.create_withdrawal(user.id, amount, upi_id)
     # Clear flow state
     context.user_data.pop("withdraw_flow", None)
     context.user_data.pop("withdraw_amount", None)
     await message.reply_text(
       f"[OK] <b>Withdrawal Requested!</b>\n\n"
       f"? Amount: ?{amount:,}\n"
       f"? UPI: {upi_id}\n\n"
       f"? Processing time: 1-24 hours\n"
       f"? You'll be notified once processed!\n\n"
       f"? Remaining balance: ?{new_bal:,}",
       parse_mode="HTML",
       reply_markup=build_main_menu(),
     )
     # Notify admin
     if config.ADMIN_CHAT_ID:
       try:
          await context.bot.send_message(
            chat_id=config.ADMIN_CHAT_ID,
            text=(
              f"? <b>New Withdrawal Request!</b>\n\n"
              f"? User: {user.first_name} "
              f"(@{user.username or 'none'})\n"
              f"? ID: {user.id}\n"
              f"? Amount: ?{amount:,}\n"
              f"? UPI: <code>{upi_id}</code>\n\n"
              f"Review in /admin"
            ),
            parse_mode="HTML",
          )
       except Exception:
          pass
async def handle_deposit_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle deposit flow."""
   text = (
     "? <b>Add Money to Wallet</b>\n\n"
     "Choose your preferred method:\n\n"
     "? <b>UPI Payment:</b>\n"
     "Send money to our UPI ID and share screenshot\n\n"
     "* <b>Telegram Stars:</b>\n"
     "Pay directly through Telegram\n\n"
     "? Contact /support for deposit assistance"
   )
   from telegram import InlineKeyboardButton, InlineKeyboardMarkup
   keyboard = InlineKeyboardMarkup([
     [InlineKeyboardButton(
       "? Contact Support to Deposit",
       callback_data=f"{CB.SUPPORT}:deposit",
     )],
     [InlineKeyboardButton(
       "? Wallet",
       callback_data=f"{CB.WALLET}:main",
     )],



   ])

   try:
     await query.edit_message_text(
       text=text, parse_mode="HTML",
       reply_markup=keyboard,
     )
   except BadRequest:
     pass
async def handle_refer_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle referral system."""
   user_id = query.from_user.id
   user = await db.get_user(user_id)
   if not user:
     return
   ref_code = user.get("referral_code", "")
   bot_username = config.BOT_USERNAME or "CricBetArenaBot"
   ref_link = f"https://t.me/{bot_username}?start=ref_{ref_code}"
   text = (
     f"? <b>Invite Friends & Earn!</b>\n\n"
     f"Share your referral link:\n"
     f"<code>{ref_link}</code>\n\n"
     f"? You earn <b>?{config.REFERRAL_BONUS}</b> "
     f"for every friend who joins!\n"
     f"? Your friend gets <b>?{config.FREE_CREDITS_ON_SIGNUP}</b> "
     f"welcome bonus!\n\n"
     f"? Tap the link above to copy it!\n\n"
     f"? Your referrals so far: Check /stats"
   )
   from telegram import InlineKeyboardButton, InlineKeyboardMarkup
   keyboard = InlineKeyboardMarkup([
     [InlineKeyboardButton(
       "? Share Link",
       switch_inline_query=f"Join CricBet Arena! {ref_link}",
     )],
     [InlineKeyboardButton(
       "? Main Menu",
       callback_data=f"{CB.MENU}:main",
     )],
   ])
   try:
     await query.edit_message_text(
       text=text, parse_mode="HTML",
       reply_markup=keyboard,
     )
   except BadRequest:
     pass
