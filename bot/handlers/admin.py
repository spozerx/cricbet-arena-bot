"""
Admin Handlers -- Full admin panel with dashboard, user management,
config editing, broadcasts, and withdrawal processing.
"""
import logging
import asyncio
from datetime import datetime, timezone
from telegram import Update, CallbackQuery
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from bot.database import db
from bot.config import config
from bot.constants import CB, TxnType, ADMIN_CONFIGURABLE
from bot.keyboards.admin import (
   build_admin_menu,
   build_config_keyboard,
   build_user_management_keyboard,
   build_withdrawal_list_keyboard,
   build_withdrawal_action_keyboard,
)
from bot.services.cricket_api import cricket_api
logger = logging.getLogger(__name__)
def is_admin(user_id: int) -> bool:
   """Check if user is admin."""
   return user_id in config.ADMIN_IDS
async def admin_command(
   update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
   """/admin handler -- Admin panel entry."""
   user = update.effective_user
   message = update.effective_message
   if not user or not message:
     return
   if not is_admin(user.id):
     await message.reply_text("? Admin access only.")
     return
   stats = await db.get_dashboard_stats()
   text = (
     "? <b>ADMIN PANEL</b>\n\n"
     f"? Total Users: <b>{stats.get('total_users', 0):,}</b>\n"
     f"? DAU: <b>{stats.get('dau', 0):,}</b>\n"
     f"? WAU: <b>{stats.get('wau', 0):,}</b>\n"
     f"? MAU: <b>{stats.get('mau', 0):,}</b>\n"
     f"? Premium: <b>{stats.get('premium_users', 0)}</b>\n"
     f"? New Today: <b>{stats.get('new_today', 0)}</b>\n"
     f"? Conversion: <b>{stats.get('conversion_rate_pct', 0)}%</b>\n"
   )
   await message.reply_text(
     text=text,
     parse_mode="HTML",
     reply_markup=build_admin_menu(),
   )





async def handle_admin_callback(
   query: CallbackQuery,
   parts: list,
   context: ContextTypes.DEFAULT_TYPE,
) -> None:
   """Handle all admin panel callbacks."""
   user_id = query.from_user.id
   if not is_admin(user_id):
     await query.answer("? Admin only!", show_alert=True)
     return
   action = parts[1] if len(parts) > 1 else "main"
   if action == "main":
     stats = await db.get_dashboard_stats()
     text = (
       "? <b>ADMIN PANEL</b>\n\n"
       f"? Total Users: <b>{stats.get('total_users', 0):,}</b>\n"
       f"? DAU: <b>{stats.get('dau', 0):,}</b>\n"
       f"? WAU: <b>{stats.get('wau', 0):,}</b>\n"
       f"? MAU: <b>{stats.get('mau', 0):,}</b>\n"
       f"? New Today: <b>{stats.get('new_today', 0)}</b>\n"
     )
     try:
       await query.edit_message_text(
          text=text, parse_mode="HTML",
          reply_markup=build_admin_menu(),
       )
     except BadRequest:
       pass
   elif action == "dash":
     stats = await db.get_dashboard_stats()
     text = (
       "? <b>DASHBOARD</b>\n\n"
       f"? Total Users: <b>{stats.get('total_users', 0):,}</b>\n"
       f"? DAU: <b>{stats.get('dau', 0):,}</b>\n"
       f"? WAU: <b>{stats.get('wau', 0):,}</b>\n"
       f"? MAU: <b>{stats.get('mau', 0):,}</b>\n"
       f"? Premium Users: <b>{stats.get('premium_users', 0)}</b>\n"
       f"? Banned: <b>{stats.get('banned_users', 0)}</b>\n"
       f"? New Today: <b>{stats.get('new_today', 0)}</b>\n"
       f"? Conversion: <b>{stats.get('conversion_rate_pct', 0)}%</b>\n"
     )
     try:
       await query.edit_message_text(
          text=text, parse_mode="HTML",
          reply_markup=build_admin_menu(),
       )
     except BadRequest:
       pass
   elif action == "users":
     try:
       await query.edit_message_text(
          text="? <b>User Management</b>\n\nSelect an action:",
          parse_mode="HTML",
          reply_markup=build_user_management_keyboard(),
       )
     except BadRequest:
       pass
   elif action == "config":
     current = await db.get_platform_config()
     try:
       await query.edit_message_text(
          text="?? <b>Bot Settings</b>\n\nTap to edit any value:",
          parse_mode="HTML",
          reply_markup=build_config_keyboard(current),
       )
     except BadRequest:



       pass

   elif action == "edit":
     if len(parts) < 3:
       return
     key = parts[2]
     meta = ADMIN_CONFIGURABLE.get(key, {})
     if not meta:
       await query.answer("Unknown setting", show_alert=True)
       return
     current = await db.get_platform_config()
     current_value = current.get(key, "N/A")
     context.user_data["admin_editing"] = key
     text = (
       f"[edit]? <b>Editing: {meta['label']}</b>\n\n"
       f"Current value: <b>{current_value}</b>\n"
       f"Type: {meta['type']}\n"
       f"Range: {meta.get('min', 'N/A')} -- {meta.get('max', 'N/A')}\n\n"
       f"Type the new value below ?"
     )
     try:
       await query.edit_message_text(text=text, parse_mode="HTML")
     except BadRequest:
       pass
   elif action == "wd":
     withdrawals = await db.get_pending_withdrawals()
     text = f"? <b>Pending Withdrawals ({len(withdrawals)})</b>"
     try:
       await query.edit_message_text(
          text=text, parse_mode="HTML",
          reply_markup=build_withdrawal_list_keyboard(withdrawals),
       )
     except BadRequest:
       pass
   elif action == "wdview":
     if len(parts) < 3:
       return
     wd_id = parts[2]
     # Get withdrawal details
     try:
       result = await (
          db.client.table("withdrawals")
          .select("*, users(telegram_id, username, first_name, balance)")
          .eq("id", wd_id)
          .limit(1)
          .execute()
       )
       if not result.data:
          await query.answer("Not found", show_alert=True)
          return
       wd = result.data[0]
       user_info = wd.get("users", {})
       text = (
          f"? <b>Withdrawal Request</b>\n\n"
          f"? User: {user_info.get('first_name', 'Unknown')} "
          f"(@{user_info.get('username', 'N/A')})\n"
          f"? ID: {wd.get('user_id', 'N/A')}\n"
          f"? Amount: ?{wd.get('amount', 0):,}\n"
          f"? UPI: <code>{wd.get('upi_id', 'N/A')}</code>\n"
          f"? Balance: ?{user_info.get('balance', 0):,}\n"
          f"? Requested: {wd.get('created_at', 'N/A')[:16]}\n"
       )
       await query.edit_message_text(
          text=text, parse_mode="HTML",
          reply_markup=build_withdrawal_action_keyboard(wd_id),



       )
     except BadRequest:
       pass
   elif action == "wdok":
     if len(parts) < 3:
       return
     wd_id = parts[2]
     await db.process_withdrawal(wd_id, "approved", "Approved by admin")
     await query.answer("[OK] Withdrawal approved!", show_alert=True)
     # Notify user
     try:
       result = await (
          db.client.table("withdrawals")
          .select("user_id, amount")
          .eq("id", wd_id)
          .limit(1)
          .execute()
       )
       if result.data:
          wd = result.data[0]
          await context.bot.send_message(
            chat_id=wd["user_id"],
            text=(
              f"[OK] <b>Withdrawal Approved!</b>\n\n"
              f"? ?{wd['amount']:,} will be sent "
              f"to your UPI within 24 hours.\n\n"
              f"Thank you for playing! ?"
            ),
            parse_mode="HTML",
          )
     except Exception:
       pass
     # Refresh list
     withdrawals = await db.get_pending_withdrawals()
     try:
       await query.edit_message_text(
          text=f"? <b>Pending Withdrawals ({len(withdrawals)})</b>",
          parse_mode="HTML",
          reply_markup=build_withdrawal_list_keyboard(withdrawals),
       )
     except BadRequest:
       pass
   elif action == "wdno":
     if len(parts) < 3:
       return
     wd_id = parts[2]
     # Get withdrawal to refund
     try:
       result = await (
          db.client.table("withdrawals")
          .select("user_id, amount")
          .eq("id", wd_id)
          .limit(1)
          .execute()
       )
       if result.data:
          wd = result.data[0]
          # Refund
          await db.credit_wallet(
            wd["user_id"], wd["amount"],
            TxnType.BET_REFUND,
            "Withdrawal rejected -- refunded",
          )
          await db.process_withdrawal(
            wd_id, "rejected", "Rejected by admin"
          )
          await context.bot.send_message(
            chat_id=wd["user_id"],



            text=(
              f"[X] <b>Withdrawal Rejected</b>\n\n"
              f"? ?{wd['amount']:,} has been returned "
              f"to your wallet.\n\n"
              f"Contact /support for questions."
            ),
            parse_mode="HTML",
          )
     except Exception as e:
       logger.error("Withdrawal rejection error: %s", e)
     await query.answer("[X] Withdrawal rejected", show_alert=True)
   elif action == "bcast":
     context.user_data["admin_broadcast"] = True
     text = (
       "? <b>Broadcast Message</b>\n\n"
       "Type the message you want to send to ALL users.\n"
       "HTML formatting supported.\n\n"
       "Type /cancel to abort."
     )
     try:
       await query.edit_message_text(text=text, parse_mode="HTML")
     except BadRequest:
       pass
   elif action == "sync":
     await query.answer("? Syncing matches...", show_alert=False)
     matches = await cricket_api.get_current_matches()
     synced = 0
     for m in matches:
       try:
          await db.upsert_match(m)
          synced += 1
       except Exception:
          pass
     await query.answer(
       f"[OK] Synced {synced} matches!", show_alert=True
     )
   elif action == "ban":
     context.user_data["admin_action"] = "ban"
     try:
       await query.edit_message_text(
          "? <b>Ban User</b>\n\n"
          "Send the Telegram ID of the user to ban:",
          parse_mode="HTML",
       )
     except BadRequest:
       pass
   elif action == "unban":
     context.user_data["admin_action"] = "unban"
     try:
       await query.edit_message_text(
          "[OK] <b>Unban User</b>\n\n"
          "Send the Telegram ID of the user to unban:",
          parse_mode="HTML",
       )
     except BadRequest:
       pass
   elif action == "credit":
     context.user_data["admin_action"] = "credit"
     try:
       await query.edit_message_text(
          "? <b>Credit User</b>\n\n"
          "Send: <code>USER_ID AMOUNT</code>\n"
          "Example: <code>123456789 100</code>",
          parse_mode="HTML",
       )
     except BadRequest:



       pass

   elif action == "debit":
     context.user_data["admin_action"] = "debit"
     try:
       await query.edit_message_text(
          "? <b>Debit User</b>\n\n"
          "Send: <code>USER_ID AMOUNT</code>\n"
          "Example: <code>123456789 100</code>",
          parse_mode="HTML",
       )
     except BadRequest:
       pass
   elif action == "revenue":
     # Revenue report
     stats = await db.get_dashboard_stats()
     try:
       total_revenue_result = await (
          db.client.table("transactions")
          .select("amount")
          .eq("txn_type", TxnType.COMMISSION.value)
          .execute()
       )
       total_revenue = sum(
          t.get("amount", 0)
          for t in (total_revenue_result.data or [])
       )
     except Exception:
       total_revenue = 0
     text = (
       f"? <b>Revenue Report</b>\n\n"
       f"? Total Commission Earned: <b>?{total_revenue:,}</b>\n"
       f"? Total Users: <b>{stats.get('total_users', 0):,}</b>\n"
       f"? Active Today: <b>{stats.get('dau', 0)}</b>\n"
     )
     try:
       await query.edit_message_text(
          text=text, parse_mode="HTML",
          reply_markup=build_admin_menu(),
       )
     except BadRequest:
       pass
async def handle_admin_text(
   update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
   """Handle admin text inputs (broadcast, ban, config edits)."""
   user = update.effective_user
   message = update.effective_message
   if not user or not message or not is_admin(user.id):
     return
   text = message.text or ""
   if text.startswith("/"):
     return
   # Check for broadcast mode
   if context.user_data.get("admin_broadcast"):
     context.user_data.pop("admin_broadcast", None)
     user_ids = await db.get_all_active_user_ids()
     sent = 0
     failed = 0
     status_msg = await message.reply_text(
       f"? Broadcasting to {len(user_ids)} users..."
     )
     for uid in user_ids:
       try:



          await context.bot.send_message(
            chat_id=uid,
            text=text,
            parse_mode="HTML",
          )
          sent += 1
       except Exception:
          failed += 1
       if sent % 30 == 0:
          await asyncio.sleep(1) # Rate limiting
     try:
       await status_msg.edit_text(
          f"[OK] Broadcast complete!\n"
          f"? Sent: {sent}\n[X] Failed: {failed}"
       )
     except BadRequest:
       pass
     return
   # Check for config editing
   editing_key = context.user_data.get("admin_editing")
   if editing_key:
     context.user_data.pop("admin_editing", None)
     meta = ADMIN_CONFIGURABLE.get(editing_key, {})
     try:
       if meta.get("type") == "int":
          value = int(text.strip())
       elif meta.get("type") == "float":
          value = float(text.strip())
       else:
          value = text.strip()
       # Validate range
       if isinstance(value, (int, float)):
          if value < meta.get("min", float("-inf")):
            await message.reply_text(
              f"[X] Value too low. Min: {meta['min']}"
            )
            return
          if value > meta.get("max", float("inf")):
            await message.reply_text(
              f"[X] Value too high. Max: {meta['max']}"
            )
            return
       success = await db.update_platform_config(editing_key, value)
       if success:
          await message.reply_text(
            f"[OK] <b>{meta.get('label', editing_key)}</b> "
            f"updated to <b>{value}</b>",
            parse_mode="HTML",
          )
       else:
          await message.reply_text("[X] Failed to update. Try again.")
     except (ValueError, TypeError):
       await message.reply_text(
          f"[X] Invalid value. Expected {meta.get('type', 'text')}."
       )
     return
   # Check for admin actions (ban/unban/credit/debit)
   admin_action = context.user_data.get("admin_action")
   if admin_action:
     context.user_data.pop("admin_action", None)
     if admin_action in ("ban", "unban"):
       try:
          target_id = int(text.strip())
       except ValueError:



          await message.reply_text("[X] Invalid user ID")
          return
       if admin_action == "ban":
          success = await db.ban_user(target_id)
          await message.reply_text(
            f"{'[OK] User banned' if success else '[X] Failed'}: {target_id}"
          )
       else:
          success = await db.unban_user(target_id)
          await message.reply_text(
            f"{'[OK] User unbanned' if success else '[X] Failed'}: {target_id}"
          )
     elif admin_action in ("credit", "debit"):
       parts = text.strip().split()
       if len(parts) != 2:
          await message.reply_text("[X] Format: USER_ID AMOUNT")
          return
       try:
          target_id = int(parts[0])
          amount = int(parts[1])
       except ValueError:
          await message.reply_text("[X] Invalid format")
          return
       if admin_action == "credit":
          success, bal = await db.credit_wallet(
            target_id, amount,
            TxnType.ADMIN_CREDIT,
            f"Admin credit by {user.id}",
          )
          await message.reply_text(
            f"{'[OK]' if success else '[X]'} "
            f"Credited ?{amount} to {target_id}. "
            f"New balance: ?{bal}"
          )
       else:
          success, bal = await db.debit_wallet(
            target_id, amount,
            TxnType.ADMIN_DEBIT,
            f"Admin debit by {user.id}",
          )
          await message.reply_text(
            f"{'[OK]' if success else '[X]'} "
            f"Debited ?{amount} from {target_id}. "
            f"New balance: ?{bal}"
          )
