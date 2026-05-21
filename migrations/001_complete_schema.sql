-- /================================================================\
-- || CRICBET ARENA -- Complete Database Schema ||
-- || Run this in Supabase SQL Editor  ||
-- \================================================================/
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
-- =======================================
-- 1. USERS TABLE
-- =======================================
CREATE TABLE IF NOT EXISTS users (
   id         UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
   telegram_id BIGINT UNIQUE NOT NULL,
   username   TEXT DEFAULT '',
   first_name TEXT NOT NULL DEFAULT 'User',
   last_name  TEXT DEFAULT '',
   language_code TEXT DEFAULT 'en',
   -- Status
   is_premium BOOLEAN DEFAULT FALSE NOT NULL,
   is_banned  BOOLEAN DEFAULT FALSE NOT NULL,
   is_admin   BOOLEAN DEFAULT FALSE NOT NULL,
   has_blocked_bot BOOLEAN DEFAULT FALSE NOT NULL,
   -- Wallet
   balance    INTEGER DEFAULT 0 NOT NULL CHECK (balance >= 0),
   -- Stats
   total_winnings INTEGER DEFAULT 0 NOT NULL,
   wins_count INTEGER DEFAULT 0 NOT NULL,
   bets_today INTEGER DEFAULT 0 NOT NULL,
   -- Engagement
   streak_days INTEGER DEFAULT 0 NOT NULL,
   last_active_date DATE DEFAULT CURRENT_DATE,
   onboarding_done BOOLEAN DEFAULT FALSE,
   notifications_on BOOLEAN DEFAULT TRUE NOT NULL,
   language   TEXT DEFAULT 'en',
   -- Referral
   referral_code TEXT UNIQUE DEFAULT substr(md5(random()::text), 1, 8),
   referred_by BIGINT,
   -- Timestamps
   created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
   updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
   last_seen  TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_referral ON users(referral_code);
CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_users_premium ON users(is_premium) WHERE is_premium = TRUE;
CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned) WHERE is_banned = TRUE;
CREATE INDEX IF NOT EXISTS idx_users_active ON users(has_blocked_bot, is_banned);
-- Auto-update trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$



BEGIN
   NEW.updated_at = NOW();
   RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_users_updated ON users;
CREATE TRIGGER trg_users_updated
   BEFORE UPDATE ON users
   FOR EACH ROW EXECUTE FUNCTION update_updated_at();
-- =======================================
-- 2. MATCHES TABLE
-- =======================================
CREATE TABLE IF NOT EXISTS matches (
   id         UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
   api_match_id TEXT UNIQUE NOT NULL,
   name       TEXT NOT NULL,
   match_type TEXT DEFAULT 'unknown',
   status     TEXT NOT NULL DEFAULT 'upcoming'
                 CHECK (status IN ('upcoming','live','completed','abandoned')),
   -- Teams
   team1      TEXT NOT NULL,
   team2      TEXT NOT NULL,
   team1_short TEXT DEFAULT '',
   team2_short TEXT DEFAULT '',
   team1_img  TEXT DEFAULT '',
   team2_img  TEXT DEFAULT '',
   -- Match info
   venue      TEXT DEFAULT '',
   match_start TIMESTAMPTZ,
   score_text TEXT DEFAULT '',
   match_status_text TEXT DEFAULT '',
   toss_winner TEXT DEFAULT '',
   toss_choice TEXT DEFAULT '',
   match_winner TEXT DEFAULT '',
   series_name TEXT DEFAULT '',
   -- Raw API data for reference
   raw_data   JSONB DEFAULT '{}',
   -- Timestamps
   created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
   updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_matches_api_id ON matches(api_match_id);
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);
CREATE INDEX IF NOT EXISTS idx_matches_start ON matches(match_start DESC);
DROP TRIGGER IF EXISTS trg_matches_updated ON matches;
CREATE TRIGGER trg_matches_updated
   BEFORE UPDATE ON matches
   FOR EACH ROW EXECUTE FUNCTION update_updated_at();
-- =======================================
-- 3. BETTING ROOMS TABLE
-- =======================================
CREATE TABLE IF NOT EXISTS rooms (
   id         UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
   match_id   UUID NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
   -- Players
   creator_id BIGINT NOT NULL,
   joiner_id  BIGINT,
   winner_id  BIGINT,
   -- Bet details
   bet_type   TEXT NOT NULL DEFAULT 'winner',



   bet_amount INTEGER NOT NULL CHECK (bet_amount > 0),
   win_amount INTEGER NOT NULL CHECK (win_amount > 0),
   pool_amount INTEGER NOT NULL DEFAULT 0,
   max_players INTEGER NOT NULL DEFAULT 2,
   -- Picks
   creator_pick TEXT NOT NULL,
   joiner_pick TEXT DEFAULT '',
   -- Status
   status     TEXT NOT NULL DEFAULT 'open'
                 CHECK (status IN (
                   'open','locked','settled',
                   'cancelled','expired'
                 )),
   result_text TEXT DEFAULT '',
   -- Timestamps
   created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
   joined_at  TIMESTAMPTZ,
   settled_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_rooms_match ON rooms(match_id);
CREATE INDEX IF NOT EXISTS idx_rooms_creator ON rooms(creator_id);
CREATE INDEX IF NOT EXISTS idx_rooms_joiner ON rooms(joiner_id);
CREATE INDEX IF NOT EXISTS idx_rooms_status ON rooms(status);
CREATE INDEX IF NOT EXISTS idx_rooms_winner ON rooms(winner_id);
CREATE INDEX IF NOT EXISTS idx_rooms_open ON rooms(status, match_id)
   WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_rooms_locked ON rooms(status, match_id)
   WHERE status = 'locked';
CREATE INDEX IF NOT EXISTS idx_rooms_created ON rooms(created_at DESC);
-- =======================================
-- 4. TRANSACTIONS TABLE
-- =======================================
CREATE TABLE IF NOT EXISTS transactions (
   id         UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
   user_id    BIGINT NOT NULL,
   amount     INTEGER NOT NULL CHECK (amount > 0),
   txn_type   TEXT NOT NULL,
   direction  TEXT NOT NULL CHECK (direction IN ('credit','debit')),
   description TEXT DEFAULT '',
   reference_id TEXT DEFAULT '',
   created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_txn_user ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_txn_type ON transactions(txn_type);
CREATE INDEX IF NOT EXISTS idx_txn_created ON transactions(created_at DESC);
-- =======================================
-- 5. WITHDRAWALS TABLE
-- =======================================
CREATE TABLE IF NOT EXISTS withdrawals (
   id         UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
   user_id    BIGINT NOT NULL,
   amount     INTEGER NOT NULL CHECK (amount > 0),
   upi_id     TEXT NOT NULL,
   status     TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','approved','rejected')),
   admin_note TEXT DEFAULT '',
   created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
   processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_wd_user ON withdrawals(user_id);
CREATE INDEX IF NOT EXISTS idx_wd_status ON withdrawals(status);
CREATE INDEX IF NOT EXISTS idx_wd_pending ON withdrawals(status, created_at)
   WHERE status = 'pending';





-- =======================================
-- 6. SPINS TABLE (Lucky Wheel)
-- =======================================
CREATE TABLE IF NOT EXISTS spins (
   id         UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
   user_id    BIGINT NOT NULL,
   prize_amount INTEGER NOT NULL DEFAULT 0,
   created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spins_user ON spins(user_id);
CREATE INDEX IF NOT EXISTS idx_spins_created ON spins(created_at DESC);
-- =======================================
-- 7. BET TIERS TABLE (Admin configurable)
-- =======================================
CREATE TABLE IF NOT EXISTS bet_tiers (
   id         UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
   amount     INTEGER NOT NULL CHECK (amount > 0),
   winner_gets INTEGER NOT NULL CHECK (winner_gets > 0),
   label      TEXT NOT NULL,
   is_active  BOOLEAN DEFAULT TRUE NOT NULL,
   sort_order INTEGER DEFAULT 0,
   created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
-- Insert default tiers
INSERT INTO bet_tiers (amount, winner_gets, label, sort_order) VALUES
   (3, 5, '? ?3 Entry -> Win ?5', 1),
   (5, 9, '? ?5 Entry -> Win ?9', 2),
   (10, 18, '? ?10 Entry -> Win ?18', 3),
   (25, 45, '? ?25 Entry -> Win ?45', 4),
   (50, 90, '? ?50 Entry -> Win ?90', 5),
   (100, 180, '? ?100 Entry -> Win ?180', 6),
   (500, 900, '? ?500 Entry -> Win ?900', 7),
   (1000, 1800, '? ?1000 Entry -> Win ?1800', 8)
ON CONFLICT DO NOTHING;
-- =======================================
-- 8. PLATFORM CONFIG TABLE
-- =======================================
CREATE TABLE IF NOT EXISTS platform_config (
   id            INTEGER PRIMARY KEY DEFAULT 1,
   min_bet_amount INTEGER DEFAULT 3,
   platform_commission_pct FLOAT DEFAULT 16.67,
   max_bet_amount INTEGER DEFAULT 10000,
   free_credits_on_signup INTEGER DEFAULT 10,
   referral_bonus INTEGER DEFAULT 5,
   daily_free_bet_amount INTEGER DEFAULT 1,
   min_withdrawal INTEGER DEFAULT 50,
   bet_lock_before_match_mins INTEGER DEFAULT 5,
   maintenance_mode BOOLEAN DEFAULT FALSE,
   updated_at    TIMESTAMPTZ DEFAULT NOW()
);
-- Insert default config
INSERT INTO platform_config (id) VALUES (1) ON CONFLICT DO NOTHING;
-- =======================================
-- 9. ATOMIC WALLET FUNCTIONS (RPC)
-- =======================================
-- Credit balance atomically
CREATE OR REPLACE FUNCTION credit_balance(
   p_telegram_id BIGINT,
   p_amount INTEGER
) RETURNS INTEGER AS $$
DECLARE



   new_balance INTEGER;
BEGIN
   UPDATE users
   SET balance = balance + p_amount
   WHERE telegram_id = p_telegram_id
   RETURNING balance INTO new_balance;
   IF new_balance IS NULL THEN
     RAISE EXCEPTION 'User not found: %', p_telegram_id;
   END IF;
   RETURN new_balance;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
-- Debit balance atomically (with check)
CREATE OR REPLACE FUNCTION debit_balance(
   p_telegram_id BIGINT,
   p_amount INTEGER
) RETURNS INTEGER AS $$
DECLARE
   current_balance INTEGER;
   new_balance INTEGER;
BEGIN
   SELECT balance INTO current_balance
   FROM users
   WHERE telegram_id = p_telegram_id
   FOR UPDATE; -- Row-level lock
   IF current_balance IS NULL THEN
     RAISE EXCEPTION 'User not found: %', p_telegram_id;
   END IF;
   IF current_balance < p_amount THEN
     RAISE EXCEPTION 'Insufficient balance: has %, needs %',
       current_balance, p_amount;
   END IF;
   UPDATE users
   SET balance = balance - p_amount
   WHERE telegram_id = p_telegram_id
   RETURNING balance INTO new_balance;
   RETURN new_balance;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
-- =======================================
-- 10. DASHBOARD STATS VIEW
-- =======================================
CREATE OR REPLACE VIEW dashboard_stats AS
SELECT
   COUNT(*) as total_users,
   COUNT(*) FILTER (WHERE is_premium) as premium_users,
   COUNT(*) FILTER (WHERE is_banned) as banned_users,
   COUNT(*) FILTER (
     WHERE last_seen > NOW() - INTERVAL '1 day'
   ) as dau,
   COUNT(*) FILTER (
     WHERE last_seen > NOW() - INTERVAL '7 days'
   ) as wau,
   COUNT(*) FILTER (
     WHERE last_seen > NOW() - INTERVAL '30 days'
   ) as mau,
   COUNT(*) FILTER (
     WHERE created_at > NOW() - INTERVAL '1 day'
   ) as new_today,
   ROUND(
     COUNT(*) FILTER (WHERE is_premium)::NUMERIC
     / NULLIF(COUNT(*), 0) * 100, 2
   ) as conversion_rate_pct



FROM users
WHERE has_blocked_bot = FALSE;

-- =======================================
-- 11. ROW LEVEL SECURITY
-- =======================================
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE rooms ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE withdrawals ENABLE ROW LEVEL SECURITY;
ALTER TABLE spins ENABLE ROW LEVEL SECURITY;
ALTER TABLE bet_tiers ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_config ENABLE ROW LEVEL SECURITY;
-- Service role gets full access (bot backend uses service_role key)
CREATE POLICY IF NOT EXISTS srv_users ON users FOR ALL TO service_role
   USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY IF NOT EXISTS srv_matches ON matches FOR ALL TO service_role
   USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY IF NOT EXISTS srv_rooms ON rooms FOR ALL TO service_role
   USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY IF NOT EXISTS srv_txn ON transactions FOR ALL TO service_role
   USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY IF NOT EXISTS srv_wd ON withdrawals FOR ALL TO service_role
   USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY IF NOT EXISTS srv_spins ON spins FOR ALL TO service_role
   USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY IF NOT EXISTS srv_tiers ON bet_tiers FOR ALL TO service_role
   USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY IF NOT EXISTS srv_config ON platform_config FOR ALL TO service_role
   USING (TRUE) WITH CHECK (TRUE);
-- =======================================
-- 12. DAILY RESET FUNCTION
-- =======================================
CREATE OR REPLACE FUNCTION reset_daily_counters()
RETURNS void AS $$
BEGIN
   UPDATE users SET bets_today = 0
   WHERE bets_today > 0;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
-- =======================================
-- VERIFICATION QUERY
-- Run this to confirm schema is correct:
-- =======================================
-- SELECT table_name FROM information_schema.tables
-- WHERE table_schema = 'public'
-- ORDER BY table_name;
--
-- Expected: bet_tiers, matches, platform_config, rooms,
--      spins, transactions, users, withdrawals
