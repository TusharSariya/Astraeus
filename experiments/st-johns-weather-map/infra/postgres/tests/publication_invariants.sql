-- Proves the storage-integrity invariants against a real PostgreSQL.
--
-- The mocked Python tests cannot reach these: they assert which statements were
-- sent, not what the database does with them. Everything below is a property the
-- experiment depends on for "a partial run can never become visible" to be true.
\set ON_ERROR_STOP on
SET client_min_messages TO NOTICE;

CREATE OR REPLACE FUNCTION pg_temp.expect_failure(statement text, label text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE statement;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'PASS  %  (rejected: %)', label, left(SQLERRM, 90);
        RETURN;
    END;
    RAISE EXCEPTION 'FAIL  %  - the statement was accepted and should not have been', label;
END;
$$;

CREATE OR REPLACE FUNCTION pg_temp.assert(condition boolean, label text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF condition THEN RAISE NOTICE 'PASS  %', label;
    ELSE RAISE EXCEPTION 'FAIL  %', label;
    END IF;
END;
$$;

INSERT INTO weather_experiment.sources (source_id, producer, product, registry_status, adapter_version)
VALUES ('eccc-hrdps', 'ECCC', 'HRDPS', 'implementing', 'test-v1');

-- ---------------------------------------------------------------------------
-- 1. A run whose parent row is not complete cannot publish, and leaves the
--    previous pointer untouched. This is the blocker: 001 gated on the
--    artifact's copied flags and never consulted the run.
-- ---------------------------------------------------------------------------
INSERT INTO weather_experiment.model_runs (run_id, source_id, provider_run_id, run_time, retrieved_at, complete, qc_passed)
VALUES ('11111111-1111-1111-1111-111111111111', 'eccc-hrdps', 'good-run', now(), now(), true, true);
INSERT INTO weather_experiment.artifact_revisions (revision_id, run_id, logical_name, object_key, media_type, byte_size, sha256, state, complete, qc_passed)
VALUES ('aaaaaaaa-1111-1111-1111-111111111111', '11111111-1111-1111-1111-111111111111', 'surface',
        'staging/eccc-hrdps/good-run/surface', 'application/zarr+zip', 1024, repeat('a', 64), 'staged', true, true);
SELECT pg_temp.assert(weather_experiment.publish_run('11111111-1111-1111-1111-111111111111') = 1,
                      'a complete, QC-passed run publishes its artifact');

-- The incomplete run: artifact rows deliberately claim complete/qc_passed, the
-- parent run does not. Under 001 this would have published.
INSERT INTO weather_experiment.model_runs (run_id, source_id, provider_run_id, run_time, retrieved_at, complete, qc_passed)
VALUES ('22222222-2222-2222-2222-222222222222', 'eccc-hrdps', 'partial-run', now(), now(), false, true);
INSERT INTO weather_experiment.artifact_revisions (revision_id, run_id, logical_name, object_key, media_type, byte_size, sha256, state, complete, qc_passed)
VALUES ('bbbbbbbb-2222-2222-2222-222222222222', '22222222-2222-2222-2222-222222222222', 'surface',
        'staging/eccc-hrdps/partial-run/surface', 'application/zarr+zip', 2048, repeat('b', 64), 'staged', true, true);

SELECT pg_temp.expect_failure(
    $$SELECT weather_experiment.publish_run('22222222-2222-2222-2222-222222222222')$$,
    'an incomplete parent run cannot publish even when its artifact rows claim otherwise');

SELECT pg_temp.assert(
    (SELECT revision_id FROM weather_experiment.current_artifacts
      WHERE source_id = 'eccc-hrdps' AND logical_name = 'surface') = 'aaaaaaaa-1111-1111-1111-111111111111',
    'the failed publish left the previous pointer byte-for-byte unchanged');

-- ---------------------------------------------------------------------------
-- 2. Immutable metadata. A published pointer must never come to mean different
--    bytes, and a recorded digest must never become a lie.
-- ---------------------------------------------------------------------------
SELECT pg_temp.expect_failure(
    $$UPDATE weather_experiment.artifact_revisions SET sha256 = repeat('c', 64)
       WHERE revision_id = 'aaaaaaaa-1111-1111-1111-111111111111'$$,
    'sha256 cannot be rewritten');
SELECT pg_temp.expect_failure(
    $$UPDATE weather_experiment.artifact_revisions SET object_key = 'artifacts/elsewhere'
       WHERE revision_id = 'aaaaaaaa-1111-1111-1111-111111111111'$$,
    'object_key cannot be repointed');
SELECT pg_temp.expect_failure(
    $$UPDATE weather_experiment.artifact_revisions SET byte_size = 9999
       WHERE revision_id = 'aaaaaaaa-1111-1111-1111-111111111111'$$,
    'byte_size cannot be rewritten');
SELECT pg_temp.expect_failure(
    $$UPDATE weather_experiment.artifact_revisions SET created_at = now()
       WHERE revision_id = 'aaaaaaaa-1111-1111-1111-111111111111'$$,
    'created_at cannot be rewritten');

-- The state machine must still be able to move, or nothing could ever publish.
UPDATE weather_experiment.artifact_revisions SET state = 'superseded', superseded_at = now()
 WHERE revision_id = 'aaaaaaaa-1111-1111-1111-111111111111';
SELECT pg_temp.assert(true, 'state and superseded_at remain mutable');
UPDATE weather_experiment.artifact_revisions SET state = 'published', superseded_at = NULL
 WHERE revision_id = 'aaaaaaaa-1111-1111-1111-111111111111';

-- ---------------------------------------------------------------------------
-- 3. Atomicity across a multi-artifact run: all pointers move, or none do.
-- ---------------------------------------------------------------------------
INSERT INTO weather_experiment.model_runs (run_id, source_id, provider_run_id, run_time, retrieved_at, complete, qc_passed)
VALUES ('33333333-3333-3333-3333-333333333333', 'eccc-hrdps', 'multi-run', now(), now(), true, true);
INSERT INTO weather_experiment.artifact_revisions (revision_id, run_id, logical_name, object_key, media_type, byte_size, sha256, state, complete, qc_passed)
VALUES ('cccccccc-3333-3333-3333-333333333333', '33333333-3333-3333-3333-333333333333', 'surface',
        'staging/eccc-hrdps/multi-run/surface', 'application/zarr+zip', 4096, repeat('d', 64), 'staged', true, true),
       ('dddddddd-3333-3333-3333-333333333333', '33333333-3333-3333-3333-333333333333', 'profile',
        'staging/eccc-hrdps/multi-run/profile', 'application/zarr+zip', 8192, repeat('e', 64), 'staged', true, true);

SELECT pg_temp.assert(weather_experiment.publish_run('33333333-3333-3333-3333-333333333333') = 2,
                      'a two-artifact run publishes both in one call');
SELECT pg_temp.assert(
    (SELECT count(*) FROM weather_experiment.current_artifacts WHERE source_id = 'eccc-hrdps') = 2,
    'both logical streams now have current pointers');
SELECT pg_temp.assert(
    (SELECT state FROM weather_experiment.artifact_revisions
      WHERE revision_id = 'aaaaaaaa-1111-1111-1111-111111111111') = 'superseded',
    'the prior surface revision was superseded, not deleted');

-- A run with a contradicting artifact must abort the WHOLE run, not publish the
-- artifacts it already reached.
INSERT INTO weather_experiment.model_runs (run_id, source_id, provider_run_id, run_time, retrieved_at, complete, qc_passed)
VALUES ('44444444-4444-4444-4444-444444444444', 'eccc-hrdps', 'contradicting-run', now(), now(), true, true);
INSERT INTO weather_experiment.artifact_revisions (revision_id, run_id, logical_name, object_key, media_type, byte_size, sha256, state, complete, qc_passed)
VALUES ('eeeeeeee-4444-4444-4444-444444444444', '44444444-4444-4444-4444-444444444444', 'aaa-first',
        'staging/eccc-hrdps/contradicting/a', 'application/zarr+zip', 16, repeat('f', 64), 'staged', true, true),
       ('ffffffff-4444-4444-4444-444444444444', '44444444-4444-4444-4444-444444444444', 'zzz-last',
        'staging/eccc-hrdps/contradicting/z', 'application/zarr+zip', 16, repeat('0', 64), 'staged', false, false);

SELECT pg_temp.expect_failure(
    $$SELECT weather_experiment.publish_run('44444444-4444-4444-4444-444444444444')$$,
    'a run containing one bad artifact publishes none of them');
SELECT pg_temp.assert(
    (SELECT count(*) FROM weather_experiment.artifact_revisions
      WHERE run_id = '44444444-4444-4444-4444-444444444444' AND state = 'published') = 0,
    'the artifact processed before the bad one was rolled back, not left visible');

-- A run with nothing staged must not report success.
INSERT INTO weather_experiment.model_runs (run_id, source_id, provider_run_id, run_time, retrieved_at, complete, qc_passed)
VALUES ('55555555-5555-5555-5555-555555555555', 'eccc-hrdps', 'empty-run', now(), now(), true, true);
SELECT pg_temp.expect_failure(
    $$SELECT weather_experiment.publish_run('55555555-5555-5555-5555-555555555555')$$,
    'a run with no staged artifacts is an error, not a silent success');
SELECT pg_temp.expect_failure(
    $$SELECT weather_experiment.publish_run('99999999-9999-9999-9999-999999999999')$$,
    'publishing a nonexistent run is an error');

-- ---------------------------------------------------------------------------
-- 4. Orphan detection: rows naming MinIO objects nothing will ever point at.
-- ---------------------------------------------------------------------------
INSERT INTO weather_experiment.artifact_revisions (revision_id, run_id, logical_name, object_key, media_type, byte_size, sha256, state, complete, qc_passed, created_at)
VALUES ('99999999-8888-8888-8888-888888888888', '11111111-1111-1111-1111-111111111111', 'abandoned',
        'staging/eccc-hrdps/abandoned/surface', 'application/zarr+zip', 64, repeat('9', 64), 'staged', true, true,
        now() - interval '3 hours');

SELECT pg_temp.assert(
    EXISTS (SELECT 1 FROM weather_experiment.orphaned_objects
             WHERE object_key = 'staging/eccc-hrdps/abandoned/surface'),
    'an abandoned staged revision is listed as an orphan');
SELECT pg_temp.assert(
    NOT EXISTS (SELECT 1 FROM weather_experiment.orphaned_objects
                 WHERE revision_id = 'cccccccc-3333-3333-3333-333333333333'),
    'a freshly published revision is not an orphan');

SELECT 'ALL PUBLICATION INVARIANTS HOLD' AS result;
