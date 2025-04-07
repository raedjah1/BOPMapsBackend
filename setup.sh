#!/bin/bash

# Colors for better readability
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Setting up BOPMaps Backend...${NC}"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is not installed. Please install Python 3 and try again.${NC}"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version | cut -d ' ' -f 2)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d '.' -f 1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d '.' -f 2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
    echo -e "${YELLOW}Warning: Python 3.8 or higher is recommended. You are using Python $PYTHON_VERSION.${NC}"
fi

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo -e "${YELLOW}PostgreSQL is not installed. You'll need to install it for the project to work properly.${NC}"
fi

# Check if PostGIS is installed
if ! psql -U postgres -c "SELECT PostGIS_Version();" &> /dev/null; then
    echo -e "${YELLOW}PostGIS extension is not available. You'll need to install it for the project to work properly.${NC}"
fi

# Check if virtualenv is installed
if ! command -v virtualenv &> /dev/null; then
    echo -e "${YELLOW}virtualenv is not installed. Installing virtualenv...${NC}"
    pip3 install virtualenv
fi

# Create virtualenv if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "${GREEN}Creating virtual environment...${NC}"
    virtualenv venv
fi

# Activate virtualenv
echo -e "${GREEN}Activating virtual environment...${NC}"
source venv/bin/activate

# Install dependencies
echo -e "${GREEN}Installing dependencies...${NC}"
pip install -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${GREEN}Creating .env file from template...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}Please update the .env file with your database credentials and other settings.${NC}"
fi

# Create database if it doesn't exist
echo -e "${GREEN}Checking database...${NC}"
if ! psql -U postgres -lqt | cut -d \| -f 1 | grep -qw bopmaps; then
    echo -e "${GREEN}Creating database...${NC}"
    psql -U postgres -c "CREATE DATABASE bopmaps;"
    psql -U postgres -d bopmaps -c "CREATE EXTENSION IF NOT EXISTS postgis;"
    psql -U postgres -d bopmaps -c "CREATE EXTENSION IF NOT EXISTS postgis_topology;"
fi

# Run migrations
echo -e "${GREEN}Running migrations...${NC}"
python manage.py migrate

# Create superuser if none exists
echo -e "${GREEN}Checking if superuser exists...${NC}"
SUPERUSER_EXISTS=$(python manage.py shell -c "from django.contrib.auth import get_user_model; print(get_user_model().objects.filter(is_superuser=True).exists())")

if [ "$SUPERUSER_EXISTS" == "False" ]; then
    echo -e "${GREEN}Creating superuser...${NC}"
    python manage.py createsuperuser
fi

# Run collectstatic
echo -e "${GREEN}Collecting static files...${NC}"
python manage.py collectstatic --noinput

# Create media directory if it doesn't exist
if [ ! -d "media" ]; then
    echo -e "${GREEN}Creating media directory...${NC}"
    mkdir -p media
fi

# Create logs directory if it doesn't exist
if [ ! -d "logs" ]; then
    echo -e "${GREEN}Creating logs directory...${NC}"
    mkdir -p logs
    touch logs/bopmaps.log
fi

echo -e "${GREEN}Setup complete!${NC}"
echo -e "${GREEN}Run 'source venv/bin/activate' to activate the virtual environment.${NC}"
echo -e "${GREEN}Run 'python manage.py runserver' to start the development server.${NC}" 