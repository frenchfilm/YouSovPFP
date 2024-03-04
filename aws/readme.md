### ESOV API AWS

add aws/lambda/.env.yaml with secret api keys  
run `cd aws/lambda && sh build_zip.sh`  
add aws/terraform/terraform.tfvars with env vars  
change terraform s3 state buckets manually  
run `cd aws/terraform && terraform apply`  
run command on terraform output command_copy_images  
test lambdas with POST and x-api-key header with value from .env.yaml

