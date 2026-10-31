#!/bin/sh
set -eu

export DATABASE_URL="$(cat /run/secrets/database_url)"
export ADMIN_PASSWORD="$(cat /run/secrets/admin_password)"

exec python -m buscadin_bot.web.admin
