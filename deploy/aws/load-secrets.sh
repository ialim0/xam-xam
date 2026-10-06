#!/usr/bin/env bash
# Lit les paramètres SSM sous XAMXAM_SSM_PREFIX (SecureString déchiffrés) et les écrit, un
# fichier par paramètre, dans XAMXAM_SECRETS_PATH : un tmpfs (mémoire), jamais le disque.
# Les fichiers appartiennent à l'UID de l'utilisateur du conteneur, en mode 400.
# Lancé au démarrage par xamxam-secrets.service, avant xamxam.service.
set -euo pipefail

: "${AWS_REGION:?AWS_REGION non définie}"
prefix="${XAMXAM_SSM_PREFIX:-/xamxam/}"
target="${XAMXAM_SECRETS_PATH:-/run/xamxam}"
container_uid="${XAMXAM_CONTAINER_UID:-10001}"

# Refuse d'écrire ailleurs que sur un tmpfs.
fstype=$(findmnt --noheadings --output FSTYPE --target "$(dirname "$target")")
if [[ "$fstype" != "tmpfs" ]]; then
	echo "load-secrets : $(dirname "$target") n'est pas un tmpfs ($fstype), arrêt." >&2
	exit 1
fi

umask 077
staging="$(dirname "$target")/.xamxam-secrets.$$"
rm -rf "$staging"
install -d -m 0700 "$staging"
trap 'rm -rf "$staging"' EXIT

# Les valeurs passent de la sortie de la CLI à Python par un tube, sans fichier intermédiaire.
aws ssm get-parameters-by-path \
	--region "$AWS_REGION" \
	--path "$prefix" \
	--recursive \
	--with-decryption \
	--query 'Parameters[].[Name,Value]' \
	--output json |
	python3 -c '
import json, os, re, sys
staging, uid = sys.argv[1], int(sys.argv[2])
count = 0
for name, value in json.load(sys.stdin):
    key = name.rsplit("/", 1)[-1]
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
        print(f"load-secrets : paramètre ignoré (nom invalide)", file=sys.stderr)
        continue
    path = os.path.join(staging, key)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(value)
    os.chown(path, uid, uid)
    count += 1
print(f"load-secrets : {count} paramètre(s) chargé(s).")
' "$staging" "$container_uid"

# Remplacement atomique du dossier, lisible uniquement par l'utilisateur du conteneur.
chown "$container_uid:$container_uid" "$staging"
chmod 0500 "$staging"
rm -rf "$target"
mv "$staging" "$target"
trap - EXIT
