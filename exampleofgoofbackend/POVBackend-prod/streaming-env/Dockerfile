FROM alfg/nginx-rtmp

# Install Python and pip
RUN apk add --no-cache python3 py3-pip supervisor gcc musl-dev python3-dev linux-headers

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf
COPY nginx.conf /etc/nginx/nginx.conf.template

# Create directory for data and SSL certs
RUN mkdir -p /opt/data/hls
RUN mkdir -p /etc/nginx/ssl

# Copy SSL certificate and key
COPY ssl_certificate.pem /etc/nginx/ssl/
COPY ssl_key.key /etc/nginx/ssl/
# Set proper permissions for the SSL key file (only readable by root)
RUN chmod 600 /etc/nginx/ssl/ssl_key.key

# Copy files
COPY async_hls_file_watcher.py /opt/data/
COPY requirements.txt /opt/data/
COPY .env /opt/data/
COPY main_app.py /opt/data/
COPY stream_moderator.py /opt/data/

# Set working directory
WORKDIR /opt/data

# Install Python requirements
RUN pip3 install -r requirements.txt

# Add Supervisor configuration
COPY supervisord.conf /etc/supervisord.conf

# Clean up build dependencies to reduce image size
RUN apk del gcc musl-dev python3-dev linux-headers

EXPOSE 80
EXPOSE 443
EXPOSE 1935

# Start Supervisor
CMD envsubst "$(env | sed -e 's/=.*//' -e 's/^/\$/g')" < \
  /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf && \
  /usr/bin/supervisord -c /etc/supervisord.conf
