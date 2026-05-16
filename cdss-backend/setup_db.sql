-- ─────────────────────────────────────────────────────────────────────────────
-- AI-CDSS PostgreSQL Setup Script
-- Run this ONCE to create the database, user, and seed initial data
-- ─────────────────────────────────────────────────────────────────────────────

-- Step 1: Connect as postgres superuser first
-- psql -U postgres

-- Create database and user
CREATE USER cdss_user WITH PASSWORD 'cdss_password';
CREATE DATABASE cdss_db OWNER cdss_user;
GRANT ALL PRIVILEGES ON DATABASE cdss_db TO cdss_user;

-- Connect to the new database
\c cdss_db

-- Grant schema permissions
GRANT ALL ON SCHEMA public TO cdss_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cdss_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO cdss_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO cdss_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO cdss_user;
