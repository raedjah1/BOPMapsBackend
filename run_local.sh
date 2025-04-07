#!/bin/bash

# Colors for better readability
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting BOPMaps Backend Development Server...${NC}"

# Activate virtual environment
if [ -d "venv" ]; then
    echo -e "${GREEN}Activating virtual environment...${NC}"
    source venv/bin/activate
else
    echo -e "${YELLOW}Virtual environment not found. Running setup script...${NC}"
    chmod +x setup.sh
    ./setup.sh
    source venv/bin/activate
fi

# Check for migrations
echo -e "${GREEN}Checking for migrations...${NC}"
python manage.py migrate

# Start the development server
echo -e "${GREEN}Starting development server...${NC}"
python manage.py runserver

# When the server stops
echo -e "${GREEN}Server stopped.${NC}" 