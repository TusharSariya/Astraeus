#!/bin/sh
# The bucket, quota and this user's policy are created by the one-shot
# `minio-bootstrap` service using root credentials. The worker holds only a
# scoped writer key and must not be able to administer MinIO.
set -eu

exec python /app/worker/runtime.py
