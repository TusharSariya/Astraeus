-- Upgrade persistent volumes from the legacy source-state vocabulary to the
-- registry's current closed vocabulary before any worker publication.
ALTER TABLE weather_experiment.sources DROP CONSTRAINT IF EXISTS sources_registry_status_check;
ALTER TABLE weather_experiment.sources ADD CONSTRAINT sources_registry_status_check CHECK (registry_status IN (
  'operational','implemented-unverified','catalogued','credential-required',
  'licence-blocked','link-only','partnership-only','unavailable','rejected','superseded'
  ,'active','implementing','credential_required','licence_review',
  'duplicate_evidence','unsupported_field','retired'
));
