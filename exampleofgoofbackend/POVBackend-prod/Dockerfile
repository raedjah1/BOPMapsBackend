FROM --platform=linux/amd64 python:3.9-bullseye

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app/

# Create static directory
RUN mkdir -p /app/static

# Expose port
EXPOSE 80

CMD ["sh", "-c", "\
celery -A pov_backend worker --loglevel=info & \
celery -A pov_backend beat --loglevel=info & \
python manage.py collectstatic --noinput & \
python manage.py runserver 0.0.0.0:80 \
"]