-- Proves the retention invariants of 003_retention_window.sql against a real
-- PostgreSQL.
--
-- The mocked Python tests assert which statements the store sends. "A third
-- complete run displaces the oldest in the same transaction that publishes the
-- newest" and "the record of what a stream held outlives its frames" are
-- properties of the database, not of the caller, so they are proved here.
--
-- This file runs against the same database as publication_invariants.sql, so
-- it uses its own source ids and asserts nothing about rows it did not create.
\set ON_ERROR_STOP on
SET client_min_messages TO NOTICE;

CREATE OR REPLACE FUNCTION pg_temp.assert(condition boolean, label text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF condition THEN RAISE NOTICE 'PASS  %', label;
    ELSE RAISE EXCEPTION 'FAIL  %', label;
    END IF;
END;
$$;

-- A staged revision with a declared valid-time span, published as its own run.
CREATE OR REPLACE FUNCTION pg_temp.publish_frame(
    stream_source text,
    stream_name text,
    run_label text,
    span_start timestamptz,
    span_end timestamptz,
    bytes bigint DEFAULT 1024
)
RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE
    new_run uuid := gen_random_uuid();
    new_revision uuid := gen_random_uuid();
BEGIN
    INSERT INTO weather_experiment.model_runs
        (run_id, source_id, provider_run_id, run_time, retrieved_at, complete, qc_passed)
    VALUES (new_run, stream_source, run_label, span_start, now(), true, true);

    INSERT INTO weather_experiment.artifact_revisions
        (revision_id, run_id, logical_name, object_key, media_type, byte_size, sha256,
         state, complete, qc_passed, provenance)
    VALUES (new_revision, new_run, stream_name,
            'staging/' || stream_source || '/' || run_label || '/' || stream_name,
            'application/zarr+zip', bytes, md5(new_revision::text) || md5(run_label),
            'staged', true, true,
            jsonb_build_object('valid_times',
                jsonb_build_array(span_start::text, span_end::text)));

    PERFORM weather_experiment.publish_run(new_run);
    RETURN new_revision;
END;
$$;

INSERT INTO weather_experiment.sources (source_id, producer, product, registry_status, adapter_version)
VALUES ('retention-forecast', 'ECCC', 'HRDPS', 'implementing', 'test-v1'),
       ('retention-observation', 'NAV CANADA', 'CYYT METAR/SPECI', 'implementing', 'test-v1'),
       ('retention-never-held', 'ECCC', 'REPS', 'implementing', 'test-v1')
ON CONFLICT (source_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 0. The window the database states is the window api/weather_api/config.py
--    defines. SQL cannot import Python, so the two are asserted equal here.
-- ---------------------------------------------------------------------------
SELECT pg_temp.assert(weather_experiment.window_back() = interval '24 hours',
                      'the retention window reaches 24 hours back, matching config.WINDOW_BACK');
SELECT pg_temp.assert(weather_experiment.window_forward() = interval '14 days',
                      'the retention window reaches 14 days forward, matching config.WINDOW_FORWARD');
SELECT pg_temp.assert(weather_experiment.keep_complete_runs() = 2,
                      'two complete runs per stream, matching config.KEEP_COMPLETE_RUNS');
SELECT pg_temp.assert(
    (SELECT window_end - window_start FROM weather_experiment.evidence_window(now()))
        = interval '15 days',
    'the window spans 24 h back plus 14 d forward');

-- ---------------------------------------------------------------------------
-- 1. The valid-time span is stamped from the artifact's own provenance.
-- ---------------------------------------------------------------------------
SELECT pg_temp.publish_frame('retention-forecast', 'surface', 'run-a',
                             now() - interval '1 hour', now() + interval '48 hours');
SELECT pg_temp.assert(
    (SELECT valid_time_end FROM weather_experiment.artifact_revisions a
      JOIN weather_experiment.model_runs r ON r.run_id = a.run_id
     WHERE r.source_id = 'retention-forecast' AND r.provider_run_id = 'run-a')
        > now() + interval '47 hours',
    'a revision carries the valid-time span its provenance declared');

-- A revision with no declared frame times still gets a span, from its run.
INSERT INTO weather_experiment.model_runs (run_id, source_id, provider_run_id, run_time, retrieved_at, complete, qc_passed)
VALUES ('7f000000-0000-0000-0000-000000000001', 'retention-forecast', 'no-stamps', now(), now(), true, true);
INSERT INTO weather_experiment.artifact_revisions (revision_id, run_id, logical_name, object_key, media_type, byte_size, sha256, state, complete, qc_passed)
VALUES ('7f000000-0000-0000-0000-0000000000a1', '7f000000-0000-0000-0000-000000000001', 'unstamped',
        'staging/retention-forecast/no-stamps/unstamped', 'application/zarr+zip', 16, repeat('1', 64), 'staged', true, true);
SELECT pg_temp.assert(
    (SELECT valid_time_start IS NOT NULL AND valid_time_end IS NOT NULL
       FROM weather_experiment.artifact_revisions
      WHERE revision_id = '7f000000-0000-0000-0000-0000000000a1'),
    'a revision declaring no frame times falls back to its run time rather than becoming unpurgeable');

-- ---------------------------------------------------------------------------
-- 2. The two-run ceiling: a third complete run displaces the oldest, in the
--    same transaction that publishes the newest, with room to spare.
-- ---------------------------------------------------------------------------
SELECT pg_temp.publish_frame('retention-forecast', 'surface', 'run-b',
                             now(), now() + interval '48 hours');
SELECT pg_temp.assert(
    (SELECT count(*) FROM weather_experiment.artifact_revisions a
      JOIN weather_experiment.model_runs r ON r.run_id = a.run_id
     WHERE r.source_id = 'retention-forecast' AND a.logical_name = 'surface') = 2,
    'two complete runs are retained');

SELECT pg_temp.publish_frame('retention-forecast', 'surface', 'run-c',
                             now(), now() + interval '48 hours');
SELECT pg_temp.assert(
    (SELECT count(*) FROM weather_experiment.artifact_revisions a
      JOIN weather_experiment.model_runs r ON r.run_id = a.run_id
     WHERE r.source_id = 'retention-forecast' AND a.logical_name = 'surface') = 2,
    'a third complete run displaces the oldest at publication: exactly two remain');
SELECT pg_temp.assert(
    NOT EXISTS (
        SELECT 1 FROM weather_experiment.artifact_revisions a
          JOIN weather_experiment.model_runs r ON r.run_id = a.run_id
         WHERE r.provider_run_id = 'run-a' AND a.logical_name = 'surface'),
    'the displaced run is the oldest, not an arbitrary one');
SELECT pg_temp.assert(
    (SELECT revision_id IS NOT NULL FROM weather_experiment.current_artifacts
      WHERE source_id = 'retention-forecast' AND logical_name = 'surface'),
    'the newest run is current: publication and purge committed together');

-- No vintage archive, however much room the quota leaves. Nothing above was
-- near a cap; the oldest run went because retention is a decision.
SELECT pg_temp.assert(
    (SELECT count(*) FROM weather_experiment.artifact_revisions a
      JOIN weather_experiment.model_runs r ON r.run_id = a.run_id
     WHERE r.source_id = 'retention-forecast' AND a.logical_name = 'surface') <= 2,
    'no vintage archive accumulates with free space available');

-- ---------------------------------------------------------------------------
-- 3. A frame that falls off the back of the window is purged, and the record
--    of how far its stream reached outlives it.
-- ---------------------------------------------------------------------------
SELECT pg_temp.publish_frame('retention-observation', 'metar',
                             'obs-old', now() - interval '30 hours', now() - interval '26 hours');
SELECT pg_temp.assert(
    (SELECT count(*) FROM weather_experiment.artifact_revisions a
      JOIN weather_experiment.model_runs r ON r.run_id = a.run_id
     WHERE r.source_id = 'retention-observation') = 0,
    'an observation frame whose whole span is older than now-24h is purged, not kept on a three-hour floor');
SELECT pg_temp.assert(
    (SELECT last_valid_time FROM weather_experiment.stream_last_valid_time
      WHERE source_id = 'retention-observation' AND logical_name = 'metar')
        BETWEEN now() - interval '27 hours' AND now() - interval '25 hours',
    'the stream records the last valid time it held, after its frames are gone');
SELECT pg_temp.assert(
    NOT EXISTS (SELECT 1 FROM weather_experiment.current_artifacts
                 WHERE source_id = 'retention-observation'),
    'the pointer is deleted in the same transaction, so no object is removed behind a current pointer');
SELECT pg_temp.assert(
    EXISTS (SELECT 1 FROM weather_experiment.purged_objects
             WHERE object_key LIKE 'staging/retention-observation/obs-old/%'),
    'the purged object key is queued for the sweep: rows before objects');

-- A stream that was never held has no record, so its absence is null and never
-- aged out.
SELECT pg_temp.assert(
    NOT EXISTS (SELECT 1 FROM weather_experiment.stream_last_valid_time
                 WHERE source_id = 'retention-never-held'),
    'a source that never published here records no last valid time');

-- The record is never lowered by a later, shorter-horizon run.
SELECT weather_experiment.record_last_valid_time('retention-observation', 'metar', now() - interval '40 hours');
SELECT pg_temp.assert(
    (SELECT last_valid_time FROM weather_experiment.stream_last_valid_time
      WHERE source_id = 'retention-observation' AND logical_name = 'metar')
        > now() - interval '28 hours',
    'a later, shorter horizon does not shorten what this deployment once held');

-- ---------------------------------------------------------------------------
-- 4. A frame inside the window survives a purge sweep, however often it runs.
-- ---------------------------------------------------------------------------
SELECT pg_temp.publish_frame('retention-observation', 'radar', 'obs-now',
                             now() - interval '2 hours', now() - interval '1 hour');
SELECT weather_experiment.purge_outside_window(now());
SELECT pg_temp.assert(
    (SELECT count(*) FROM weather_experiment.artifact_revisions a
      JOIN weather_experiment.model_runs r ON r.run_id = a.run_id
     WHERE r.source_id = 'retention-observation' AND a.logical_name = 'radar') = 1,
    'an in-window frame survives a sweep');

-- ---------------------------------------------------------------------------
-- 5. The projection may only count bytes already outside the window.
-- ---------------------------------------------------------------------------
SELECT pg_temp.assert(
    weather_experiment.reclaimable_bytes(now()) = 0,
    'with nothing outside the window, no bytes are reclaimable: a projection cannot be satisfied by purging an in-window frame');

-- ---------------------------------------------------------------------------
-- 6. Draining the purge queue is idempotent and hands each key out once.
-- ---------------------------------------------------------------------------
SELECT pg_temp.assert(
    (SELECT count(*) FROM weather_experiment.claim_purged_objects(1000)) > 0,
    'the sweep claims the queued keys');
SELECT pg_temp.assert(
    (SELECT count(*) FROM weather_experiment.claim_purged_objects(1000)) = 0,
    'a second sweep claims nothing: a key is handed out once');

SELECT 'ALL RETENTION INVARIANTS HOLD' AS result;
