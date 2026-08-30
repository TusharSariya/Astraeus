CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS weather_experiment;

CREATE TYPE weather_experiment.job_state AS ENUM (
    'queued', 'running', 'succeeded', 'failed', 'cancelled'
);

CREATE TYPE weather_experiment.revision_state AS ENUM (
    'staged', 'published', 'superseded', 'rejected'
);

CREATE TABLE weather_experiment.sources (
    source_id text PRIMARY KEY,
    producer text NOT NULL,
    product text NOT NULL,
    registry_status text NOT NULL CHECK (registry_status IN (
        'active', 'implementing', 'credential_required', 'licence_review',
        'unavailable', 'duplicate_evidence', 'unsupported_field', 'retired',
        'rejected'
    )),
    adapter_version text NOT NULL,
    native_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE weather_experiment.jobs (
    job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    state weather_experiment.job_state NOT NULL DEFAULT 'queued',
    requested_sources text[] NOT NULL DEFAULT '{}',
    detail text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (finished_at IS NULL OR started_at IS NOT NULL),
    CHECK (started_at IS NULL OR started_at >= created_at),
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX jobs_recent_idx
    ON weather_experiment.jobs (created_at DESC);

CREATE TABLE weather_experiment.model_runs (
    run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id text NOT NULL REFERENCES weather_experiment.sources(source_id),
    provider_run_id text NOT NULL,
    run_time timestamptz NOT NULL,
    retrieved_at timestamptz NOT NULL,
    complete boolean NOT NULL DEFAULT false,
    qc_passed boolean NOT NULL DEFAULT false,
    coverage geometry(MultiPolygon, 4326),
    native_crs text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source_id, provider_run_id)
);

CREATE TABLE weather_experiment.artifact_revisions (
    revision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES weather_experiment.model_runs(run_id),
    logical_name text NOT NULL,
    object_key text NOT NULL UNIQUE,
    media_type text NOT NULL,
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    state weather_experiment.revision_state NOT NULL DEFAULT 'staged',
    complete boolean NOT NULL DEFAULT false,
    qc_passed boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    superseded_at timestamptz,
    provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (state <> 'published' OR (complete AND qc_passed AND published_at IS NOT NULL)),
    CHECK (state <> 'superseded' OR superseded_at IS NOT NULL)
);

CREATE INDEX artifact_revisions_run_idx
    ON weather_experiment.artifact_revisions (run_id, logical_name, created_at DESC);

CREATE UNIQUE INDEX artifact_one_published_idx
    ON weather_experiment.artifact_revisions (run_id, logical_name)
    WHERE state = 'published';

CREATE TABLE weather_experiment.current_artifacts (
    source_id text NOT NULL REFERENCES weather_experiment.sources(source_id),
    logical_name text NOT NULL,
    revision_id uuid NOT NULL UNIQUE REFERENCES weather_experiment.artifact_revisions(revision_id),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, logical_name)
);

CREATE OR REPLACE FUNCTION weather_experiment.publish_revision(candidate uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    candidate_source text;
    candidate_name text;
    previous_revision uuid;
BEGIN
    SELECT r.source_id, a.logical_name
      INTO candidate_source, candidate_name
      FROM weather_experiment.artifact_revisions a
      JOIN weather_experiment.model_runs r ON r.run_id = a.run_id
     WHERE a.revision_id = candidate
       AND a.state = 'staged'
       AND a.complete
       AND a.qc_passed
     FOR UPDATE OF a;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'revision must be staged, complete, and QC-passed';
    END IF;

    SELECT revision_id INTO previous_revision
      FROM weather_experiment.current_artifacts
     WHERE source_id = candidate_source AND logical_name = candidate_name
     FOR UPDATE;

    IF previous_revision IS NOT NULL THEN
        UPDATE weather_experiment.artifact_revisions
           SET state = 'superseded', superseded_at = now()
         WHERE revision_id = previous_revision;
    END IF;

    UPDATE weather_experiment.artifact_revisions
       SET state = 'published', published_at = now()
     WHERE revision_id = candidate;

    INSERT INTO weather_experiment.current_artifacts
        (source_id, logical_name, revision_id, updated_at)
    VALUES (candidate_source, candidate_name, candidate, now())
    ON CONFLICT (source_id, logical_name) DO UPDATE
        SET revision_id = EXCLUDED.revision_id, updated_at = EXCLUDED.updated_at;
END;
$$;

COMMENT ON FUNCTION weather_experiment.publish_revision(uuid) IS
    'Atomically changes visibility only after immutable object upload, completeness, and QC.';

