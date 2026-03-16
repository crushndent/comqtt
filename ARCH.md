# ARCH.md

This file provides guidance to LLMs when working with code in this repository.

## Project Overview

This is a fork/customization of [comqtt](https://github.com/wind-c/comqtt), a high-performance MQTT broker written in Go (v3.0/v3.1.1/v5.0). The project adds a Django-based management layer and a custom entrypoint (`cmd/custom/main.go`) that integrates PostgreSQL auth and Redis storage for a containerized deployment.

## Architecture

The codebase has two major parts:

**Go MQTT Broker (upstream comqtt):**
- `mqtt/` - Core MQTT server: packet handling, client management, hooks, listeners (TCP/WS/HTTP), inflight messages
- `cluster/` - Distributed clustering via Gossip (memberlist/serf) and Raft (hashicorp/etcd) for multi-node deployments
- `config/` - YAML-based configuration with constants for storage (memory/bolt/badger/redis), auth (anonymous/username/clientid), auth datasources (redis/mysql/postgresql/http), and bridge (kafka)
- `plugin/` - Auth plugins (redis, mysql, postgresql, http) and bridge plugins (kafka)
- `mqtt/hooks/` - Hook system for auth (`auth/`), storage (`storage/bolt`, `storage/badger`, `storage/redis`), and debug

**Three Go entrypoints in `cmd/`:**
- `cmd/single/main.go` - Standalone broker with configurable storage/auth/bridge
- `cmd/cluster/main.go` - Clustered broker requiring Redis storage + Gossip/Raft
- `cmd/custom/main.go` - **Local customization**: hardcoded PostgreSQL auth against Django's `core_mqttuser`/`core_mqttacl` tables, Redis storage, stdout logging for Docker

**Django Management App (`mqtt_manager`/`core`):**
- `core/models.py` - `MqttUser` (bcrypt passwords) and `MqttAcl` (topic-level read/write/readwrite permissions)
- `core/views.py` - Dashboard that proxies comqtt REST API stats
- `mqtt_manager/settings.py` - PostgreSQL database (`mqtt_db`/`mqtt_user`)

**Container orchestration:**
- `Dockerfile` - Multi-stage: Go build of `cmd/custom/main.go`, then Python image with PostgreSQL 15, Redis, supervisord
- `supervisord.conf` - Runs PostgreSQL, Redis, Django (port 8000), and comqtt (with config file)
- `entrypoint.sh` - Initializes PostgreSQL, runs Django migrations, then starts supervisord

## Build & Run Commands

```bash
# Build Go broker (standalone)
cd cmd && go build -o comqtt ./single/main.go

# Build Go broker (custom/containerized version)
go build -o comqtt cmd/custom/main.go

# Run standalone broker
./comqtt                              # defaults: tcp :1883, ws :1882, http :8080
./comqtt --conf=./cmd/config/single.yml  # with config file

# Run tests (requires docker-compose for mysql/postgres)
go test ./...                         # all tests
go test ./mqtt/...                    # mqtt package tests
go test -run TestFunctionName ./mqtt/ # single test

# Docker
docker build -t comqtt:latest .
docker run -p 1883:1883 -p 8000:8000 -p 8080:8080 comqtt:latest

# Django management
python3 manage.py migrate
python3 manage.py runserver 0.0.0.0:8000
```

## Key Conventions

- Go module path: `github.com/wind-c/comqtt/v2`
- Go version: 1.24 (go.mod), though Dockerfile uses 1.22 and CI uses 1.21
- Hook-based plugin architecture: implement `mqtt.Hook` interface for auth, storage, or bridge extensions
- Config via YAML files in `cmd/config/` or CLI flags
- REST API at `/api/v1/mqtt/...` (single) and `/api/v1/cluster/...` (cluster mode)
- Default ports: 1883 (MQTT TCP), 1882 (WebSocket), 8080 (HTTP/stats), 8000 (Django)
- The custom entrypoint bypasses the config-file-based auth/storage setup and hardcodes PostgreSQL + Redis connection parameters for the container environment
