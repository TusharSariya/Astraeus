\set ON_ERROR_STOP on
SET client_min_messages TO NOTICE;
CREATE OR REPLACE FUNCTION pg_temp.assert(condition boolean,label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN IF condition THEN RAISE NOTICE 'PASS  %',label; ELSE RAISE EXCEPTION 'FAIL  %',label; END IF; END; $$;
CREATE OR REPLACE FUNCTION pg_temp.expect_failure(statement text,label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN BEGIN EXECUTE statement; EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'PASS  %  (rejected: %)',label,left(SQLERRM,100); RETURN; END;
RAISE EXCEPTION 'FAIL  % - statement was accepted',label; END; $$;
SELECT * FROM weather_experiment.acquire_resource_reservation('10000000-0000-0000-0000-000000000001','task-owner','host-a','10000000-0000-0000-0000-000000000002','7','/tmp/task','task','store-a',600,700,100,1000000000,2000);
SELECT pg_temp.assert((SELECT deadline_at-admitted_at BETWEEN interval '14 minutes 59 seconds' AND interval '15 minutes 1 second' FROM weather_experiment.resource_reservations WHERE operation_id='10000000-0000-0000-0000-000000000001'),'task reservation uses the fixed database-server 15 minute deadline');
SELECT * FROM weather_experiment.acquire_resource_reservation('20000000-0000-0000-0000-000000000001','ingest-owner','host-b','20000000-0000-0000-0000-000000000002','7','/tmp/ingest','ingestion','store-b',600,700,100,1000000000,2000);
SELECT pg_temp.assert((SELECT deadline_at-admitted_at BETWEEN interval '1 hour 59 minutes 59 seconds' AND interval '2 hours 1 second' FROM weather_experiment.resource_reservations WHERE operation_id='20000000-0000-0000-0000-000000000001'),'ingestion reservation uses the fixed database-server 2 hour deadline');
SELECT pg_temp.expect_failure($q$SELECT * FROM weather_experiment.acquire_resource_reservation('20000000-0000-0000-0000-000000000003','second-owner','host-b','20000000-0000-0000-0000-000000000004','7','/tmp/second','ingestion','store-b',1,1401,0,1000000000,2000)$q$,'a competing process cannot overcommit the same host filesystem');
SELECT pg_temp.assert(NOT EXISTS(SELECT 1 FROM weather_experiment.resource_reservations WHERE operation_id='20000000-0000-0000-0000-000000000003'),'failed admission records neither global nor local allocation');
UPDATE weather_experiment.resource_reservations SET admitted_at=clock_timestamp()-interval '16 minutes',deadline_at=clock_timestamp()-interval '1 minute' WHERE operation_id='10000000-0000-0000-0000-000000000001';
SELECT weather_experiment.revoke_expired_reservations();
SELECT pg_temp.assert((SELECT state='revoking' FROM weather_experiment.resource_reservations WHERE operation_id='10000000-0000-0000-0000-000000000001'),'deadline expiry transitions active to revoking');
SELECT pg_temp.assert((SELECT sum(store_bytes)=600 FROM weather_experiment.resource_reservations WHERE store_key='store-a' AND state <> 'released'),'revoking capacity remains fully charged');
SELECT pg_temp.expect_failure(format('SELECT weather_experiment.assert_active_reservation(''10000000-0000-0000-0000-000000000001'',%s)',(SELECT fencing_token FROM weather_experiment.resource_reservations WHERE operation_id='10000000-0000-0000-0000-000000000001')),'a paused owner cannot use an expired fence');
SELECT pg_temp.expect_failure($q$SELECT weather_experiment.assert_active_reservation('20000000-0000-0000-0000-000000000001',999999)$q$,'a wrong fencing token is refused');
UPDATE weather_experiment.resource_reservations SET cleanup_started_at=clock_timestamp()-interval '16 minutes',detail='operator recovery required' WHERE operation_id='10000000-0000-0000-0000-000000000001';
SELECT pg_temp.assert((SELECT state='revoking' AND released_at IS NULL FROM weather_experiment.resource_reservations WHERE operation_id='10000000-0000-0000-0000-000000000001'),'missing the cleanup objective retains the charge for operator recovery');
SELECT pg_temp.expect_failure(format('SELECT weather_experiment.release_clean_reservation(''10000000-0000-0000-0000-000000000001'',%s)',(SELECT fencing_token FROM weather_experiment.resource_reservations WHERE operation_id='10000000-0000-0000-0000-000000000001')),'revoking alone cannot release capacity');
UPDATE weather_experiment.resource_reservations SET state='releasable' WHERE operation_id='10000000-0000-0000-0000-000000000001';
SELECT weather_experiment.release_clean_reservation('10000000-0000-0000-0000-000000000001',(SELECT fencing_token FROM weather_experiment.resource_reservations WHERE operation_id='10000000-0000-0000-0000-000000000001'));
SELECT pg_temp.assert((SELECT state='released' AND cleanup_verified_at IS NOT NULL FROM weather_experiment.resource_reservations WHERE operation_id='10000000-0000-0000-0000-000000000001'),'only proven releasable cleanup reaches released');
DO $$ BEGIN RAISE NOTICE 'ALL RESOURCE RESERVATION INVARIANTS HOLD'; END $$;
