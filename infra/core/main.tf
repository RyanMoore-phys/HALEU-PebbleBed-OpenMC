variable "az" { type = string }
data "aws_region" "current" {}

resource "aws_vpc" "block" {
  cidr_block           = "10.72.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = { Name = "block-vpc" }
}
resource "aws_subnet" "private" {
  vpc_id                  = aws_vpc.block.id
  availability_zone       = var.az
  cidr_block              = "10.72.1.0/24"
  map_public_ip_on_launch = false
  tags = { Name = "block-private" }
}
resource "aws_route_table" "private" { vpc_id = aws_vpc.block.id }
resource "aws_route_table_association" "private" {
  route_table_id = aws_route_table.private.id
  subnet_id      = aws_subnet.private.id
}
resource "aws_vpc_endpoint" "s3" {
  vpc_id          = aws_vpc.block.id
  service_name    = "com.amazonaws.${data.aws_region.current.name}.s3"
  route_table_ids = [aws_route_table.private.id]
}
resource "aws_security_group" "nodes" {
  name   = "block-nodes"
  vpc_id = aws_vpc.block.id
  ingress {
    protocol  = "-1"
    from_port = 0
    to_port   = 0
    self      = true
  }
  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_security_group" "services" {
  for_each = { efs = 2049, endpoints = 443 }
  name     = "block-${each.key}"
  vpc_id   = aws_vpc.block.id
  ingress {
    protocol        = "tcp"
    from_port       = each.value
    to_port         = each.value
    security_groups = [aws_security_group.nodes.id]
  }
}
resource "aws_efs_file_system" "block" {
  encrypted              = true
  availability_zone_name = var.az
  tags = { Name = "block-data" }
}
resource "aws_efs_mount_target" "block" {
  file_system_id  = aws_efs_file_system.block.id
  subnet_id       = aws_subnet.private.id
  security_groups = [aws_security_group.services["efs"].id]
}
resource "aws_efs_access_point" "block" {
  file_system_id = aws_efs_file_system.block.id
  posix_user {
    uid = 1000
    gid = 1000
  }
  root_directory {
    path = "/block"
    creation_info {
      owner_uid   = 1000
      owner_gid   = 1000
      permissions = "0750"
    }
  }
}
resource "aws_s3_bucket" "storage" {
  for_each      = toset(["data", "results"])
  bucket_prefix = "openmc-block-${each.key}-"
}
resource "aws_s3_bucket_public_access_block" "storage" {
  for_each                = aws_s3_bucket.storage
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_ecr_repository" "block" {
  name                 = "block-depletion"
  image_tag_mutability = "IMMUTABLE"
}
resource "aws_cloudwatch_log_group" "block" {
  name              = "/aws/batch/block-depletion"
  retention_in_days = 14
}
output "network" {
  value = {
    vpc = aws_vpc.block.id, subnet = aws_subnet.private.id,
    endpoints = aws_security_group.services["endpoints"].id, nodes = aws_security_group.nodes.id
  }
}
output "storage" {
  value = { for k, bucket in aws_s3_bucket.storage : k => bucket.id }
}
output "efs" {
  value = { filesystem = aws_efs_file_system.block.id, access_point = aws_efs_access_point.block.id }
}
output "ecr_uri" { value = aws_ecr_repository.block.repository_url }
