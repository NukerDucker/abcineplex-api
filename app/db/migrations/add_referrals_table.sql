-- Migration: add referrals table
-- Replaces the referral_pending hack in membership_transactions with a proper table.
-- A user can only be referred once (UNIQUE on referred_id).

CREATE TABLE IF NOT EXISTS referrals (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_id    uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    referred_id    uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    points_awarded boolean     NOT NULL DEFAULT false,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (referred_id)
);
