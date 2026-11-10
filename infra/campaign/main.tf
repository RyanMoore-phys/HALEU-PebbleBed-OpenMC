variable "state_bucket" { type = string }
data "aws_region" "current" {}
data "terraform_remote_state" "core" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = "block/core.tfstate"
    region = data.aws_region.current.name
  }
}
locals { network = data.terraform_remote_state.core.outputs.network }
resource "aws_vpc_endpoint" "private" {
  for_each            = toset(["ecs", "ecs-agent", "ecs-telemetry", "ecr.api", "ecr.dkr", "logs"])
  service_name        = "com.amazonaws.${data.aws_region.current.name}.${each.key}"
  vpc_id              = local.network.vpc
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [local.network.subnet]
  security_group_ids  = [local.network.endpoints]
}
resource "aws_placement_group" "block" {
  name     = "block-campaign"
  strategy = "cluster"
}
output "placement_group" { value = aws_placement_group.block.name }
