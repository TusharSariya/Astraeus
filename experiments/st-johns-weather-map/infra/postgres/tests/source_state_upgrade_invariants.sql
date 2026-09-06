\set ON_ERROR_STOP on
SET client_min_messages TO NOTICE;
CREATE OR REPLACE FUNCTION pg_temp.assert(condition boolean,label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN IF condition THEN RAISE NOTICE 'PASS  %',label; ELSE RAISE EXCEPTION 'FAIL  %',label; END IF; END; $$;
INSERT INTO weather_experiment.sources(source_id,producer,product,registry_status,adapter_version)
VALUES('legacy-state-proof','proof','proof','implementing','v1'),
      ('current-state-proof','proof','proof','implemented-unverified','v1');
SELECT pg_temp.assert((SELECT registry_status='implementing' FROM weather_experiment.sources WHERE source_id='legacy-state-proof'),'upgrade preserves a legacy implementing row');
SELECT pg_temp.assert((SELECT registry_status='implemented-unverified' FROM weather_experiment.sources WHERE source_id='current-state-proof'),'current experimental state is accepted for publication metadata');
SELECT pg_temp.assert(NOT EXISTS(SELECT 1 FROM weather_experiment.sources WHERE registry_status='operational'),'migration never promotes a source to operational');
DO $$ BEGIN RAISE NOTICE 'ALL SOURCE STATE UPGRADE INVARIANTS HOLD'; END $$;
