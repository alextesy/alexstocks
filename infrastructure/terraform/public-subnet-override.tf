# Override for public subnet deployment
# If you don't have private subnets + NAT Gateway, use this configuration

# Comment: If your VPC doesn't have private subnets with NAT Gateway,
# you can use public subnets instead. Just change assign_public_ip to true
# in the EventBridge scheduler network configuration.

# This file is here as a reference. To use public subnets:
# 1. Edit eventbridge.tf and change all "assign_public_ip = false" to "true"
# 2. Use any subnets from your VPC in terraform.tfvars
# 3. Make sure the subnets have an Internet Gateway route

# Alternative: Create this override (will take precedence)
# Uncomment the sections below if you want to use this approach:

# locals {
#   use_public_subnets = true
# }
