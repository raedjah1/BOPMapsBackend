#!/bin/bash

# Disable pager for AWS CLI commands
export AWS_PAGER=""

set -e  # Exit immediately if a command exits with a non-zero status.

# Function to wait for Lambda function to be ready
wait_for_lambda() {
    local function_name=$1
    echo "Waiting for Lambda function $function_name to be ready..."
    while true; do
        STATUS=$(aws lambda get-function --function-name $function_name --region $AWS_REGION --query 'Configuration.LastUpdateStatus' --output text)
        if [ "$STATUS" = "Successful" ]; then
            echo "Lambda function $function_name is ready"
            break
        elif [ "$STATUS" = "Failed" ]; then
            echo "Lambda function $function_name update failed"
            exit 1
        fi
        echo "Current status: $STATUS. Waiting..."
        sleep 5
    done
}

# Function to deploy a Lambda function
deploy_lambda() {
    local function_name=$1
    local handler=$2
    local source_dir=$3
    local env_vars=$4

    echo "Building Lambda package for $function_name..."
    # Create a temporary build directory
    rm -rf $source_dir/build
    mkdir -p $source_dir/build

    # Install dependencies
    cd $source_dir
    pip3 install -r requirements.txt -t build/
    cd ..

    # Copy Lambda function
    cp $source_dir/lambda_function.py $source_dir/build/

    # Special handling for FCM notification Lambda
    if [ "$function_name" = "fcm_notification" ]; then
        echo "Copying Firebase credentials for FCM notification Lambda..."
        cp "$GOOGLE_APPLICATION_CREDENTIALS" $source_dir/build/
    fi

    # Create ZIP package
    cd $source_dir/build
    zip -r ../../${function_name}.zip .
    cd ../..

    echo "Deploying Lambda function $function_name..."
    if aws lambda get-function --function-name $function_name --region $AWS_REGION 2>&1 | grep -q 'Function not found'; then
        # Create new function
        aws lambda create-function \
            --function-name $function_name \
            --runtime python3.9 \
            --handler $handler \
            --role arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/${function_name}_role \
            --zip-file fileb://${function_name}.zip \
            --environment "$env_vars" \
            --region $AWS_REGION
        
        wait_for_lambda $function_name
    else
        # Update existing function code
        aws lambda update-function-code \
            --function-name $function_name \
            --zip-file fileb://${function_name}.zip \
            --region $AWS_REGION
        
        wait_for_lambda $function_name

        # Update function configuration
        aws lambda update-function-configuration \
            --function-name $function_name \
            --environment "$env_vars" \
            --region $AWS_REGION
        
        wait_for_lambda $function_name
    fi

    # Clean up
    rm -f ${function_name}.zip
    rm -rf $source_dir/build
}

# Load environment variables
source .env

# Check required environment variables
if [ -z "$AWS_REGION" ] || [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "Error: AWS credentials not set. Please check your .env file."
    exit 1
fi

if [ ! -f "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo "Error: Firebase service account file ($GOOGLE_APPLICATION_CREDENTIALS) not found."
    exit 1
fi

if [ -z "$BACKEND_URL" ] || [ -z "$ANALYTICS_AUTH_TOKEN" ]; then
    echo "Error: BACKEND_URL and ANALYTICS_AUTH_TOKEN must be set in .env file."
    exit 1
fi

echo "Setting up user permissions..."
# Create IAM policy for Lambda deployment
aws iam create-policy --policy-name lambda_deployment_policy --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "lambda:*",
                "lambda:InvokeFunction",
                "iam:CreateRole",
                "iam:PutRolePolicy",
                "iam:PassRole",
                "cloudwatch:PutMetricData",
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
                "events:PutRule",
                "events:PutTargets"
            ],
            "Resource": "*"
        }
    ]
}' || true

# Attach policy to user
aws iam attach-user-policy --user-name POVBackend --policy-arn arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):policy/lambda_deployment_policy || true

echo "Verifying Lambda permissions..."
aws lambda get-account-settings

echo "Permissions verified successfully. Proceeding with deployment..."

echo "Creating IAM roles and policies..."
# Create Lambda execution roles for both functions
for function_name in "fcm_notification" "trigger_analytics"; do
    aws iam create-role \
        --role-name ${function_name}_role \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "lambda.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }' || true

    # Attach basic Lambda execution policy
    aws iam attach-role-policy \
        --role-name ${function_name}_role \
        --policy-arn arn:aws:aws-service-role/lambda.amazonaws.com/AWSServiceRoleForLambda || true
done

# Deploy FCM notification Lambda
deploy_lambda "fcm_notification" "lambda_function.lambda_handler" "fcm_notification" \
    "Variables={GOOGLE_APPLICATION_CREDENTIALS=$(basename $GOOGLE_APPLICATION_CREDENTIALS)}"

# Deploy Analytics trigger Lambda
deploy_lambda "trigger_analytics" "lambda_function.lambda_handler" "trigger_analytics" \
    "Variables={BACKEND_URL=$BACKEND_URL,ANALYTICS_AUTH_TOKEN=$ANALYTICS_AUTH_TOKEN}"

# Create EventBridge rule for analytics trigger (midnight UTC)
echo "Setting up EventBridge trigger for analytics..."
aws events put-rule \
    --name "daily-analytics-trigger" \
    --schedule-expression "cron(0 0 * * ? *)" \
    --state ENABLED \
    --description "Triggers analytics Lambda function daily at midnight UTC"

# Add Lambda permission for EventBridge
aws lambda add-permission \
    --function-name trigger_analytics \
    --statement-id EventBridgeInvoke \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn $(aws events describe-rule --name daily-analytics-trigger --query 'Arn' --output text) || true

# Add target to EventBridge rule
aws events put-targets \
    --rule daily-analytics-trigger \
    --targets "Id"="1","Arn"="$(aws lambda get-function --function-name trigger_analytics --query 'Configuration.FunctionArn' --output text)"

# Update FCM_LAMBDA_ARN in .env
LAMBDA_ARN=$(aws lambda get-function --function-name fcm_notification --region $AWS_REGION --query 'Configuration.FunctionArn' --output text)
sed -i.bak "s|^FCM_LAMBDA_ARN=.*|FCM_LAMBDA_ARN=$LAMBDA_ARN|" .env
rm -f .env.bak

echo "Deployment completed successfully!"