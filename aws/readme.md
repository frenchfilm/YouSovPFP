### ESOV API AWS

build metadata with notebook csv_pfp_data_proc.ipynb   
copy metadata folder to ./images and name to layers_meta   
copy all background images to ./images/bgs   
add aws/lambda/.env.yaml with secret api keys  
run `cd aws/lambda && sh build_zip.sh`  
add aws/terraform/terraform.tfvars with env vars  
change terraform s3 state buckets manually  
run `cd aws/terraform && terraform apply`  
run command on terraform output command_copy_images  
test lambdas with POST and x-api-key header with value from .env.yaml

roles  
AmazonEC2FullAccess  
AmazonElastiCacheFullAccess  
AmazonS3FullAccess  
AmazonVPCFullAccess  
AWSCloudFormationFullAccess  
AWSLambda_FullAccess  
IAMFullAccess  