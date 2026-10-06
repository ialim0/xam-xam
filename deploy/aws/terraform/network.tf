# VPC par défaut : une seule instance publique, pas besoin d'un réseau dédié.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnet" "selected" {
  vpc_id            = data.aws_vpc.default.id
  availability_zone = var.availability_zone
  default_for_az    = true
}

resource "aws_security_group" "bot" {
  name        = "${var.project}-bot"
  description = "Xam-Xam : HTTP et HTTPS uniquement (pas de SSH, administration par SSM)"
  vpc_id      = data.aws_vpc.default.id
}

resource "aws_vpc_security_group_ingress_rule" "web" {
  for_each = {
    http_ipv4  = { port = 80, cidr_ipv4 = "0.0.0.0/0", cidr_ipv6 = null }
    https_ipv4 = { port = 443, cidr_ipv4 = "0.0.0.0/0", cidr_ipv6 = null }
    http_ipv6  = { port = 80, cidr_ipv4 = null, cidr_ipv6 = "::/0" }
    https_ipv6 = { port = 443, cidr_ipv4 = null, cidr_ipv6 = "::/0" }
  }

  security_group_id = aws_security_group.bot.id
  description       = each.key
  ip_protocol       = "tcp"
  from_port         = each.value.port
  to_port           = each.value.port
  cidr_ipv4         = each.value.cidr_ipv4
  cidr_ipv6         = each.value.cidr_ipv6
}

# Sortie : ECR, S3, SSM, Bedrock, Meta, Kiriku, Let's Encrypt.
resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.bot.id
  description       = "Sortie vers Internet"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_eip" "bot" {
  domain   = "vpc"
  instance = aws_instance.bot.id

  tags = { Name = "${var.project}-bot" }
}
