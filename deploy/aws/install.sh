#!/usr/bin/env bash
# Exécuté sur l'instance par deploy.sh (via SSM Run Command), depuis le dossier du paquet
# extrait : installe les fichiers, fixe l'image à déployer, puis docker compose pull et up.
# Usage : install.sh <uri-de-l-image>
set -euo pipefail

image="${1:?usage : install.sh <uri-de-l-image>}"
source_dir="$(cd "$(dirname "$0")" && pwd)"
app_dir=/opt/xamxam
env_file=/etc/xamxam/xamxam.env

install -d -m 0755 "$app_dir"
install -m 0644 "$source_dir/docker-compose.yml" "$source_dir/Caddyfile" "$app_dir/"
install -m 0755 "$source_dir/entrypoint.sh" "$source_dir/load-secrets.sh" \
	"$source_dir/backup-cache.sh" "$source_dir/restore-cache.sh" "$app_dir/"
install -m 0644 "$source_dir"/systemd/*.service "$source_dir"/systemd/*.timer /etc/systemd/system/

# Image à déployer : seule ligne du fichier d'environnement modifiée par le déploiement.
if grep -q '^XAMXAM_IMAGE=' "$env_file"; then
	sed -i "s|^XAMXAM_IMAGE=.*|XAMXAM_IMAGE=$image|" "$env_file"
else
	echo "XAMXAM_IMAGE=$image" >>"$env_file"
fi

systemctl daemon-reload
systemctl enable xamxam-secrets.service xamxam.service xamxam-backup.timer
systemctl start xamxam-backup.timer

set -a
# shellcheck source=/dev/null
source "$env_file"
set +a
cd "$app_dir"
docker compose pull --quiet
# Recharge les secrets (un paramètre SSM a pu changer) puis recrée les conteneurs ;
# xamxam.service échoue si le bot n'est pas en bonne santé, ce qui fait échouer le déploiement.
systemctl restart xamxam-secrets.service xamxam.service
docker compose ps
