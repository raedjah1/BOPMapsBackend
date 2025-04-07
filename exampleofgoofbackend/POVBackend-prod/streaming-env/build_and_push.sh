#!/bin/bash

# Exit on error
set -e

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Check for required AWS environment variables
if [ -z "$AWS_DEFAULT_REGION" ]; then
    echo "Error: AWS_DEFAULT_REGION environment variable is not set"
    exit 1
fi

if [ -z "$AWS_ACCOUNT_ID" ]; then
    # Try to get AWS account ID automatically
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    if [ $? -ne 0 ]; then
        echo "Error: Could not determine AWS account ID. Please set AWS_ACCOUNT_ID in your .env file"
        exit 1
    fi
fi

# ECR repository details
REPOSITORY_NAME="povstreaming"
IMAGE_TAG="latest"

# Full ECR image name
FULL_IMAGE_NAME="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/$REPOSITORY_NAME:$IMAGE_TAG"

# Create ECR repository if it doesn't exist
echo "Ensuring ECR repository exists..."
if ! aws ecr describe-repositories --repository-names $REPOSITORY_NAME 2>/dev/null; then
    echo "Creating ECR repository $REPOSITORY_NAME..."
    aws ecr create-repository --repository-name $REPOSITORY_NAME
fi

# Authenticate Docker to ECR
echo "Authenticating with ECR..."
aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com

# Set up Docker buildx for multi-platform builds
echo "Setting up Docker buildx..."
docker buildx create --use

# Build and push the Docker image
echo "Building and pushing Docker image..."
docker buildx build --platform linux/amd64 -t $FULL_IMAGE_NAME --push .

echo "Successfully built and pushed $FULL_IMAGE_NAME to ECR!" 