
echo "Building zip files for AWS Lambda functions"

echo "Cleaning up old zip files"
rm -rf getRandomBGFunction.zip
rm -rf generatePFPFunction.zip
rm -rf .aws-sam/build

echo "Building"
sam build

echo "Zipping up the files"
cd .aws-sam/build/GeneratePFPFunction/
rm -rf .env.additional.yaml
zip -r ../../../generatePFPFunction.zip .
cd ../GetRandomBGFunction/
rm -rf .env.additional.yaml
zip -r ../../../getRandomBGFunction.zip .
cd ../../../../
