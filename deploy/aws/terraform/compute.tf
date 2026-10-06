# Dernière Amazon Linux 2023, lue uniquement si aucune AMI n'est fixée (premier apply).
data "aws_ssm_parameter" "al2023" {
  count = var.ami_id == null ? 1 : 0
  name  = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

locals {
  ami_id = var.ami_id != null ? var.ami_id : nonsensitive(data.aws_ssm_parameter.al2023[0].value)
}

resource "aws_instance" "bot" {
  ami                    = local.ami_id
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnet.selected.id
  vpc_security_group_ids = [aws_security_group.bot.id]
  iam_instance_profile   = aws_iam_instance_profile.bot.name

  # IMDSv2 obligatoire ; une limite de 1 saut empêche les conteneurs de lire les
  # identifiants du rôle de l'instance.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  # Crédits CPU « standard » : pas de facturation au-delà du tarif horaire (une t3 en mode
  # « unlimited » peut facturer les dépassements prolongés).
  credit_specification {
    cpu_credits = "standard"
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gb
    encrypted             = true
    delete_on_termination = true
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    region          = var.region
    domain          = var.domain
    bucket          = aws_s3_bucket.backup.bucket
    ssm_prefix      = local.ssm_prefix
    registry        = split("/", aws_ecr_repository.bot.repository_url)[0]
    cache_volume_id = aws_ebs_volume.cache.id
    container_uid   = var.container_uid
    compose_version = var.compose_version
    compose_sha256  = var.compose_sha256
  })

  tags = { Name = "${var.project}-bot" }

  lifecycle {
    # Un apply futur ne remplace jamais l'instance : ni nouvelle AMI, ni changement du
    # script de premier démarrage (les mises à jour passent par deploy.sh).
    ignore_changes = [ami, user_data]
  }
}

# Le cache vit sur un volume EBS séparé du disque système : il survit au remplacement de
# l'instance et se sauvegarde indépendamment.
resource "aws_ebs_volume" "cache" {
  availability_zone = var.availability_zone
  size              = var.cache_volume_gb
  type              = "gp3"
  encrypted         = true

  tags = { Name = "${var.project}-cache" }
}

resource "aws_volume_attachment" "cache" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.cache.id
  instance_id = aws_instance.bot.id
}
