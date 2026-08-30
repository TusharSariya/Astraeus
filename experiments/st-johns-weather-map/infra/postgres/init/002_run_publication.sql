-- Run-level publication, metadata immutability and orphan detection.
--
-- 001_weather_metadata.sql publishes one revision at a time and gates on the
-- artifact row's own copied complete/qc_passed flags. Two problems follow.
-- First, the parent weather_experiment.model_runs row is never consulted, so a
-- run marked incomplete could still publish artifacts whose copied flags said
-- otherwise. Second, ingest.store called publish_revision once per revision in
-- separate transactions, so a crash halfway through a run left some logical
-- streams pointing at the new run and the rest at the old one - a run that is
-- half visible, which is exactly the partial publication this experiment
-- forbids.
--
-- This file is additive. publish_revision keeps working for single-artifact
-- callers; publish_run is the path a worker cycle takes.

-- ---------------------------------------------------------------------------
-- Immutable revision metadata.
--
-- object_key, sha256, byte_size and created_at describe an object that was
-- already uploaded. Changing any of them after the fact would silently point a
-- published pointer at different bytes, or make the recorded digest a lie. Only
-- the state machine columns may move.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION weather_experiment.reject_revision_metadata_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.object_key IS DISTINCT FROM OLD.object_key
       OR NEW.sha256 IS DISTINCT FROM OLD.sha256
       OR NEW.byte_size IS DISTINCT FROM OLD.byte_size
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION
            'artifact revision % has immutable metadata: object_key, sha256, byte_size and created_at cannot change',
            OLD.revision_id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS artifact_revisions_immutable_metadata
    ON weather_experiment.artifact_revisions;

CREATE TRIGGER artifact_revisions_immutable_metadata
    BEFORE UPDATE ON weather_experiment.artifact_revisions
    FOR EACH ROW
    EXECUTE FUNCTION weather_experiment.reject_revision_metadata_change();

-- ---------------------------------------------------------------------------
-- Publish a whole run, or nothing.
--
-- The gate is the parent model_runs row: the manifest validator in
-- ingest.manifest writes its verdict there, and it is that verdict, not a
-- per-artifact copy of it, that decides visibility.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION weather_experiment.publish_run(candidate_run uuid)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    run_source text;
    run_complete boolean;
    run_qc boolean;
    staged record;
    previous_revision uuid;
    published_count integer := 0;
BEGIN
    SELECT source_id, complete, qc_passed
      INTO run_source, run_complete, run_qc
      FROM weather_experiment.model_runs
     WHERE run_id = candidate_run
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'run % does not exist', candidate_run;
    END IF;

    IF NOT (run_complete AND run_qc) THEN
        RAISE EXCEPTION
            'run % is not publishable: complete=%, qc_passed=%',
            candidate_run, run_complete, run_qc
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;

    -- Ordered by logical_name so concurrent runs of different sources always
    -- take the current_artifacts rows in the same order and cannot deadlock.
    FOR staged IN
        SELECT revision_id, logical_name
          FROM weather_experiment.artifact_revisions
         WHERE run_id = candidate_run
           AND state = 'staged'
         ORDER BY logical_name
         FOR UPDATE
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM weather_experiment.artifact_revisions
             WHERE revision_id = staged.revision_id AND complete AND qc_passed
        ) THEN
            RAISE EXCEPTION
                'revision % contradicts its run: the run is complete and QC-passed but the revision is not',
                staged.revision_id
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;

        -- SELECT INTO leaves the previous iteration's value when it matches no
        -- row, which would supersede an unrelated revision.
        previous_revision := NULL;
        SELECT revision_id INTO previous_revision
          FROM weather_experiment.current_artifacts
         WHERE source_id = run_source AND logical_name = staged.logical_name
         FOR UPDATE;

        IF previous_revision IS NOT NULL AND previous_revision <> staged.revision_id THEN
            UPDATE weather_experiment.artifact_revisions
               SET state = 'superseded', superseded_at = now()
             WHERE revision_id = previous_revision;
        END IF;

        UPDATE weather_experiment.artifact_revisions
           SET state = 'published', published_at = now()
         WHERE revision_id = staged.revision_id;

        INSERT INTO weather_experiment.current_artifacts
            (source_id, logical_name, revision_id, updated_at)
        VALUES (run_source, staged.logical_name, staged.revision_id, now())
        ON CONFLICT (source_id, logical_name) DO UPDATE
            SET revision_id = EXCLUDED.revision_id, updated_at = EXCLUDED.updated_at;

        published_count := published_count + 1;
    END LOOP;

    IF published_count = 0 THEN
        RAISE EXCEPTION 'run % has no staged artifacts to publish', candidate_run;
    END IF;

    RETURN published_count;
END;
$$;

COMMENT ON FUNCTION weather_experiment.publish_run(uuid) IS
    'Publishes every staged artifact of one run in a single transaction, gated on the run row itself. Raises rather than publishing part of a run.';

-- ---------------------------------------------------------------------------
-- Orphan detection.
--
-- A staged revision older than the staging sweep window, or any rejected one,
-- names an object in MinIO that nothing will ever point at. The row is the
-- record of truth for the object's existence, so this view is what a sweep
-- reads to decide what to delete.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS artifact_revisions_unpublished_idx
    ON weather_experiment.artifact_revisions (state, created_at)
    WHERE state IN ('staged', 'rejected');

CREATE OR REPLACE VIEW weather_experiment.orphaned_objects AS
    SELECT a.revision_id,
           a.object_key,
           a.byte_size,
           a.state,
           a.created_at,
           r.source_id,
           r.provider_run_id,
           r.complete,
           r.qc_passed,
           now() - a.created_at AS age
      FROM weather_experiment.artifact_revisions a
      JOIN weather_experiment.model_runs r ON r.run_id = a.run_id
     WHERE a.state = 'rejected'
        OR (a.state = 'staged' AND a.created_at < now() - interval '1 hour');

COMMENT ON VIEW weather_experiment.orphaned_objects IS
    'Revisions whose MinIO objects are no longer reachable through any pointer: rejected, or staged and abandoned for over an hour.';
