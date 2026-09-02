-- Retention as the sliding valid-time window, used as a restart cache.
--
-- 001 and 002 gave the store atomic publication but no retention policy the
-- database itself could state. What retention there was lived in Python
-- (ingest.store.prune) and was expressed in run age: "keep the latest and
-- previous complete run, plus three hours of observations". Run age says a
-- different amount of history per source and nothing at all about what a
-- reader can be shown, and it had already drifted apart from the API's own
-- 3 h/24 h window and from the 14-day planning tier.
--
-- This file makes the window the retention rule, in the units a reader asks
-- in: a frame is retained if and only if a request could name its instant.
-- Owner decision of record: wayfinder ticket 20,
-- https://github.com/TusharSariya/Astraeus/issues/20. Sizing evidence:
-- docs/research/wayfinder/size-probe-full-fields.md (non-normative).
--
-- The numbers here are the same numbers as api/weather_api/config.py
-- (WINDOW_BACK, WINDOW_FORWARD, KEEP_COMPLETE_RUNS). They are stated twice
-- because SQL cannot import Python; infra/postgres/tests/retention_invariants.sql
-- and api/tests/test_retention.py both assert the two agree, so a change to
-- one that is not made to the other fails a gate rather than drifting.

-- ---------------------------------------------------------------------------
-- The window, as the database states it.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION weather_experiment.window_back()
RETURNS interval LANGUAGE sql IMMUTABLE AS $$ SELECT interval '24 hours' $$;

CREATE OR REPLACE FUNCTION weather_experiment.window_forward()
RETURNS interval LANGUAGE sql IMMUTABLE AS $$ SELECT interval '14 days' $$;

CREATE OR REPLACE FUNCTION weather_experiment.keep_complete_runs()
RETURNS integer LANGUAGE sql IMMUTABLE AS $$ SELECT 2 $$;

COMMENT ON FUNCTION weather_experiment.keep_complete_runs() IS
    'The latest and the previous complete run per forecast stream, and no more. A ceiling by decision, not a consequence of free space: retaining every run whose valid times still fall inside a 14-day window would make this store a vintage archive by accident.';

CREATE OR REPLACE FUNCTION weather_experiment.evidence_window(
    at_moment timestamptz DEFAULT now(),
    OUT window_start timestamptz,
    OUT window_end timestamptz
)
LANGUAGE sql STABLE AS $$
    SELECT at_moment - weather_experiment.window_back(),
           at_moment + weather_experiment.window_forward()
$$;

COMMENT ON FUNCTION weather_experiment.evidence_window(timestamptz) IS
    'The sliding evidence window, now-24h through now+14d, both boundaries inclusive. It bounds what the store retains exactly as it bounds what the API accepts.';

-- ---------------------------------------------------------------------------
-- What span of valid time a revision covers.
--
-- Stamped by a trigger rather than by the caller: every adapter already writes
-- its own provenance and none of them agree on shape, so reading the span out
-- of the provenance at insert time is the one place that can be made to hold
-- for all of them. It also means retention does not wait on a Python change in
-- the ingest package to start being true.
-- ---------------------------------------------------------------------------
ALTER TABLE weather_experiment.artifact_revisions
    ADD COLUMN IF NOT EXISTS valid_time_start timestamptz,
    ADD COLUMN IF NOT EXISTS valid_time_end timestamptz;

CREATE INDEX IF NOT EXISTS artifact_revisions_valid_time_idx
    ON weather_experiment.artifact_revisions (valid_time_end, valid_time_start);

CREATE OR REPLACE FUNCTION weather_experiment.provenance_valid_times(document jsonb)
RETURNS timestamptz[]
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    collected timestamptz[] := '{}';
    raw text;
BEGIN
    IF document IS NULL THEN
        RETURN collected;
    END IF;

    IF jsonb_typeof(document -> 'valid_times') = 'array' THEN
        FOR raw IN SELECT jsonb_array_elements_text(document -> 'valid_times') LOOP
            BEGIN
                collected := collected || raw::timestamptz;
            EXCEPTION WHEN OTHERS THEN
                -- An unparseable stamp is not a frame time. Skipping it leaves
                -- the span narrower, which retains more, never less: guessing
                -- wide is how a frame gets purged that a request could name.
                CONTINUE;
            END;
        END LOOP;
    END IF;

    IF array_length(collected, 1) IS NULL AND jsonb_typeof(document -> 'valid_time') = 'string' THEN
        BEGIN
            collected := collected || (document ->> 'valid_time')::timestamptz;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END;
    END IF;

    RETURN collected;
END;
$$;

CREATE OR REPLACE FUNCTION weather_experiment.stamp_revision_valid_times()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    stamps timestamptz[];
    fallback timestamptz;
BEGIN
    IF NEW.valid_time_start IS NOT NULL AND NEW.valid_time_end IS NOT NULL THEN
        RETURN NEW;
    END IF;

    stamps := weather_experiment.provenance_valid_times(NEW.provenance);

    IF array_length(stamps, 1) IS NOT NULL THEN
        NEW.valid_time_start := coalesce(NEW.valid_time_start, (SELECT min(t) FROM unnest(stamps) AS t));
        NEW.valid_time_end := coalesce(NEW.valid_time_end, (SELECT max(t) FROM unnest(stamps) AS t));
        RETURN NEW;
    END IF;

    -- No frame times declared. The run's own time is the only instant this
    -- artifact can be placed at; a NULL span would make the revision
    -- unpurgeable, which is the safe direction but leaks storage forever.
    SELECT run_time INTO fallback
      FROM weather_experiment.model_runs
     WHERE run_id = NEW.run_id;

    NEW.valid_time_start := coalesce(NEW.valid_time_start, fallback);
    NEW.valid_time_end := coalesce(NEW.valid_time_end, fallback);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS artifact_revisions_stamp_valid_times
    ON weather_experiment.artifact_revisions;

CREATE TRIGGER artifact_revisions_stamp_valid_times
    BEFORE INSERT ON weather_experiment.artifact_revisions
    FOR EACH ROW
    EXECUTE FUNCTION weather_experiment.stamp_revision_valid_times();

-- ---------------------------------------------------------------------------
-- The last valid time held per logical stream.
--
-- Kept after the frames are purged, and never lowered. It is the whole
-- difference between "we held this out to here and it aged out" and "we never
-- held it": a deployment with no row here reports null, and must not claim it
-- once had evidence.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS weather_experiment.stream_last_valid_time (
    source_id text NOT NULL REFERENCES weather_experiment.sources(source_id),
    logical_name text NOT NULL,
    last_valid_time timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, logical_name)
);

COMMENT ON TABLE weather_experiment.stream_last_valid_time IS
    'The latest valid time this deployment ever held for each logical stream, kept after its frames are purged. Absent means never held: the response is then null, never aged out.';

CREATE OR REPLACE FUNCTION weather_experiment.record_last_valid_time(
    stream_source text,
    stream_name text,
    held_until timestamptz
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    IF held_until IS NULL THEN
        RETURN;
    END IF;

    INSERT INTO weather_experiment.stream_last_valid_time
        (source_id, logical_name, last_valid_time, recorded_at)
    VALUES (stream_source, stream_name, held_until, now())
    ON CONFLICT (source_id, logical_name) DO UPDATE
        -- Never lowered. A later run whose horizon is shorter than an earlier
        -- one's does not shorten what this deployment once held.
        SET last_valid_time = greatest(
                weather_experiment.stream_last_valid_time.last_valid_time,
                EXCLUDED.last_valid_time),
            recorded_at = now();
END;
$$;

-- ---------------------------------------------------------------------------
-- Objects whose rows are gone.
--
-- The purge deletes metadata rows and queues their object keys here; a sweep
-- drains the queue against MinIO. Rows before objects, as the storage-integrity
-- requirement says, and a delete that never runs leaks bytes rather than
-- leaving a pointer at nothing. An object already gone does not abort a sweep,
-- so draining is idempotent.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS weather_experiment.purged_objects (
    object_key text PRIMARY KEY,
    purged_at timestamptz NOT NULL DEFAULT now(),
    reason text NOT NULL
);

COMMENT ON TABLE weather_experiment.purged_objects IS
    'Object keys whose metadata rows have been deleted and whose bytes are still in the object store. The metadata row is the record of truth, so this queue is drained after the row is already gone.';

CREATE OR REPLACE FUNCTION weather_experiment.claim_purged_objects(batch integer DEFAULT 1000)
RETURNS SETOF text
LANGUAGE sql
AS $$
    DELETE FROM weather_experiment.purged_objects
     WHERE object_key IN (
         SELECT object_key FROM weather_experiment.purged_objects
          ORDER BY purged_at
          LIMIT batch
          FOR UPDATE SKIP LOCKED
     )
    RETURNING object_key;
$$;

-- ---------------------------------------------------------------------------
-- The purge.
--
-- Two rules, both ceilings rather than consequences of free space:
--   1. A revision whose whole valid-time span lies outside the window goes.
--   2. Per logical stream, the latest complete run and the previous one stay;
--      a third displaces the oldest.
--
-- A revision a current pointer references is not simply unlinked and left
-- behind: the pointer row is deleted in the same transaction, so the object is
-- never removed while something still points at it, and a read already in
-- flight fails closed rather than being served truncated bytes.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION weather_experiment.purge_outside_window(
    at_moment timestamptz DEFAULT now()
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    bounds record;
    purged integer := 0;
BEGIN
    SELECT * INTO bounds FROM weather_experiment.evidence_window(at_moment);

    -- Record what each stream held before anything is removed. After this the
    -- frames may go; the record of how far they reached may not.
    INSERT INTO weather_experiment.stream_last_valid_time
        (source_id, logical_name, last_valid_time, recorded_at)
    SELECT r.source_id, a.logical_name, max(a.valid_time_end), now()
      FROM weather_experiment.artifact_revisions a
      JOIN weather_experiment.model_runs r ON r.run_id = a.run_id
     WHERE a.valid_time_end IS NOT NULL
     GROUP BY r.source_id, a.logical_name
    ON CONFLICT (source_id, logical_name) DO UPDATE
        SET last_valid_time = greatest(
                weather_experiment.stream_last_valid_time.last_valid_time,
                EXCLUDED.last_valid_time),
            recorded_at = now();

    WITH doomed AS (
        SELECT a.revision_id, a.object_key, r.source_id, a.logical_name,
               CASE
                   WHEN a.valid_time_end < bounds.window_start THEN 'aged_out'
                   WHEN a.valid_time_start > bounds.window_end THEN 'beyond_window'
                   ELSE 'run_ceiling'
               END AS reason
          FROM weather_experiment.artifact_revisions a
          JOIN weather_experiment.model_runs r ON r.run_id = a.run_id
         WHERE a.state IN ('published', 'superseded')
           AND (
                (a.valid_time_end IS NOT NULL AND a.valid_time_end < bounds.window_start)
             OR (a.valid_time_start IS NOT NULL AND a.valid_time_start > bounds.window_end)
             OR a.revision_id IN (
                    SELECT revision_id FROM (
                        SELECT b.revision_id,
                               row_number() OVER (
                                   PARTITION BY runs.source_id, b.logical_name
                                   ORDER BY b.created_at DESC
                               ) AS position
                          FROM weather_experiment.artifact_revisions b
                          JOIN weather_experiment.model_runs runs ON runs.run_id = b.run_id
                         WHERE b.state IN ('published', 'superseded')
                    ) ranked
                     WHERE ranked.position > weather_experiment.keep_complete_runs()
                )
           )
    ),
    unlinked AS (
        -- The pointer goes first, in this same transaction. Unlinking is what
        -- makes removing the bytes safe; leaving the pointer and deleting the
        -- object is the one ordering that can serve a key with nothing behind it.
        DELETE FROM weather_experiment.current_artifacts c
         USING doomed
         WHERE c.revision_id = doomed.revision_id
        RETURNING c.revision_id
    ),
    removed AS (
        DELETE FROM weather_experiment.artifact_revisions a
         USING doomed
         WHERE a.revision_id = doomed.revision_id
        RETURNING a.object_key
    ),
    queued AS (
        INSERT INTO weather_experiment.purged_objects (object_key, purged_at, reason)
        SELECT doomed.object_key, now(), doomed.reason FROM doomed
        ON CONFLICT (object_key) DO NOTHING
        RETURNING object_key
    )
    SELECT count(*) INTO purged FROM removed;

    RETURN purged;
END;
$$;

COMMENT ON FUNCTION weather_experiment.purge_outside_window(timestamptz) IS
    'Purges every revision whose valid-time span has left the sliding window, and every run beyond the two-run ceiling, however much room the quota leaves. Records each stream last valid time first, so the absence it creates reports aged out rather than null.';

-- ---------------------------------------------------------------------------
-- What the projection may count on being freed.
--
-- A projection must never be satisfied by planning to purge a frame that is
-- still inside the window: that would trade evidence a request could name for
-- room to fetch more, which is an eviction of visible data by another name.
-- Only bytes this function reports are reclaimable.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION weather_experiment.reclaimable_bytes(
    at_moment timestamptz DEFAULT now()
)
RETURNS bigint
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    bounds record;
    total bigint;
BEGIN
    SELECT * INTO bounds FROM weather_experiment.evidence_window(at_moment);
    SELECT coalesce(sum(a.byte_size), 0) INTO total
      FROM weather_experiment.artifact_revisions a
     WHERE a.state <> 'rejected'
       AND (
            (a.valid_time_end IS NOT NULL AND a.valid_time_end < bounds.window_start)
         OR (a.valid_time_start IS NOT NULL AND a.valid_time_start > bounds.window_end)
       );
    RETURN total;
END;
$$;

COMMENT ON FUNCTION weather_experiment.reclaimable_bytes(timestamptz) IS
    'Bytes held by revisions already outside the evidence window. A staging projection may count these and nothing else: an in-window frame is never traded for room.';

-- ---------------------------------------------------------------------------
-- Publication and purge in one transaction.
--
-- publish_run is replaced rather than wrapped so a caller cannot publish
-- without purging. A third complete run therefore displaces the oldest in the
-- same operation that makes the newest visible, which is what stops the two-run
-- ceiling from depending on a separate sweep ever running.
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
        SELECT revision_id, logical_name, valid_time_end
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

        -- Recorded at publication, not only at purge: a stack that publishes
        -- once and is then down for a week must still be able to say how far
        -- its evidence reached.
        PERFORM weather_experiment.record_last_valid_time(
            run_source, staged.logical_name, staged.valid_time_end);

        published_count := published_count + 1;
    END LOOP;

    IF published_count = 0 THEN
        RAISE EXCEPTION 'run % has no staged artifacts to publish', candidate_run;
    END IF;

    -- One transaction with the publication above. A commit that made the
    -- newest run visible without displacing the oldest would leave the store a
    -- run over its ceiling for as long as no separate sweep ran, and "no
    -- vintage archive" would be a hope rather than an invariant.
    PERFORM weather_experiment.purge_outside_window(now());

    RETURN published_count;
END;
$$;

COMMENT ON FUNCTION weather_experiment.publish_run(uuid) IS
    'Publishes every staged artifact of one run and purges what has left the retention window, in a single transaction. Raises rather than publishing part of a run.';
