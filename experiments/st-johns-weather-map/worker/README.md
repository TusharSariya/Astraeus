# Ingestion worker

One process, on purpose. `runtime.py` schedules each registered adapter on the
cadence derived from its registry record, isolates sources from each other, and
publishes a run's artifacts only after the shared manifest validator has judged
the run complete and QC-passed.

## Liveness vs. progress

`--check-heartbeat` answers two different questions, because a live process is
not the same claim as advancing ingestion:

1. **Is the process alive?** The heartbeat file is rewritten before every
   source, not only between cycles, so a long serial cycle over many sources
   does not read as death.
2. **Is ingestion advancing?** The same file records `last_success` and the
   nominal cadence per source. A source that succeeded before and has since
   gone `STALL_CADENCE_MULTIPLIER` cadences without another success marks the
   worker unhealthy.

A source that has **never** succeeded is reported but does not fail the
healthcheck. A 404 endpoint or a product this experiment cannot yet decode is an
ingestion fact to surface through the API's source status, not a reason to
restart-loop the container.

## Credentials

The worker holds a scoped MinIO writer key: object read/write/delete on one
bucket, no admin rights. The bucket, its quota and that user are created by the
one-shot `minio-bootstrap` Compose service, which is the only place root MinIO
credentials are used.
