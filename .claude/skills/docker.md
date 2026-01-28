# Docker Management Guide

This skill provides guidance for Docker container management, image handling, and Docker Compose operations.

## Quick Reference

### Container Lifecycle

| Action | Command |
|--------|---------|
| List running | `docker ps` |
| List all | `docker ps -a` |
| Start | `docker start <container>` |
| Stop | `docker stop <container>` |
| Restart | `docker restart <container>` |
| Remove | `docker rm <container>` |
| Force remove | `docker rm -f <container>` |
| Logs | `docker logs <container>` |
| Follow logs | `docker logs -f <container>` |
| Shell access | `docker exec -it <container> /bin/bash` |

### Image Management

| Action | Command |
|--------|---------|
| List images | `docker images` |
| Pull image | `docker pull <image>:<tag>` |
| Build image | `docker build -t <name>:<tag> .` |
| Remove image | `docker rmi <image>` |
| Prune unused | `docker image prune` |
| Tag image | `docker tag <source> <target>` |
| Push image | `docker push <image>:<tag>` |

### Docker Compose

| Action | Command |
|--------|---------|
| Start services | `docker compose up -d` |
| Stop services | `docker compose down` |
| Rebuild & start | `docker compose up -d --build` |
| View logs | `docker compose logs` |
| Follow logs | `docker compose logs -f` |
| Service logs | `docker compose logs <service>` |
| List services | `docker compose ps` |
| Execute command | `docker compose exec <service> <cmd>` |
| Pull updates | `docker compose pull` |

## Common Tasks

### View Container Status

```bash
# Running containers with resource usage
docker stats --no-stream

# Detailed container info
docker inspect <container>

# Container processes
docker top <container>
```

### Troubleshooting

```bash
# View last 100 log lines
docker logs --tail 100 <container>

# Logs since timestamp
docker logs --since "2024-01-15T10:00:00" <container>

# Check container health
docker inspect --format='{{.State.Health.Status}}' <container>

# View container events
docker events --filter container=<container>
```

### Cleanup Operations

```bash
# Remove stopped containers
docker container prune

# Remove unused images
docker image prune

# Remove unused volumes
docker volume prune

# Remove all unused resources
docker system prune

# Nuclear option: remove everything
docker system prune -a --volumes
```

### Network Operations

```bash
# List networks
docker network ls

# Inspect network
docker network inspect <network>

# Create network
docker network create <name>

# Connect container to network
docker network connect <network> <container>

# Disconnect from network
docker network disconnect <network> <container>
```

### Volume Operations

```bash
# List volumes
docker volume ls

# Create volume
docker volume create <name>

# Inspect volume
docker volume inspect <name>

# Remove volume
docker volume rm <name>

# Backup volume to tar
docker run --rm -v <volume>:/data -v $(pwd):/backup alpine tar czf /backup/backup.tar.gz -C /data .

# Restore volume from tar
docker run --rm -v <volume>:/data -v $(pwd):/backup alpine tar xzf /backup/backup.tar.gz -C /data
```

## Docker Compose Patterns

### Basic docker-compose.yml Structure

```yaml
version: '3.8'

services:
  app:
    image: myapp:latest
    # Or build from Dockerfile
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8080:80"
    environment:
      - NODE_ENV=production
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - app-logs:/var/log/app
    depends_on:
      - db
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  db:
    image: postgres:15
    volumes:
      - db-data:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password

volumes:
  app-logs:
  db-data:

secrets:
  db_password:
    file: ./secrets/db_password.txt

networks:
  default:
    driver: bridge
```

### Environment Variables

```bash
# Pass env file
docker compose --env-file .env.production up -d

# Override with env var
DB_PASSWORD=secret docker compose up -d
```

### Multiple Compose Files

```bash
# Development (base + dev overrides)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Production
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Dockerfile Best Practices

### Multi-stage Build

```dockerfile
# Build stage
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage
FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
EXPOSE 3000
USER node
CMD ["node", "dist/index.js"]
```

### Python Application

```dockerfile
FROM python:3.12-slim

# Prevent Python from writing bytecode and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run as non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0"]
```

### Key Principles

1. **Use specific base image tags** (not `latest`)
2. **Multi-stage builds** to minimize final image size
3. **Order layers by change frequency** (dependencies before code)
4. **Run as non-root user** for security
5. **Use `.dockerignore`** to exclude unnecessary files
6. **Combine RUN commands** to reduce layers

### .dockerignore Example

```
.git
.gitignore
.env*
*.md
__pycache__
*.pyc
node_modules
.npm
.cache
tests/
docs/
*.log
.DS_Store
```

## Registry Operations

### Docker Hub

```bash
# Login
docker login

# Push image
docker tag myapp:latest username/myapp:latest
docker push username/myapp:latest
```

### GitHub Container Registry (GHCR)

```bash
# Login with PAT
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Tag and push
docker tag myapp:latest ghcr.io/username/myapp:latest
docker push ghcr.io/username/myapp:latest
```

### Private Registry

```bash
# Login
docker login registry.example.com

# Pull/Push
docker pull registry.example.com/myapp:latest
docker push registry.example.com/myapp:latest
```

## Resource Limits

### In docker run

```bash
docker run -d \
  --memory="512m" \
  --memory-swap="1g" \
  --cpus="1.5" \
  --cpu-shares=1024 \
  myapp:latest
```

### In docker-compose.yml

```yaml
services:
  app:
    image: myapp:latest
    deploy:
      resources:
        limits:
          cpus: '1.5'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M
```

## Health Checks

### In Dockerfile

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1
```

### In docker-compose.yml

```yaml
services:
  app:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      start_period: 5s
      retries: 3
```

### Check Health Status

```bash
# View health status
docker inspect --format='{{json .State.Health}}' <container> | jq

# Filter by health
docker ps --filter health=healthy
docker ps --filter health=unhealthy
```

## Debugging Containers

### Access Running Container

```bash
# Bash shell
docker exec -it <container> /bin/bash

# Shell (for Alpine)
docker exec -it <container> /bin/sh

# Run specific command
docker exec <container> cat /etc/hosts
```

### Debug Stopped Container

```bash
# Start with shell override
docker run -it --entrypoint /bin/sh myapp:latest

# Copy files from stopped container
docker cp <container>:/path/to/file ./local-file
```

### View Container Details

```bash
# Full inspection
docker inspect <container>

# Specific fields
docker inspect --format='{{.NetworkSettings.IPAddress}}' <container>
docker inspect --format='{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}' <container>
```

## Security Best Practices

### Run as Non-Root

```dockerfile
# Create user in Dockerfile
RUN addgroup -g 1000 appgroup && \
    adduser -u 1000 -G appgroup -s /bin/sh -D appuser
USER appuser
```

### Read-Only Filesystem

```bash
docker run --read-only --tmpfs /tmp myapp:latest
```

### Drop Capabilities

```bash
docker run --cap-drop ALL --cap-add NET_BIND_SERVICE myapp:latest
```

### Security Scanning

```bash
# Scan image for vulnerabilities
docker scout cves myapp:latest

# Or use Trivy
trivy image myapp:latest
```

## Common Issues & Solutions

### Container Exits Immediately

```bash
# Check exit code and logs
docker ps -a  # Check STATUS column
docker logs <container>

# Run interactively to debug
docker run -it myapp:latest /bin/sh
```

### Port Already in Use

```bash
# Find what's using the port
sudo lsof -i :8080
# Or
sudo ss -tlnp | grep 8080

# Kill the process or use different port
docker run -p 8081:80 myapp:latest
```

### Out of Disk Space

```bash
# Check Docker disk usage
docker system df

# Clean up
docker system prune -a --volumes
```

### Permission Denied on Volumes

```bash
# Fix ownership
docker exec <container> chown -R 1000:1000 /data

# Or mount with user mapping
docker run -v ./data:/data:z --user $(id -u):$(id -g) myapp:latest
```

### Network Connectivity Issues

```bash
# Check container can reach internet
docker exec <container> ping -c 3 8.8.8.8

# Check DNS resolution
docker exec <container> nslookup google.com

# Restart Docker networking
sudo systemctl restart docker
```

## AIOS Integration

When using AIOS to manage Docker:

1. **Use `run_command`** for basic Docker commands
2. **Use `manage_service`** for Docker daemon control
3. **Use `view_logs`** for Docker daemon logs (unit:docker)
4. **Use long_running=true** for operations like builds and pulls

### Example AIOS Requests

- "List all running Docker containers"
- "Show logs for the nginx container"
- "Restart the docker compose stack"
- "Build and start containers with docker compose"
- "Check disk space used by Docker"
- "Remove all stopped containers and unused images"
