#!/bin/bash

set -e  # Exit immediately if a command exits with a non-zero status.

# Load environment variables from .env file
if [ -f .env ]; then
    set -a  # automatically export all variables
    source .env
    set +a
fi

# Check if required environment variables are set
if [ -z "$AWS_DEFAULT_REGION" ]; then
    echo "Error: AWS_DEFAULT_REGION environment variable is not set. Please check your .env file."
    exit 1
fi

# Function to deploy an Elastic Beanstalk environment for streaming
deploy_stream_environment() {
    local env_name=$1
    local platform=$2
    local cname_prefix=$3

    # Build and push Docker image first
    ./build_and_push.sh

    # Check if the environment exists
    if ! eb status $env_name 2>/dev/null; then
        echo "Creating environment $env_name with CNAME prefix $cname_prefix..."
        eb create $env_name --platform "$platform" --region $AWS_DEFAULT_REGION --elb-type network --cname $cname_prefix
    else
        echo "Deploying to existing environment $env_name..."
        eb use $env_name
        eb deploy $env_name
    fi
}

# Function to deploy an Elastic Beanstalk environment
deploy_environment() {
    local env_name=$1
    local platform=$2
    local cname_prefix=$3

    # Build and push Docker image first
    ./build_and_push.sh

    # Check if the environment exists
    if ! eb status $env_name 2>/dev/null; then
        echo "Creating environment $env_name with CNAME prefix $cname_prefix..."
        eb create $env_name --platform "$platform" --region $AWS_DEFAULT_REGION --cname $cname_prefix
    else
        echo "Deploying to existing environment $env_name..."
        eb use $env_name
        eb deploy $env_name
    fi
}

# Deploy Backend Environment
echo "Deploying Backend Environment..."
deploy_environment "povbackend" "Docker running on 64bit Amazon Linux 2" "povreality-backend"

# Deploy Streaming Environment
echo "Deploying Streaming Environment..."
cd streaming-env
deploy_stream_environment "povstream" "Docker running on 64bit Amazon Linux 2" "povreality-stream"
cd ../

# Deploy Lambda Functions
echo "Deploying Lambda Functions..."
cd aws_lambda
./deploy-lambda.sh
cd ../

echo "Deployment process completed successfully."