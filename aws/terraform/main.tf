terraform {
  backend "s3" {
    bucket = "oleks-dev-esov-api-terraformstate"
    key    = "esov-terraformstate"
    region = "us-east-1"
  }
}

variable "publicImagesBucketName" {
  type = string
}

variable "argsImagesBucketName" {
  type = string
}

variable "region" {
  type = string
}

# s3

resource "aws_s3_bucket" "public_images_bucket" {
  bucket = var.publicImagesBucketName
}

resource "aws_s3_bucket" "images_args_bucket" {
  bucket = var.argsImagesBucketName
}

resource "aws_s3_bucket_public_access_block" "images_public_acl" {
  bucket = aws_s3_bucket.public_images_bucket.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_public_access_block" "images_arg_acl" {
  bucket = aws_s3_bucket.images_args_bucket.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "images_public_policy" {
  bucket = aws_s3_bucket.public_images_bucket.id

  policy = <<POLICY
{
  "Version":"2012-10-17",
  "Statement":[
    {
      "Sid":"PublicReadGetObject",
      "Effect":"Allow",
      "Principal": "*",
      "Action":["s3:GetObject"],
      "Resource":["arn:aws:s3:::${aws_s3_bucket.public_images_bucket.bucket}/*"]
    }
  ]
}
POLICY
}

resource "aws_s3_bucket_policy" "images_arg_policy" {
    bucket = aws_s3_bucket.images_args_bucket.id

  policy = <<POLICY
{
  "Version":"2012-10-17",
  "Statement":[
    {
      "Sid":"PublicReadGetObject",
      "Effect":"Allow",
      "Principal": "*",
      "Action":["s3:GetObject"],
      "Resource":["arn:aws:s3:::${aws_s3_bucket.images_args_bucket.bucket}/*"]
    }
  ]
}
POLICY
}

# vpc

resource "aws_vpc" "vpc_esov" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "subnet_esov" {
  vpc_id     = aws_vpc.vpc_esov.id
  cidr_block = "10.0.1.0/24"
}

# VPC Endpoint for S3
resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.vpc_esov.id
  service_name = "com.amazonaws.${var.region}.s3"
  route_table_ids = [aws_route_table.public.id]
  depends_on = [ aws_route_table.public ]
}

# Route table
resource "aws_route_table" "main" {
  vpc_id = aws_vpc.vpc_esov.id
}

### IGW for external api requests

# Create a new public subnet
resource "aws_subnet" "public_subnet" {
  vpc_id     = aws_vpc.vpc_esov.id
  cidr_block = "10.0.2.0/24"
  map_public_ip_on_launch = true
}

# Create an Internet Gateway and attach it to the VPC
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.vpc_esov.id
}

# Create a route table for the public subnet
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.vpc_esov.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
}

resource "aws_nat_gateway" "nat_gateway" {
  subnet_id = aws_subnet.public_subnet.id

  allocation_id = aws_eip.nat_eip.allocation_id

  depends_on = [aws_eip.nat_eip]
}

resource "aws_eip" "nat_eip" {
  vpc = true

  depends_on = [aws_internet_gateway.igw]
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.vpc_esov.id
}

# Create a route in the private route table that points to the NAT Gateway
resource "aws_route" "private_nat_gateway" {
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.nat_gateway.id
}

# Associate the public subnet with the public route table
resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public_subnet.id
  route_table_id = aws_route_table.public.id
}

# Associate the esov_api subnet with the private route table
resource "aws_route_table_association" "esov_api_private" {
  subnet_id      = aws_subnet.subnet_esov.id
  route_table_id = aws_route_table.private.id
}

### IGW


# redis

resource "aws_security_group" "redis" {
  name        = "redis"
  description = "Allow inbound traffic"
  vpc_id      = aws_vpc.vpc_esov.id

  ingress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  depends_on = [ aws_vpc.vpc_esov ]
}

resource "aws_elasticache_subnet_group" "redis_subnet_group" {
  name       = "redis-subnet-group"
  subnet_ids = [aws_subnet.subnet_esov.id]
  depends_on = [ aws_subnet.subnet_esov ]
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "redis"
  engine               = "redis"
  node_type            = "cache.t2.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis5.0"
  engine_version       = "5.0.6"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.redis_subnet_group.name
  security_group_ids   = [aws_security_group.redis.id]
  depends_on = [ aws_elasticache_subnet_group.redis_subnet_group, aws_security_group.redis ]
}

# lambda

resource "aws_iam_role" "api_lambda_role" {
  name = "LambdaS3Role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# todo: split and finegrane policies
resource "aws_iam_policy" "api_lambda_s3_policy" {
  name        = "LambdaS3Policy"
  description = "Policy to allow Lambda to read/write to S3"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "*"
        ],
        Effect = "Allow",
        Resource = [
          "${aws_s3_bucket.public_images_bucket.arn}/*",
          "${aws_s3_bucket.images_args_bucket.arn}/*",
        ]
      },
      # {
      #   Action = [
      #     R/W
      #   ],
      #   Effect = "Allow",
      #   Resource = [
      #     "${aws_s3_bucket.images_args_bucket.arn}/*",
      #   ]
      # }
    ]
  })

  depends_on = [aws_s3_bucket.images_args_bucket, aws_s3_bucket.public_images_bucket]
}

resource "aws_iam_policy" "api_lambda_logs_policy" {
  name        = "LambdaLogsPolicy"
  description = "Policy to allow Lambda to write logs to CloudWatch"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:CreateLogGroup",
          "logs:DescribeLogStreams"
        ],
        Effect   = "Allow",
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_iam_policy" "api_lambda_redis_policy" {
  name        = "LambdaRedisPolicy"
  description = "Policy to allow Lambda to connect to elasticache"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
            "elasticache:Describe*",
            "elasticache:List*",
            "elasticache:Get*"
        ],
        Effect   = "Allow",
        Resource = "*"
      }
    ]
  })
}

# IAM Policy for EC2 Network Interfaces
resource "aws_iam_policy" "ec2_network_interface_policy" {
  name        = "EC2NetworkInterfacePolicy"
  description = "Policy to allow EC2 network interface operations"

  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [
      {
        Action   = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface"
        ],
        Effect   = "Allow",
        Resource = "*"
      }
    ]
  })
}


resource "aws_iam_role_policy_attachment" "s3_attachment" {
  policy_arn = aws_iam_policy.api_lambda_s3_policy.arn
  role       = aws_iam_role.api_lambda_role.name
  depends_on = [aws_iam_policy.api_lambda_s3_policy, aws_iam_role.api_lambda_role]
}

resource "aws_iam_role_policy_attachment" "logs_attachment" {
  policy_arn = aws_iam_policy.api_lambda_logs_policy.arn
  role       = aws_iam_role.api_lambda_role.name
  depends_on = [aws_iam_policy.api_lambda_logs_policy, aws_iam_role.api_lambda_role]
}

resource "aws_iam_role_policy_attachment" "redis_attachment" {
  policy_arn = aws_iam_policy.api_lambda_redis_policy.arn
  role       = aws_iam_role.api_lambda_role.name
  depends_on = [aws_iam_policy.api_lambda_redis_policy, aws_iam_role.api_lambda_role]
}

resource "aws_iam_role_policy_attachment" "ec2_network_interface_attachment" {
  policy_arn = aws_iam_policy.ec2_network_interface_policy.arn
  role       = aws_iam_role.api_lambda_role.name
  depends_on = [aws_iam_policy.ec2_network_interface_policy, aws_iam_role.api_lambda_role]
}

resource "aws_lambda_function" "generatePFPFunction" {
  function_name    = "generatePFPFunction"
  role             = aws_iam_role.api_lambda_role.arn
  handler          = "main.generate_pfp"
  runtime          = "python3.8"
  filename         = "../lambda/generatePFPFunction.zip"
  timeout          = 900
  memory_size      = 128
  vpc_config {
    subnet_ids         = [aws_subnet.subnet_esov.id]
    security_group_ids = [aws_security_group.redis.id]
  }
  source_code_hash = filebase64sha256("../lambda/generatePFPFunction.zip")
  environment {
    variables = {
      "REDIS_HOST" = aws_elasticache_cluster.redis.cache_nodes.0.address
      "PUBLIC_IMAGES_BUCKET" = aws_s3_bucket.public_images_bucket.bucket
      "ARGS_IMAGES_BUCKET" = aws_s3_bucket.images_args_bucket.bucket
    }
  }
  depends_on = [
    aws_iam_role.api_lambda_role, 
    aws_elasticache_cluster.redis, 
    aws_s3_bucket.public_images_bucket, 
    aws_s3_bucket.images_args_bucket,
    aws_iam_role_policy_attachment.redis_attachment,
    aws_iam_role_policy_attachment.s3_attachment,
    aws_iam_role_policy_attachment.logs_attachment,
    aws_iam_role_policy_attachment.ec2_network_interface_attachment
    ]
}

resource "aws_lambda_function" "getRandomBGFunction" {
  function_name    = "getRandomBGFunction"
  role             = aws_iam_role.api_lambda_role.arn
  handler          = "main.get_random_bg"
  runtime          = "python3.8"
  filename         = "../lambda/getRandomBGFunction.zip"
  timeout          = 900
  memory_size      = 128
  vpc_config {
    subnet_ids         = [aws_subnet.subnet_esov.id]
    security_group_ids = [aws_security_group.redis.id]
  }
  source_code_hash = filebase64sha256("../lambda/getRandomBGFunction.zip")
  environment {
    variables = {
      "REDIS_HOST" = aws_elasticache_cluster.redis.cache_nodes.0.address
      "PUBLIC_IMAGES_BUCKET" = aws_s3_bucket.public_images_bucket.bucket
      "ARGS_IMAGES_BUCKET" = aws_s3_bucket.images_args_bucket.bucket
    }
  }
  depends_on = [
    aws_iam_role.api_lambda_role, 
    aws_elasticache_cluster.redis, 
    aws_s3_bucket.public_images_bucket, 
    aws_s3_bucket.images_args_bucket,
    aws_iam_role_policy_attachment.redis_attachment,
    aws_iam_role_policy_attachment.s3_attachment,
    aws_iam_role_policy_attachment.logs_attachment,
    aws_iam_role_policy_attachment.ec2_network_interface_attachment
    ]
}

resource "aws_lambda_function_url" "generatePFPFunction_url" {
  function_name      = aws_lambda_function.generatePFPFunction.function_name
  authorization_type = "NONE"
}

resource "aws_lambda_function_url" "getRandomBGFunction_url" {
  function_name      = aws_lambda_function.getRandomBGFunction.function_name
  authorization_type = "NONE"
}

# outs

output "redis_endpoint" {
  value = aws_elasticache_cluster.redis.cache_nodes.0.address
}

output "public_images_bucket" {
  value = aws_s3_bucket.public_images_bucket.bucket
}

output "args_images_bucket" {
  value = aws_s3_bucket.images_args_bucket.bucket
}

output "gen_pfp_url" {
  value = aws_lambda_function_url.generatePFPFunction_url.function_url
}

output "get_random_bg_url" {
  value = aws_lambda_function_url.getRandomBGFunction_url.function_url
}

output "command_copy_images" {
  value = "aws s3 cp ./images s3://${aws_s3_bucket.public_images_bucket.bucket} --recursive"
}