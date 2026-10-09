#!/usr/bin/env bash
# Déploie le bot sur Amazon ECS Express Mode (Fargate + HTTPS fourni par AWS, sans domaine).
#
# 1. Crée au besoin le dépôt ECR, le cluster et les deux rôles IAM (idempotent).
# 2. Construit l'image du commit courant (le dépôt doit être propre) et la pousse dans ECR.
# 3. Injecte chaque paramètre SSM sous /xamxam/ comme variable d'environnement (secrets ECS).
# 4. Crée le service, ou le met à jour (déploiement progressif), puis affiche l'URL du webhook.
#
# Une seule tâche (min = max = 1) : la mémoire de conversation et les rafales de messages
# vivent en RAM, deux tâches couperaient les conversations.
set -euo pipefail

region="${AWS_REGION:-eu-west-3}"
# Toutes les commandes aws utilisent cette région, même sans région dans ~/.aws/config.
export AWS_REGION="$region" AWS_DEFAULT_REGION="$region"
service="${XAMXAM_SERVICE:-xamxam}"
cluster="${XAMXAM_CLUSTER:-default}"
prefix="${XAMXAM_SSM_PREFIX:-/xamxam/}"
cpu="${XAMXAM_CPU:-1024}"       # unités CPU : 1024 = 1 vCPU
memory="${XAMXAM_MEMORY:-2048}" # Mio
execution_role="${service}-execution"
infrastructure_role="${service}-infrastructure"

root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
if [[ -n "$(git -C "$root" status --porcelain)" ]]; then
	echo "deploy : le dépôt contient des modifications non commitées, arrêt." >&2
	exit 1
fi
tag="$(git -C "$root" rev-parse --short=12 HEAD)"
account="$(aws sts get-caller-identity --query Account --output text)"
registry="$account.dkr.ecr.$region.amazonaws.com"
image="$registry/$service:$tag"
service_arn="arn:aws:ecs:$region:$account:service/$cluster/$service"

ensure_role() {
	local name="$1" principal="$2" policy="$3"
	if ! aws iam get-role --role-name "$name" >/dev/null 2>&1; then
		echo "Création du rôle $name."
		aws iam create-role --role-name "$name" --output text --query Role.Arn \
			--assume-role-policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"$principal\"},\"Action\":\"sts:AssumeRole\"}]}" >/dev/null
		new_role=1
	fi
	aws iam attach-role-policy --role-name "$name" --policy-arn "$policy"
}

# --- 1. Ressources ----------------------------------------------------------------------
aws ecr describe-repositories --region "$region" --repository-names "$service" >/dev/null 2>&1 ||
	aws ecr create-repository --region "$region" --repository-name "$service" \
		--image-tag-mutability IMMUTABLE --image-scanning-configuration scanOnPush=true >/dev/null
aws ecs create-cluster --region "$region" --cluster-name "$cluster" >/dev/null

new_role=0
ensure_role "$execution_role" ecs-tasks.amazonaws.com \
	arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
# Lecture des seuls paramètres du bot (la clé KMS par défaut aws/ssm ne demande rien de plus).
aws iam put-role-policy --role-name "$execution_role" --policy-name ssm-xamxam \
	--policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"ssm:GetParameters\",\"Resource\":\"arn:aws:ssm:$region:$account:parameter${prefix%/}/*\"}]}"
ensure_role "$infrastructure_role" ecs.amazonaws.com \
	arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices
# La création de l'équilibreur lit les attributs du compte avec ce rôle ; la politique gérée
# ne le permet pas (CreateLoadBalancer refusé, AccessDenied, sans ce droit en lecture seule).
aws iam put-role-policy --role-name "$infrastructure_role" --policy-name elb-account-attributes \
	--policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"ec2:DescribeAccountAttributes","Resource":"*"}]}'
if ((new_role)); then
	sleep 15 # propagation IAM : un rôle tout neuf n'est pas utilisable immédiatement
fi

# --- 2. Image -----------------------------------------------------------------------------
if aws ecr describe-images --region "$region" --repository-name "$service" \
	--image-ids "imageTag=$tag" >/dev/null 2>&1; then
	echo "Image $tag déjà présente dans ECR."
else
	aws ecr get-login-password --region "$region" |
		docker login --username AWS --password-stdin "$registry"
	docker build --platform linux/amd64 -t "$image" "$root"
	docker push "$image"
fi

# --- 3. Configuration ---------------------------------------------------------------------
names="$(aws ssm get-parameters-by-path --region "$region" --path "$prefix" \
	--query 'Parameters[].Name' --output text)"
if [[ -z "$names" ]]; then
	echo "deploy : aucun paramètre sous $prefix ; lancez d'abord set-secrets.sh." >&2
	exit 1
fi
container="$(
	python3 - "$image" "$region" "$account" $names <<'EOF'
import json, sys
image, region, account, *names = sys.argv[1:]
secrets = [
    {"name": n.rsplit("/", 1)[-1], "valueFrom": f"arn:aws:ssm:{region}:{account}:parameter{n}"}
    for n in names
]
print(json.dumps({"image": image, "containerPort": 8080, "secrets": secrets}))
EOF
)"
scaling='{"minTaskCount":1,"maxTaskCount":1}'

# --- 4. Service ---------------------------------------------------------------------------
status="$(aws ecs describe-services --region "$region" --cluster "$cluster" --services "$service" \
	--query 'services[0].status' --output text 2>/dev/null || true)"
common=(--region "$region" --primary-container "$container" --health-check-path /health
	--cpu "$cpu" --memory "$memory" --scaling-target "$scaling")
if [[ "$status" == "ACTIVE" ]]; then
	echo "Mise à jour du service $service ($tag)."
	aws ecs update-express-gateway-service --service-arn "$service_arn" "${common[@]}" >/dev/null
else
	echo "Création du service $service ($tag)."
	aws ecs create-express-gateway-service --cluster "$cluster" --service-name "$service" \
		--execution-role-arn "arn:aws:iam::$account:role/$execution_role" \
		--infrastructure-role-arn "arn:aws:iam::$account:role/$infrastructure_role" \
		"${common[@]}" >/dev/null
fi

echo "Attente de la stabilisation du service (quelques minutes)…"
aws ecs wait services-stable --region "$region" --cluster "$cluster" --services "$service"
endpoint="$(aws ecs describe-express-gateway-service --region "$region" --service-arn "$service_arn" \
	--query 'service.activeConfigurations[0].ingressPaths[0].endpoint' --output text 2>/dev/null || true)"
if [[ -z "$endpoint" || "$endpoint" == "None" ]]; then
	endpoint="$service.ecs.$region.on.aws"
fi
endpoint="https://${endpoint#https://}"
echo "Déployé : $tag"
echo "Santé : ${endpoint%/}/health"
echo "Webhook à saisir chez Meta : ${endpoint%/}/webhook"
