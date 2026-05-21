# CricBet Arena - Telegram Cricket Betting Bot

Production-grade Telegram bot for head-to-head cricket betting with auto-settlement, anti-fraud, admin panel, and 20+ engagement features.

**Stack:** Python 3.11 · python-telegram-bot v21 · Supabase (PostgreSQL) · CricAPI · Render.com

## Quick Start

### 1. Prerequisites
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- [Supabase](https://supabase.com) project (free tier)
- [CricAPI](https://cricapi.com) key (free tier)
- [Render.com](https://render.com) account

### 2. Setup Database
1. Open Supabase → SQL Editor
2. Paste entire contents of `migrations/001_complete_schema.sql`
3. Run

### 3. Configure Env Vars
Copy `.env.example` → `.env` and fill in your values.

### 4. Deploy to Render
1. Push this repo to GitHub
2. Render → New → Web Service → connect GitHub repo
3. Build: `pip install -r requirements.txt`
4. Start: `python -m bot.main`
5. Add all environment variables from `.env.example`
6. Deploy

### 5. Keep Alive
Add an [UptimeRobot](https://uptimerobot.com) HTTPS monitor pointing at `https://<your-app>.onrender.com/webhook` every 5 minutes.

## Project Structure
```
bot/
  config.py · constants.py · database.py · main.py
  handlers/    start, betting, wallet, admin, callbacks
  keyboards/   main_menu, betting, admin
  services/    cricket_api, settlement, scheduler, rate_limiter
  middlewares/ auth, rate_limit, anti_fraud
migrations/001_complete_schema.sql
render.yaml · Procfile · requirements.txt · runtime.txt
```

## Legal
Online betting may be regulated in your jurisdiction. Ensure compliance with local laws and add appropriate disclaimers, age verification, and responsible-gambling notices.
