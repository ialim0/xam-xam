#!/usr/bin/env bash
# Sauvegarde quotidienne du cache (/cache) vers le bucket S3 (versionné, donc historisé).
# Lancé par xamxam-backup.timer. Rien n'est supprimé du bucket.
set -euo pipefail

: "${AWS_REGION:?AWS_REGION non définie}"
: "${XAMXAM_BACKUP_BUCKET:?XAMXAM_BACKUP_BUCKET non définie}"
cache="${XAMXAM_CACHE_PATH:-/cache}"

aws s3 sync "$cache/" "s3://$XAMXAM_BACKUP_BUCKET/cache/" \
	--region "$AWS_REGION" \
	--exclude "*.tmp" \
	--no-follow-symlinks \
	--only-show-errors
echo "backup-cache : synchronisation terminée."
