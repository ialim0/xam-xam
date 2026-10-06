output "region" {
  value = var.region
}

output "instance_id" {
  description = "Instance à cibler avec SSM (Session Manager, deploy.sh)."
  value       = aws_instance.bot.id
}

output "public_ip" {
  description = "Elastic IP : créer l'enregistrement DNS A du domaine vers cette adresse."
  value       = aws_eip.bot.public_ip
}

output "ecr_repository_url" {
  value = aws_ecr_repository.bot.repository_url
}

output "backup_bucket" {
  value = aws_s3_bucket.backup.bucket
}

output "ssm_prefix" {
  description = "Préfixe des paramètres SSM lus au démarrage."
  value       = local.ssm_prefix
}

output "ami_id" {
  description = "AMI utilisée : la recopier dans ami_id pour la figer explicitement."
  value       = aws_instance.bot.ami
}
