-- Run once on first PostgreSQL startup
-- Creates the database (already handled by POSTGRES_DB env var)
-- This script sets additional hardening options.

-- Restrict public schema access
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- Create read-only reporting role (optional)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'escrow_readonly') THEN
        CREATE ROLE escrow_readonly;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE escrow_bot TO escrow_readonly;
GRANT USAGE ON SCHEMA public TO escrow_readonly;
-- Grant SELECT after tables are created (run via migration or separately)
