#!/bin/sh
set -eu

export DATABASE_URL="$(cat /run/secrets/database_url)"
export ADMIN_PASSWORD="$(cat /run/secrets/admin_password)"

exec python /app/scripts/run_admin_restricted.py
