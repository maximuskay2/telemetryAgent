-- Commercial schema (commercial-roadmap §8.3, frozen at C-J0; built at C-J1).
--
-- Idempotent: every statement is safe to re-run (ensure_schema() re-runs
-- this whole file whenever its hash changes, tracked in schemaversions).
-- Table shapes match §8.3 exactly; only defaults/constraints are added here.
-- New columns on existing tables must be added as ALTER TABLE ...
-- ADD COLUMN IF NOT EXISTS lines (CREATE TABLE IF NOT EXISTS will not
-- widen a table that is already there).
--
-- Row-level security: every org-scoped table forces org_id =
-- current_setting('app.org_id'). The API sets app.org_id (+ app.user_id) per
-- transaction; with no setting the policies match nothing (fail closed).
-- Role checks (owner/admin/member/viewer) are application-enforced in routes;
-- RLS guarantees org isolation even when a query forgets its filter.
-- No billing columns: Phase 4's migration adds subscriptions then.

CREATE TABLE IF NOT EXISTS schemaversions (
    hash text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orgs (
    id text PRIMARY KEY,
    name text NOT NULL DEFAULT '',
    data_key_enc text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE IF NOT EXISTS users (
    id text PRIMARY KEY,
    external_id text UNIQUE NOT NULL,
    email text UNIQUE NOT NULL,
    name text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    last_login timestamptz
);

CREATE TABLE IF NOT EXISTS memberships (
    org_id text NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
    user_id text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role text NOT NULL DEFAULT 'member',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, user_id)
);

CREATE TABLE IF NOT EXISTS device_tokens (
    id text PRIMARY KEY,
    org_id text NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
    user_id text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash text UNIQUE NOT NULL,
    label text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    revoked_at timestamptz
);

CREATE TABLE IF NOT EXISTS pairing_codes (
    code_hash text PRIMARY KEY,
    org_id text NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
    user_id text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    label text NOT NULL DEFAULT '',
    expires_at timestamptz NOT NULL DEFAULT now(),
    used_at timestamptz
);

CREATE TABLE IF NOT EXISTS invites (
    token_hash text PRIMARY KEY,
    org_id text NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
    email text NOT NULL DEFAULT '',
    role text NOT NULL DEFAULT 'member',
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT now(),
    accepted_at timestamptz
);

CREATE TABLE IF NOT EXISTS systems (
    id text PRIMARY KEY,
    org_id text NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
    profile jsonb NOT NULL DEFAULT '{}',
    status text NOT NULL DEFAULT 'draft',
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE IF NOT EXISTS systems_versions (
    system_id text NOT NULL REFERENCES systems (id) ON DELETE CASCADE,
    version integer NOT NULL,
    profile jsonb NOT NULL DEFAULT '{}',
    at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (system_id, version)
);

CREATE TABLE IF NOT EXISTS connections (
    id text PRIMARY KEY,
    org_id text NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
    system_id text NOT NULL,
    kind text NOT NULL DEFAULT '',
    config jsonb NOT NULL DEFAULT '{}',
    secret_enc text NOT NULL DEFAULT '',
    secret_hint text NOT NULL DEFAULT '',
    key_hash text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'waiting',
    detail text NOT NULL DEFAULT '',
    last_seen timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runs (
    id text PRIMARY KEY,
    org_id text NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
    system_id text,
    domain text NOT NULL DEFAULT '',
    kind text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT '',
    language text,
    fingerprint text NOT NULL DEFAULT '',
    pr_url text NOT NULL DEFAULT '',
    result jsonb NOT NULL DEFAULT '{}',
    cost_estimate_usd double precision NOT NULL DEFAULT 0,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS runs_org_fingerprint
    ON runs (org_id, fingerprint);

CREATE TABLE IF NOT EXISTS audit (
    id bigserial PRIMARY KEY,
    org_id text NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
    actor text NOT NULL DEFAULT '',
    action text NOT NULL DEFAULT '',
    detail jsonb NOT NULL DEFAULT '{}',
    at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rate_stamps (
    org_id text NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
    system_id text NOT NULL,
    at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, system_id)
);

CREATE TABLE IF NOT EXISTS pause_state (
    org_id text PRIMARY KEY REFERENCES orgs (id) ON DELETE CASCADE,
    paused boolean NOT NULL DEFAULT false,
    at timestamptz NOT NULL DEFAULT now(),
    by_user text NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS usage_events (
    id bigserial PRIMARY KEY,
    org_id text NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
    system_id text,
    run_id text,
    kind text NOT NULL,
    quantity double precision NOT NULL DEFAULT 1,
    unit text NOT NULL DEFAULT 'count',
    provider text NOT NULL DEFAULT '',
    model text NOT NULL DEFAULT '',
    language text,
    cost_estimate_usd double precision NOT NULL DEFAULT 0,
    at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS usage_org_at ON usage_events (org_id, at);

CREATE TABLE IF NOT EXISTS allowances (
    org_id text PRIMARY KEY REFERENCES orgs (id) ON DELETE CASCADE,
    systems_limit integer NOT NULL DEFAULT 3,
    devices_limit integer NOT NULL DEFAULT 5,
    fix_runs_limit integer NOT NULL DEFAULT 30,
    cost_ceiling_usd double precision NOT NULL DEFAULT 25.0,
    fix_runs_used integer NOT NULL DEFAULT 0,
    cost_used_usd double precision NOT NULL DEFAULT 0,
    period_month text NOT NULL DEFAULT '',
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- --- RLS -----------------------------------------------------------------
-- One setting per transaction: SET LOCAL app.org_id = '<org>';
-- SET LOCAL app.user_id = '<user>'. Bootstrap (signup/org create) sets only
-- app.user_id; org rows become visible through the membership created next.

ALTER TABLE orgs ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE device_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE pairing_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE systems ENABLE ROW LEVEL SECURITY;
ALTER TABLE systems_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE rate_stamps ENABLE ROW LEVEL SECURITY;
ALTER TABLE pause_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE allowances ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS org_iso ON device_tokens;
CREATE POLICY org_iso ON device_tokens
    USING (org_id = current_setting('app.org_id', true))
    WITH CHECK (org_id = current_setting('app.org_id', true));

DROP POLICY IF EXISTS org_iso ON pairing_codes;
CREATE POLICY org_iso ON pairing_codes
    USING (org_id = current_setting('app.org_id', true))
    WITH CHECK (org_id = current_setting('app.org_id', true));

DROP POLICY IF EXISTS org_iso ON invites;
CREATE POLICY org_iso ON invites
    USING (org_id = current_setting('app.org_id', true))
    WITH CHECK (org_id = current_setting('app.org_id', true));

DROP POLICY IF EXISTS org_iso ON systems;
CREATE POLICY org_iso ON systems
    USING (org_id = current_setting('app.org_id', true))
    WITH CHECK (org_id = current_setting('app.org_id', true));

DROP POLICY IF EXISTS org_iso ON connections;
CREATE POLICY org_iso ON connections
    USING (org_id = current_setting('app.org_id', true))
    WITH CHECK (org_id = current_setting('app.org_id', true));

DROP POLICY IF EXISTS org_iso ON runs;
CREATE POLICY org_iso ON runs
    USING (org_id = current_setting('app.org_id', true))
    WITH CHECK (org_id = current_setting('app.org_id', true));

DROP POLICY IF EXISTS org_iso ON audit;
CREATE POLICY org_iso ON audit
    USING (org_id = current_setting('app.org_id', true))
    WITH CHECK (org_id = current_setting('app.org_id', true));

DROP POLICY IF EXISTS org_iso ON rate_stamps;
CREATE POLICY org_iso ON rate_stamps
    USING (org_id = current_setting('app.org_id', true))
    WITH CHECK (org_id = current_setting('app.org_id', true));

DROP POLICY IF EXISTS org_iso ON pause_state;
CREATE POLICY org_iso ON pause_state
    USING (org_id = current_setting('app.org_id', true))
    WITH CHECK (org_id = current_setting('app.org_id', true));

DROP POLICY IF EXISTS org_iso ON usage_events;
CREATE POLICY org_iso ON usage_events
    USING (org_id = current_setting('app.org_id', true))
    WITH CHECK (org_id = current_setting('app.org_id', true));

DROP POLICY IF EXISTS org_iso ON allowances;
CREATE POLICY org_iso ON allowances
    USING (org_id = current_setting('app.org_id', true))
    WITH CHECK (org_id = current_setting('app.org_id', true));

-- Memberships: my own rows (org switcher) plus my current org's (members page).
DROP POLICY IF EXISTS member_read ON memberships;
CREATE POLICY member_read ON memberships FOR SELECT
    USING (user_id = current_setting('app.user_id', true)
        OR org_id = current_setting('app.org_id', true));
DROP POLICY IF EXISTS member_write ON memberships;
CREATE POLICY member_write ON memberships FOR INSERT
    WITH CHECK (org_id = current_setting('app.org_id', true));
DROP POLICY IF EXISTS member_update ON memberships;
CREATE POLICY member_update ON memberships FOR UPDATE
    USING (org_id = current_setting('app.org_id', true))
    WITH CHECK (org_id = current_setting('app.org_id', true));
DROP POLICY IF EXISTS member_remove ON memberships;
CREATE POLICY member_remove ON memberships FOR DELETE
    USING (org_id = current_setting('app.org_id', true));

-- Versions inherit their system's org (no org_id column of their own).
DROP POLICY IF EXISTS org_iso ON systems_versions;
CREATE POLICY org_iso ON systems_versions
    USING (system_id IN (
        SELECT id FROM systems
        WHERE org_id = current_setting('app.org_id', true)))
    WITH CHECK (system_id IN (
        SELECT id FROM systems
        WHERE org_id = current_setting('app.org_id', true)));

-- Orgs: my orgs via membership (switcher), or my current org (in-org reads
-- such as the outbound-call secret lookup, which carries no user).
DROP POLICY IF EXISTS org_member ON orgs;
CREATE POLICY org_member ON orgs FOR SELECT
    USING (id = current_setting('app.org_id', true)
        OR id IN (
            SELECT org_id FROM memberships
            WHERE user_id = current_setting('app.user_id', true)));
DROP POLICY IF EXISTS org_create ON orgs;
CREATE POLICY org_create ON orgs FOR INSERT
    WITH CHECK (coalesce(current_setting('app.user_id', true), '') <> '');
DROP POLICY IF EXISTS org_member_write ON orgs;
CREATE POLICY org_member_write ON orgs FOR UPDATE
    USING (id = current_setting('app.org_id', true))
    WITH CHECK (id = current_setting('app.org_id', true));
DROP POLICY IF EXISTS org_member_delete ON orgs;
CREATE POLICY org_member_delete ON orgs FOR DELETE
    USING (id = current_setting('app.org_id', true));

-- Users: yourself (by id or by the verified provider sub the app sets as
-- app.external_id at login), plus members of your current org (members page).
DROP POLICY IF EXISTS user_self ON users;
CREATE POLICY user_self ON users FOR SELECT
    USING (id = current_setting('app.user_id', true)
        OR external_id = current_setting('app.external_id', true)
        OR id IN (
            SELECT user_id FROM memberships
            WHERE org_id = current_setting('app.org_id', true)));
DROP POLICY IF EXISTS user_create ON users;
CREATE POLICY user_create ON users FOR INSERT
    WITH CHECK (coalesce(current_setting('app.user_id', true), '') <> '');
DROP POLICY IF EXISTS user_self_write ON users;
CREATE POLICY user_self_write ON users FOR UPDATE
    USING (id = current_setting('app.user_id', true))
    WITH CHECK (id = current_setting('app.user_id', true));

-- Constrain table owners too (superusers still bypass RLS: production must
-- connect as the least-privilege app role from ensure_app_role, never as
-- the bootstrap superuser — see docs/ops-backups.md).
ALTER TABLE orgs FORCE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE memberships FORCE ROW LEVEL SECURITY;
ALTER TABLE device_tokens FORCE ROW LEVEL SECURITY;
ALTER TABLE pairing_codes FORCE ROW LEVEL SECURITY;
ALTER TABLE invites FORCE ROW LEVEL SECURITY;
ALTER TABLE systems FORCE ROW LEVEL SECURITY;
ALTER TABLE systems_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE connections FORCE ROW LEVEL SECURITY;
ALTER TABLE runs FORCE ROW LEVEL SECURITY;
ALTER TABLE audit FORCE ROW LEVEL SECURITY;
ALTER TABLE rate_stamps FORCE ROW LEVEL SECURITY;
ALTER TABLE pause_state FORCE ROW LEVEL SECURITY;
ALTER TABLE usage_events FORCE ROW LEVEL SECURITY;
ALTER TABLE allowances FORCE ROW LEVEL SECURITY;

-- --- Resolution functions ------------------------------------------------
-- Key -> org lookups run BEFORE any org is known, so they cannot set
-- app.org_id. These SECURITY DEFINER functions resolve them by hash only;
-- knowledge of the unguessable hash is the capability, so EXECUTE is PUBLIC.
DROP FUNCTION IF EXISTS resolve_connection_key(text, text);
CREATE FUNCTION resolve_connection_key(p_digest text, p_kind text)
RETURNS TABLE (
    id text, org_id text, system_id text, kind text, config jsonb,
    secret_hint text, key_hash text, status text, detail text,
    last_seen timestamptz, created_at timestamptz
) LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    SELECT id, org_id, system_id, connections.kind, config, secret_hint,
        key_hash, status, detail, last_seen, created_at
    FROM connections WHERE key_hash = p_digest AND connections.kind = p_kind;
$$;
GRANT EXECUTE ON FUNCTION resolve_connection_key(text, text) TO PUBLIC;

DROP FUNCTION IF EXISTS resolve_device_token(text);
CREATE FUNCTION resolve_device_token(digest text)
RETURNS TABLE (
    id text, org_id text, user_id text, label text,
    created_at timestamptz, last_used_at timestamptz, revoked_at timestamptz
) LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    SELECT id, org_id, user_id, label, created_at, last_used_at, revoked_at
    FROM device_tokens WHERE token_hash = digest;
$$;
GRANT EXECUTE ON FUNCTION resolve_device_token(text) TO PUBLIC;

DROP FUNCTION IF EXISTS claim_pairing_code_fn(text);
CREATE FUNCTION claim_pairing_code_fn(digest text)
RETURNS TABLE (org_id text, user_id text, label text)
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    UPDATE pairing_codes SET used_at = now()
    WHERE code_hash = digest AND used_at IS NULL AND expires_at > now()
    RETURNING org_id, user_id, label;
$$;
GRANT EXECUTE ON FUNCTION claim_pairing_code_fn(text) TO PUBLIC;

DROP FUNCTION IF EXISTS resolve_invite(text);
CREATE FUNCTION resolve_invite(digest text)
RETURNS TABLE (
    org_id text, email text, role text, created_at timestamptz,
    expires_at timestamptz, accepted_at timestamptz
) LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    SELECT org_id, email, role, created_at, expires_at, accepted_at
    FROM invites WHERE token_hash = digest;
$$;
GRANT EXECUTE ON FUNCTION resolve_invite(text) TO PUBLIC;

-- --- Retention sweep (C-J5) -------------------------------------------------
-- The app role cannot see across orgs (RLS), so the retention script calls
-- these SECURITY DEFINER functions. Floors keep a bad argument from wiping
-- recent history: audit keeps >= 7 days, versions keep >= 5 per system.
DROP FUNCTION IF EXISTS sweep_audit_older_than(int);
CREATE FUNCTION sweep_audit_older_than(p_days int)
RETURNS int LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    days int := GREATEST(COALESCE(p_days, 90), 7);
    removed int := 0;
BEGIN
    DELETE FROM audit WHERE at < now() - make_interval(days => days);
    GET DIAGNOSTICS removed = ROW_COUNT;
    RETURN removed;
END;
$$;
GRANT EXECUTE ON FUNCTION sweep_audit_older_than(int) TO PUBLIC;

DROP FUNCTION IF EXISTS sweep_system_versions_keep(int);
CREATE FUNCTION sweep_system_versions_keep(p_keep int)
RETURNS int LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    keep int := GREATEST(COALESCE(p_keep, 20), 5);
    removed int := 0;
BEGIN
    DELETE FROM systems_versions v USING (
        SELECT system_id, version,
            ROW_NUMBER() OVER (
                PARTITION BY system_id ORDER BY version DESC
            ) AS rn
        FROM systems_versions
    ) ranked
    WHERE v.system_id = ranked.system_id
        AND v.version = ranked.version
        AND ranked.rn > keep;
    GET DIAGNOSTICS removed = ROW_COUNT;
    RETURN removed;
END;
$$;
GRANT EXECUTE ON FUNCTION sweep_system_versions_keep(int) TO PUBLIC;
