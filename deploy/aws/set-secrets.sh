#!/usr/bin/env bash
# Enregistre la configuration du bot dans SSM Parameter Store, sous /xamxam/<VARIABLE>.
# Les secrets sont des SecureString, saisis sans écho et passés à la CLI par l'entrée standard :
# ils n'apparaissent ni dans l'historique du shell ni dans la liste des processus.
# Entrée vide : le paramètre existant est conservé (ou reste absent).
# Relancez le script pour modifier une valeur, puis deploy.sh pour l'appliquer.
set -euo pipefail

region="${AWS_REGION:-eu-west-3}"
prefix="${XAMXAM_SSM_PREFIX:-/xamxam/}"

secrets=(
	WHATSAPP_TOKEN WHATSAPP_APP_SECRET WHATSAPP_VERIFY_TOKEN
	RODIUM_API_KEY GEMINI_API_KEY KVICC_API_KEY TIMALENS_API_KEY
	LOG_HASH_KEY UNLIMITED_NUMBERS
)
settings=(
	WHATSAPP_PHONE_NUMBER_ID KVICC_TTS_URL KVICC_STT_URL
	TIMALENS_VOICE TIMALENS_MAX_CREDITS RODIUM_MODEL RODIUM_FALLBACK_MODEL
)

put() {
	local name="$1" type="$2" value="$3"
	printf '%s' "$value" | aws ssm put-parameter --region "$region" --name "$prefix$name" \
		--type "$type" --value file:///dev/stdin --overwrite --output text >/dev/null
	echo "  $prefix$name enregistré ($type)."
}

echo "Région $region, préfixe $prefix. Entrée vide : valeur inchangée."
echo "LOG_HASH_KEY : générez-la avec « openssl rand -hex 32 »."
for name in "${secrets[@]}"; do
	read -rsp "$name (secret) : " value
	echo
	if [[ -n "$value" ]]; then put "$name" SecureString "$value"; fi
done
for name in "${settings[@]}"; do
	read -rp "$name : " value
	if [[ -n "$value" ]]; then put "$name" String "$value"; fi
done
unset value

echo "Paramètres présents :"
aws ssm get-parameters-by-path --region "$region" --path "$prefix" \
	--query 'Parameters[].[Name,Type]' --output text
