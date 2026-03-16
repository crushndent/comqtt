# Stage 1: Build the Go binary
FROM golang:1.22-bookworm AS builder

WORKDIR /app

# Copy go mod and sum files
COPY go.mod go.sum ./
RUN go mod download

# Copy the source code
COPY . .

# Build the custom binary
RUN go build -o comqtt cmd/custom/main.go

# Stage 2: Final Image
FROM python:3.11-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-15 \
    postgresql-contrib-15 \
    redis-server \
    supervisor \
    nginx \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy the binary from the builder stage
COPY --from=builder /app/comqtt /app/comqtt

# Copy requirements and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the Django project code
COPY . /app

# Copy configuration files
COPY supervisord.conf /app/supervisord.conf
COPY entrypoint.sh /app/entrypoint.sh

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Create configuration directory for comqtt
RUN mkdir -p /app/config

# Configuration for Redis
RUN sed -i 's/daemonize yes/daemonize no/g' /etc/redis/redis.conf
RUN sed -i 's/bind 127.0.0.1 -::1/bind 0.0.0.0/g' /etc/redis/redis.conf
RUN mkdir -p /var/lib/redis && chown -R redis:redis /var/lib/redis

# Expose ports
# 1883: MQTT TCP
# 8000: Django
# 8080: Comqtt Stats (if enabled)
EXPOSE 1883 8000 8080

# Define volume for persistence
VOLUME ["/var/lib/postgresql/data", "/var/lib/redis"]

# Set the entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]
