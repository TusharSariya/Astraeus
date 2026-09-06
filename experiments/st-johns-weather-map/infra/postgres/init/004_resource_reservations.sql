-- Durable, fenced capacity reservations for experimental ingestion.
DO $$ BEGIN
    CREATE TYPE weather_experiment.reservation_state AS ENUM ('active','revoking','releasable','released');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE SEQUENCE IF NOT EXISTS weather_experiment.resource_fencing_token_seq;

CREATE TABLE IF NOT EXISTS weather_experiment.resource_reservations (
    operation_id uuid PRIMARY KEY,
    fencing_token bigint NOT NULL UNIQUE DEFAULT nextval('weather_experiment.resource_fencing_token_seq'),
    owner_id text NOT NULL,
    host_id text NOT NULL,
    host_epoch uuid NOT NULL,
    device_id text NOT NULL,
    workspace_path text NOT NULL,
    workload_kind text NOT NULL CHECK (workload_kind IN ('task', 'ingestion', 'snapshot')),
    store_key text NOT NULL,
    store_bytes bigint NOT NULL CHECK (store_bytes >= 0),
    filesystem_bytes bigint NOT NULL CHECK (filesystem_bytes >= 0),
    margin_bytes bigint NOT NULL CHECK (margin_bytes >= 0),
    state weather_experiment.reservation_state NOT NULL DEFAULT 'active',
    admitted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    deadline_at timestamptz NOT NULL,
    revoking_at timestamptz,
    cleanup_started_at timestamptz,
    cleanup_verified_at timestamptz,
    released_at timestamptz,
    detail text,
    CHECK (deadline_at > admitted_at),
    CHECK (state <> 'released' OR (cleanup_verified_at IS NOT NULL AND released_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS resource_reservations_charged_store_idx
    ON weather_experiment.resource_reservations (store_key, state);
CREATE INDEX IF NOT EXISTS resource_reservations_charged_host_idx
    ON weather_experiment.resource_reservations (host_id, device_id, state);

ALTER TABLE weather_experiment.artifact_revisions
    ADD COLUMN IF NOT EXISTS reservation_operation_id uuid REFERENCES weather_experiment.resource_reservations(operation_id),
    ADD COLUMN IF NOT EXISTS reservation_fencing_token bigint;

CREATE OR REPLACE FUNCTION weather_experiment.acquire_resource_reservation(
    candidate uuid, owner text, stable_host text, epoch uuid, device text,
    workspace text, kind text, target_store text, wanted_store bigint,
    wanted_filesystem bigint, wanted_margin bigint, store_cap bigint,
    filesystem_free bigint
) RETURNS TABLE(fencing_token bigint, deadline_at timestamptz)
LANGUAGE plpgsql AS $$
DECLARE charged_store bigint; used_store bigint; charged_filesystem bigint; duration interval;
BEGIN
    IF kind NOT IN ('task','ingestion','snapshot') THEN RAISE EXCEPTION 'unknown workload kind'; END IF;
    IF wanted_store < 0 OR wanted_filesystem < 0 OR wanted_margin < 0 THEN RAISE EXCEPTION 'negative allocation'; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('store:'||target_store,0));
    PERFORM pg_advisory_xact_lock(hashtextextended('fs:'||stable_host||':'||device,0));
    PERFORM weather_experiment.revoke_expired_reservations();
    SELECT coalesce(sum(store_bytes),0) INTO charged_store FROM weather_experiment.resource_reservations
     WHERE store_key=target_store AND state <> 'released';
    SELECT coalesce(sum(byte_size),0) INTO used_store FROM weather_experiment.artifact_revisions WHERE state <> 'rejected';
    IF used_store+charged_store+wanted_store > store_cap THEN
        RAISE EXCEPTION 'hot storage quota exhausted: projected % against cap %',used_store+charged_store+wanted_store,store_cap
          USING ERRCODE='disk_full';
    END IF;
    SELECT coalesce(sum(filesystem_bytes+margin_bytes),0) INTO charged_filesystem
      FROM weather_experiment.resource_reservations
     WHERE host_id=stable_host AND device_id=device AND state <> 'released';
    IF charged_filesystem+wanted_filesystem+wanted_margin > filesystem_free THEN
        RAISE EXCEPTION 'local filesystem budget exhausted: required % against % free',
          charged_filesystem+wanted_filesystem+wanted_margin,filesystem_free USING ERRCODE='disk_full';
    END IF;
    duration := CASE WHEN kind IN ('task','snapshot') THEN interval '15 minutes' ELSE interval '2 hours' END;
    RETURN QUERY INSERT INTO weather_experiment.resource_reservations
      (operation_id,owner_id,host_id,host_epoch,device_id,workspace_path,workload_kind,
       store_key,store_bytes,filesystem_bytes,margin_bytes,deadline_at)
    VALUES(candidate,owner,stable_host,epoch,device,workspace,kind,target_store,wanted_store,
           wanted_filesystem,wanted_margin,clock_timestamp()+duration)
    RETURNING resource_reservations.fencing_token,resource_reservations.deadline_at;
END;
$$;

CREATE OR REPLACE FUNCTION weather_experiment.assert_active_reservation(candidate uuid, token bigint)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE lease weather_experiment.resource_reservations%ROWTYPE;
BEGIN
    SELECT * INTO lease FROM weather_experiment.resource_reservations
     WHERE operation_id = candidate FOR UPDATE;
    IF NOT FOUND OR lease.fencing_token <> token THEN
        RAISE EXCEPTION 'reservation fence mismatch' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF lease.state <> 'active' OR clock_timestamp() >= lease.deadline_at THEN
        RAISE EXCEPTION 'reservation is not active' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION weather_experiment.publish_run(candidate_run uuid, candidate_operation uuid, candidate_token bigint)
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE
    run_source text; run_complete boolean; run_qc boolean; staged record;
    previous_revision uuid; published_count integer := 0;
BEGIN
    PERFORM weather_experiment.assert_active_reservation(candidate_operation, candidate_token);
    SELECT source_id, complete, qc_passed INTO run_source, run_complete, run_qc
      FROM weather_experiment.model_runs WHERE run_id = candidate_run FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'run % does not exist', candidate_run; END IF;
    IF NOT (run_complete AND run_qc) THEN
        RAISE EXCEPTION 'run % is not publishable: complete=%, qc_passed=%', candidate_run, run_complete, run_qc
          USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF EXISTS (
        SELECT 1 FROM weather_experiment.artifact_revisions
         WHERE run_id=candidate_run AND state='staged'
           AND (reservation_operation_id IS DISTINCT FROM candidate_operation
                OR reservation_fencing_token IS DISTINCT FROM candidate_token)
    ) THEN
        RAISE EXCEPTION 'run % contains staged artifacts owned by another reservation', candidate_run
          USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    FOR staged IN
        SELECT revision_id, logical_name, valid_time_end FROM weather_experiment.artifact_revisions
         WHERE run_id = candidate_run AND state = 'staged'
           AND reservation_operation_id = candidate_operation
           AND reservation_fencing_token = candidate_token
         ORDER BY logical_name FOR UPDATE
    LOOP
        IF NOT EXISTS (SELECT 1 FROM weather_experiment.artifact_revisions
                        WHERE revision_id=staged.revision_id AND complete AND qc_passed) THEN
            RAISE EXCEPTION 'revision % contradicts its run', staged.revision_id
              USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        previous_revision := NULL;
        SELECT revision_id INTO previous_revision FROM weather_experiment.current_artifacts
         WHERE source_id=run_source AND logical_name=staged.logical_name FOR UPDATE;
        IF previous_revision IS NOT NULL AND previous_revision <> staged.revision_id THEN
            UPDATE weather_experiment.artifact_revisions SET state='superseded', superseded_at=now()
             WHERE revision_id=previous_revision;
        END IF;
        UPDATE weather_experiment.artifact_revisions SET state='published', published_at=now()
         WHERE revision_id=staged.revision_id;
        INSERT INTO weather_experiment.current_artifacts(source_id,logical_name,revision_id,updated_at)
        VALUES(run_source,staged.logical_name,staged.revision_id,now())
        ON CONFLICT(source_id,logical_name) DO UPDATE SET revision_id=EXCLUDED.revision_id,updated_at=EXCLUDED.updated_at;
        PERFORM weather_experiment.record_last_valid_time(run_source,staged.logical_name,staged.valid_time_end);
        published_count := published_count + 1;
    END LOOP;
    IF published_count=0 THEN RAISE EXCEPTION 'run % has no staged artifacts for reservation',candidate_run; END IF;
    -- Published objects are now counted by artifact_revisions. Keeping their
    -- complete-operation store reservation would count the same allocation
    -- twice until context cleanup.
    UPDATE weather_experiment.resource_reservations SET store_bytes=0
     WHERE operation_id=candidate_operation AND fencing_token=candidate_token AND state='active';
    PERFORM weather_experiment.purge_outside_window(now());
    RETURN published_count;
END;
$$;

-- Once the ledger exists there is no unfenced publication entry point.
CREATE OR REPLACE FUNCTION weather_experiment.publish_run(candidate_run uuid)
RETURNS integer LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'durable reservation identity is required for publication'
      USING ERRCODE = 'integrity_constraint_violation';
END;
$$;

CREATE OR REPLACE FUNCTION weather_experiment.publish_revision(candidate uuid)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'single-revision unfenced publication is disabled; publish the fenced run'
      USING ERRCODE = 'integrity_constraint_violation';
END;
$$;

CREATE OR REPLACE FUNCTION weather_experiment.revoke_expired_reservations()
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE changed integer;
BEGIN
    UPDATE weather_experiment.resource_reservations
       SET state='revoking', revoking_at=coalesce(revoking_at,clock_timestamp()),
           detail=coalesce(detail,'deadline elapsed; capacity remains charged')
     WHERE state='active' AND deadline_at <= clock_timestamp();
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed;
END;
$$;

CREATE OR REPLACE FUNCTION weather_experiment.begin_reservation_cleanup(candidate uuid, token bigint)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    UPDATE weather_experiment.resource_reservations
       SET state='revoking', revoking_at=coalesce(revoking_at,clock_timestamp()),
           cleanup_started_at=coalesce(cleanup_started_at,clock_timestamp())
     WHERE operation_id=candidate AND fencing_token=token AND state IN ('active','revoking');
    IF NOT FOUND THEN
        RAISE EXCEPTION 'reservation fence mismatch or reservation is no longer cleanable'
          USING ERRCODE = 'integrity_constraint_violation';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION weather_experiment.release_clean_reservation(candidate uuid, token bigint)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    UPDATE weather_experiment.resource_reservations
       SET state='released',cleanup_verified_at=clock_timestamp(),released_at=clock_timestamp(),
           detail='allocator stopped; local and remote allocations verified absent'
     WHERE operation_id=candidate AND fencing_token=token AND state='releasable';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'reservation is not releasable or fence mismatched'
          USING ERRCODE = 'integrity_constraint_violation';
    END IF;
END;
$$;

-- Mutation entry points are worker capabilities, never ambient schema rights.
REVOKE EXECUTE ON FUNCTION weather_experiment.acquire_resource_reservation(uuid,text,text,uuid,text,text,text,text,bigint,bigint,bigint,bigint,bigint) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION weather_experiment.assert_active_reservation(uuid,bigint) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION weather_experiment.publish_run(uuid,uuid,bigint) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION weather_experiment.publish_run(uuid) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION weather_experiment.publish_revision(uuid) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION weather_experiment.revoke_expired_reservations() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION weather_experiment.begin_reservation_cleanup(uuid,bigint) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION weather_experiment.release_clean_reservation(uuid,bigint) FROM PUBLIC;
