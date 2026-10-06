#!/bin/sh
# Point d'entrée du conteneur : chaque fichier de XAMXAM_SECRETS_DIR (monté en lecture seule
# depuis /run/xamxam, un tmpfs de l'hôte) devient une variable d'environnement du processus.
# Les secrets restent ainsi hors de la configuration Docker (docker inspect, disque).
set -eu

secrets_dir="${XAMXAM_SECRETS_DIR:-/run/secrets/xamxam}"
if [ -d "$secrets_dir" ]; then
	for file in "$secrets_dir"/*; do
		[ -f "$file" ] || continue
		name=$(basename "$file")
		case "$name" in
		"" | [!A-Z]* | *[!A-Z0-9_]*)
			echo "entrypoint : nom de secret ignoré" >&2
			continue
			;;
		esac
		value=$(cat "$file")
		export "$name=$value"
	done
fi

exec "$@"
