
echo "Building zip files for AWS Lambda functions"

echo "Cleaning up old zip files"
rm -rf getRandomBGFunction.zip
rm -rf generatePFPFunction.zip
rm -rf .aws-sam/build

echo "Building"
sam build

echo "Zipping up the files"
cd .aws-sam/build/GeneratePFPFunction/
zip -r ../../../generatePFPFunction.zip .
cd ../GetRandomBGFunction/
zip -r ../../../getRandomBGFunction.zip .
cd ../../../../
