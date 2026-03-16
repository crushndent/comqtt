#!/bin/bash
set -e

# Initialize Postgres if data directory is empty
if [ -z "$(ls -A /var/lib/postgresql/data)" ]; then
    echo "Initializing Postgres data directory..."
    chown -R postgres:postgres /var/lib/postgresql
    su - postgres -c "/usr/lib/postgresql/15/bin/initdb -D /var/lib/postgresql/data"
    
    echo "Starting Postgres temporarily to create user and db..."
    su - postgres -c "/usr/lib/postgresql/15/bin/pg_ctl -D /var/lib/postgresql/data -w start"
    
    su - postgres -c "psql -c \"CREATE USER mqtt_user WITH PASSWORD 'mqtt_password';\""
    su - postgres -c "psql -c \"CREATE DATABASE mqtt_db OWNER mqtt_user;\""
    su - postgres -c "psql -c \"ALTER USER postgres WITH PASSWORD 'postgres';\""
    
    su - postgres -c "/usr/lib/postgresql/15/bin/pg_ctl -D /var/lib/postgresql/data -m fast -w stop"
fi

# Initialize Redis dir
mkdir -p /var/lib/redis
chown -R redis:redis /var/lib/redis

# Wait for Postgres to be ready (managed by supervisord, but we might need migrations first if we don't rely on auto-restart loops)
# For simplicity, we assume Django will fail and restart until DB is ready, or we can use wait-for-it.
# However, since we run everything under supervisord, we can just run migrations in a pre-start script or let Django handle it if we wrap it.
# Ideally, migrations should run once. Let's do it here by starting PG temporarily again if needed, or rely on a separate init step.
# A robust way: Start PG in background, run migrations, stop PG, then exec supervisord.

echo "Starting Postgres for migrations..."
su - postgres -c "/usr/lib/postgresql/15/bin/pg_ctl -D /var/lib/postgresql/data -w start"

echo "Running Django migrations..."
cd /app
python3 manage.py migrate

echo "Stopping Postgres..."
su - postgres -c "/usr/lib/postgresql/15/bin/pg_ctl -D /var/lib/postgresql/data -m fast -w stop"

echo "Starting Supervisord..."
exec /usr/bin/supervisord -c /app/supervisord.conf
