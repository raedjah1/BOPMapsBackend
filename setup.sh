#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}BOPMaps Backend Setup${NC}"
echo -e "${BLUE}========================================${NC}"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is not installed. Please install Python 3 before continuing.${NC}"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "${BLUE}Creating virtual environment...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}Virtual environment created.${NC}"
else
    echo -e "${GREEN}Virtual environment already exists.${NC}"
fi

# Activate virtual environment
echo -e "${BLUE}Activating virtual environment...${NC}"
source venv/bin/activate

# Check if pip is up to date
echo -e "${BLUE}Upgrading pip...${NC}"
pip install --upgrade pip

# Install dependencies
echo -e "${BLUE}Installing dependencies...${NC}"
pip install -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${BLUE}Creating .env file from example...${NC}"
    cp .env.example .env
    echo -e "${GREEN}.env file created. Please update it with your settings.${NC}"
else
    echo -e "${GREEN}.env file already exists.${NC}"
fi

# Check if PostgreSQL with PostGIS is installed
echo -e "${BLUE}Checking for PostgreSQL with PostGIS...${NC}"
if ! command -v psql &> /dev/null; then
    echo -e "${RED}PostgreSQL is not installed or not in PATH.${NC}"
    echo -e "${RED}Please install PostgreSQL with PostGIS and make sure it's in your PATH.${NC}"
    echo -e "${RED}On macOS: brew install postgresql postgis${NC}"
    echo -e "${RED}On Ubuntu: sudo apt-get install postgresql postgresql-contrib postgis${NC}"
else
    echo -e "${GREEN}PostgreSQL is installed.${NC}"
fi

# Create database if it doesn't exist
echo -e "${BLUE}Checking if database exists...${NC}"
if ! psql -lqt | cut -d \| -f 1 | grep -qw bopmaps; then
    echo -e "${BLUE}Creating database...${NC}"
    createdb bopmaps
    psql -d bopmaps -c "CREATE EXTENSION postgis;"
    echo -e "${GREEN}Database created with PostGIS extension.${NC}"
else
    echo -e "${GREEN}Database already exists.${NC}"
fi

# Run migrations
echo -e "${BLUE}Running migrations...${NC}"
python manage.py migrate

# Create superuser if needed
echo -e "${BLUE}Do you want to create a superuser? (y/n)${NC}"
read -r create_superuser

if [ "$create_superuser" = "y" ]; then
    python manage.py createsuperuser
fi

echo -e "${GREEN}Setup complete!${NC}"
echo -e "${GREEN}To start the development server:${NC}"
echo -e "${BLUE}python manage.py runserver${NC}"
echo ""
echo -e "${GREEN}To use Docker instead:${NC}"
echo -e "${BLUE}docker-compose up${NC}"
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Happy coding!${NC}"
echo -e "${BLUE}========================================${NC}" 