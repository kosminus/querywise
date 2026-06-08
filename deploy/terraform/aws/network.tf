# Minimal private-subnet VPC for the data plane. RDS + ElastiCache live here;
# compute (EKS/ECS) reaches them via security-group references. Set
# create_vpc = false to drop these into an existing VPC instead.

resource "aws_vpc" "this" {
  count                = var.create_vpc ? 1 : 0
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${var.name_prefix}-vpc" }
}

resource "aws_subnet" "private" {
  count             = var.create_vpc ? length(local.azs) : 0
  vpc_id            = aws_vpc.this[0].id
  availability_zone = local.azs[count.index]
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, count.index)

  tags = { Name = "${var.name_prefix}-private-${local.azs[count.index]}" }
}
