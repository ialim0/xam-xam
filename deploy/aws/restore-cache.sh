#!/usr/bin/env bash
# Restaure le cache depuis le bucket S3 vers /cache, bot arrêté pendant la copie.
# Usage (sur l'instance, via Session Manager) : sudo /opt/xamxam/restore-cache.sh
set -euo pipefail

set -a
# shellcheck source=/dev/null
source /etc/xamxam/xamxam.env
set +a
: "${XAMXAM_BACKUP_BUCKET:?XAMXAM_BACKUP_BUCKET non définie}"
cache="${XAMXAM_CACHE_PATH:-/cache}"
container_uid="${XAMXAM_CONTAINER_UID:-10001}"

cd /opt/xamxam
docker compose stop bot
trap 'docker compose start bot' EXIT

aws s3 sync "s3://$XAMXAM_BACKUP_BUCKET/cache/" "$cache/" \
	--region "$AWS_REGION" \
	--exclude "bot-state.sqlite3*" \
	--only-show-errors
chown -R "$container_uid:$container_uid" "$cache"
echo "restore-cache : cache restauré depuis s3://$XAMXAM_BACKUP_BUCKET/cache/."
