-- Migration: replace password_hash with has_password boolean
-- Storing bcrypt hashes in public.users is redundant — Supabase Auth owns
-- password verification. We only need a flag so the frontend knows whether
-- an OAuth user has completed the set-password step.

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS has_password boolean NOT NULL DEFAULT false;

-- Back-fill from existing data: anyone who already has a hash has a password.
UPDATE public.users
SET has_password = true
WHERE password_hash IS NOT NULL;

ALTER TABLE public.users
    DROP COLUMN IF EXISTS password_hash;
