#!/usr/bin/env bash
set -euo pipefail

mkdir -p /backups
pg_dump --format=custom --file="/backups/openmodel-$(date +%F-%H%M).dump"
