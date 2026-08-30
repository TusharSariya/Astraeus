#!/bin/sh
# Create the bucket, its quota, and two least-privilege service users.
#
# Root credentials are used here and ONLY here. The worker needs to write and
# prune objects; the API and the tile server only ever read one bucket. Handing
# either of them the root key would make an API compromise a storage compromise.
set -eu

BUCKET="${WEATHER_MINIO_BUCKET:?bucket name is required}"
CAP="${WEATHER_STORAGE_CAP:-25GiB}"

mc alias set root "${WEATHER_MINIO_ENDPOINT}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}"
mc mb --ignore-existing "root/${BUCKET}"
mc quota set "root/${BUCKET}" --size "${CAP}"

cat >/tmp/weather-writer.json <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"],
      "Resource": ["arn:aws:s3:::${BUCKET}/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation", "s3:ListBucketMultipartUploads"],
      "Resource": ["arn:aws:s3:::${BUCKET}"]
    }
  ]
}
JSON

cat >/tmp/weather-reader.json <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": ["arn:aws:s3:::${BUCKET}/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": ["arn:aws:s3:::${BUCKET}"]
    }
  ]
}
JSON

mc admin policy create root weather-writer /tmp/weather-writer.json 2>/dev/null || \
  mc admin policy update root weather-writer /tmp/weather-writer.json
mc admin policy create root weather-reader /tmp/weather-reader.json 2>/dev/null || \
  mc admin policy update root weather-reader /tmp/weather-reader.json

# `mc admin user add` is idempotent enough for a local stack: re-running resets
# the secret to the same compose-supplied value.
mc admin user add root "${WEATHER_MINIO_WRITER_KEY}" "${WEATHER_MINIO_WRITER_SECRET}"
mc admin user add root "${WEATHER_MINIO_READER_KEY}" "${WEATHER_MINIO_READER_SECRET}"
mc admin policy attach root weather-writer --user "${WEATHER_MINIO_WRITER_KEY}" 2>/dev/null || true
mc admin policy attach root weather-reader --user "${WEATHER_MINIO_READER_KEY}" 2>/dev/null || true

echo "minio bootstrap complete: bucket=${BUCKET} quota=${CAP} writer=${WEATHER_MINIO_WRITER_KEY} reader=${WEATHER_MINIO_READER_KEY}"
