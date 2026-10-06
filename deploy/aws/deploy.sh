#!/usr/bin/env bash
# Déploiement depuis le poste de l'équipe, sans SSH :
#   1. build de l'image (linux/amd64) et push vers ECR, taguée par le commit ;
#   2. envoi des fichiers de déploiement (compose, Caddyfile, scripts, unités systemd) dans
#      le bucket S3 du projet ;
#   3. SSM Run Command sur l'instance : install.sh (docker compose pull et up).
# Prérequis : AWS CLI v2 authentifiée, Docker avec buildx, terraform apply déjà fait.
# Usage : deploy/aws/deploy.sh
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$here/../.." && pwd)"
tf_dir="$here/terraform"

tf_output() { terraform -chdir="$tf_dir" output -raw "$1"; }

region="$(tf_output region)"
instance_id="$(tf_output instance_id)"
repository_url="$(tf_output ecr_repository_url)"
bucket="$(tf_output backup_bucket)"
registry="${repository_url%%/*}"

# Les tags ECR sont immuables : on déploie un commit, jamais un arbre modifié.
if [[ -n "$(git -C "$repo_root" status --porcelain)" ]]; then
	echo "deploy : des modifications ne sont pas commitées, arrêt." >&2
	exit 1
fi
tag="$(git -C "$repo_root" rev-parse --short=12 HEAD)"
image="$repository_url:$tag"

echo "==> Image $image"
aws ecr get-login-password --region "$region" |
	docker login --username AWS --password-stdin "$registry"
if aws ecr describe-images --region "$region" --repository-name "${repository_url#*/}" \
	--image-ids "imageTag=$tag" >/dev/null 2>&1; then
	echo "    déjà présente dans ECR, build ignoré."
else
	docker buildx build --platform linux/amd64 --tag "$image" --push "$repo_root"
fi

echo "==> Paquet de déploiement"
bundle="$(mktemp -t xamxam-deploy-XXXXXX.tar.gz)"
trap 'rm -f "$bundle"' EXIT
tar -czf "$bundle" -C "$here" \
	docker-compose.yml Caddyfile entrypoint.sh load-secrets.sh install.sh \
	backup-cache.sh restore-cache.sh systemd
bundle_key="deploy/$tag.tar.gz"
aws s3 cp --region "$region" --only-show-errors "$bundle" "s3://$bucket/$bundle_key"

echo "==> Mise à jour de l'instance $instance_id (SSM Run Command)"
# Toutes les valeurs interpolées sont sûres : identifiants hexadécimaux, noms AWS.
read -r -d '' commands <<JSON || true
{"commands": [
  "set -euo pipefail",
  "work=\$(mktemp -d)",
  "trap 'rm -rf \"\$work\"' EXIT",
  "aws s3 cp --region $region --only-show-errors s3://$bucket/$bundle_key \"\$work/bundle.tar.gz\"",
  "tar -xzf \"\$work/bundle.tar.gz\" -C \"\$work\"",
  "bash \"\$work/install.sh\" $image"
]}
JSON
command_id="$(aws ssm send-command \
	--region "$region" \
	--instance-ids "$instance_id" \
	--document-name AWS-RunShellScript \
	--comment "xamxam $tag" \
	--parameters "$commands" \
	--query Command.CommandId --output text)"

echo "    commande $command_id, attente du résultat…"
if ! aws ssm wait command-executed --region "$region" \
	--command-id "$command_id" --instance-id "$instance_id"; then
	status=failed
fi
aws ssm get-command-invocation --region "$region" \
	--command-id "$command_id" --instance-id "$instance_id" \
	--query '[Status, StandardOutputContent, StandardErrorContent]' --output text
if [[ "${status:-}" == failed ]]; then
	echo "deploy : échec sur l'instance (voir ci-dessus)." >&2
	exit 1
fi
echo "==> Déployé : $image"
