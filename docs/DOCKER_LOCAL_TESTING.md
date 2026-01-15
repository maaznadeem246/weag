# Docker Local Testing Guide

## Overview

This guide explains how to run the WEAG assessment system with Docker locally for testing.

## Architecture

```
┌─────────────────────┐         ┌─────────────────────┐
│   Host Machine      │         │  Docker Network     │
│                     │         │  (weag-network)     │
│  kickstart_         │─────────▶                     │
│  assessment.py      │         │                     │
│                     │         │                     │
│  Port Mapping:      │         │                     │
│  9009 → Green Agent │         │                     │
│  9010 → Purple Agent│         │                     │
│  8001 → MCP Server  │         │                     │
└─────────────────────┘         │                     │
                                │  ┌──────────────┐   │
                                │  │ Green Agent  │   │
                                │  │ Port: 9009   │   │
                                │  │ (A2A Server) │   │
                                │  │              │   │
                                │  │ ┌──────────┐ │   │
                                │  │ │   MCP    │ │   │
                                │  │ │  Server  │ │   │
                                │  │ │ Port:8001│ │   │
                                │  │ └──────────┘ │   │
                                │  └──────────────┘   │
                                │         │           │
                                │         ▼           │
                                │  ┌──────────────┐   │
                                │  │Purple Agent  │   │
                                │  │Port: 9010    │   │
                                │  │(A2A Client)  │   │
                                │  └──────────────┘   │
                                └─────────────────────┘
```

## Key Points

1. **MCP Server is NOT a separate container** - it runs inside the Green Agent container
2. **Green Agent spawns MCP server** automatically when assessment starts
3. **Purple Agent connects to MCP** via `http://green-agent:8001` (Docker network)
4. **Host machine connects** via `http://localhost:9009` (port mapping)

## Step-by-Step Instructions

### 1. Prerequisites

- Docker and Docker Compose installed
- `.env` file with your API keys

```bash
# .env file
OPENROUTER_API_KEY=your_key_here
LANGFUSE_PUBLIC_KEY=your_langfuse_key  # Optional
LANGFUSE_SECRET_KEY=your_langfuse_secret  # Optional
```

### 2. Build Docker Images

```powershell
# Build both images
docker compose -f docker-compose.local.yml build

# Or build individually
docker build -t weag-green-agent:latest ./green-agent
docker build -t weag-purple-agent:latest ./purple-agent
```

### 3. Start Containers

```powershell
# Start in detached mode
docker compose -f docker-compose.local.yml up -d

# Or start with logs visible
docker compose -f docker-compose.local.yml up
```

Wait for health checks to pass (about 30 seconds).

### 4. Run Assessment from Host

Open a new terminal and run:

```powershell
cd E:\Maaz\Projects\weag
.\.venv\Scripts\Activate.ps1
python kickstart_assessment.py
```

The kickstart script will:
- Detect Docker containers are running
- Skip starting local agent processes
- Send A2A request to `http://localhost:9009`

### 5. Monitor Logs

```powershell
# Follow all logs
docker compose -f docker-compose.local.yml logs -f

# Follow specific service
docker compose -f docker-compose.local.yml logs -f green-agent
docker compose -f docker-compose.local.yml logs -f purple-agent

# View last 100 lines
docker compose -f docker-compose.local.yml logs --tail 100 green-agent
```

### 6. Stop Containers

```powershell
# Stop containers (preserves data)
docker compose -f docker-compose.local.yml stop

# Stop and remove containers
docker compose -f docker-compose.local.yml down

# Stop and remove containers + volumes
docker compose -f docker-compose.local.yml down -v
```

## Troubleshooting

### Health Check Failing

```powershell
# Check if ports are available
netstat -an | findstr ":9009 :9010 :8001"

# Check container logs
docker compose -f docker-compose.local.yml logs green-agent

# Restart containers
docker compose -f docker-compose.local.yml restart
```

### MCP Server Not Accessible

1. **MCP server starts when assessment begins** - not immediately on container start
2. Check Green Agent logs: `docker logs weag-green-agent`
3. Verify port 8001 is exposed: `docker port weag-green-agent`

### Cannot Connect from Kickstart

1. Ensure containers are healthy: `docker ps`
2. Test Green Agent endpoint: `curl http://localhost:9009/health`
3. Check network: `docker network inspect weag-network`

### Rebuilding After Code Changes

```powershell
# Rebuild specific service
docker compose -f docker-compose.local.yml build green-agent

# Rebuild and restart
docker compose -f docker-compose.local.yml up -d --build

# Force rebuild without cache
docker compose -f docker-compose.local.yml build --no-cache
```

## Environment Variables

### Green Agent

| Variable | Description | Example |
|----------|-------------|---------|
| `GREEN_LLM_PROVIDER` | LLM provider | `litellm` |
| `GREEN_LITELLM_MODEL` | Model name | `openrouter/google/gemini-2.5-flash` |
| `GREEN_OPENROUTER_API_KEY` | API key | From `.env` |
| `BROWSER_HEADLESS` | Headless browser | `true` |
| `LANGFUSE_PUBLIC_KEY` | Tracing key (optional) | From `.env` |

### Purple Agent

| Variable | Description | Example |
|----------|-------------|---------|
| `PURPLE_LLM_PROVIDER` | LLM provider | `litellm` |
| `PURPLE_LITELLM_MODEL` | Model name | `openrouter/google/gemini-2.5-flash` |
| `PURPLE_OPENROUTER_API_KEY` | API key | From `.env` |
| `LANGFUSE_PUBLIC_KEY` | Tracing key (optional) | From `.env` |

## Testing with Different Benchmarks

### AssistantBench (requires package)

The Green Agent Dockerfile already includes `browsergym-assistantbench` via the `docker` extras:

```dockerfile
RUN uv sync --locked --extra docker
```

To run only assistantbench:

```powershell
# Edit scenarios/browsergym/scenario-local.toml
# Uncomment only assistantbench benchmark section

python kickstart_assessment.py
```

### MiniWoB (local dataset)

The miniwob dataset is copied into the container during build:

```dockerfile
COPY --chown=agent:agent datasets datasets
```

Ensure `benchmarks/miniwob/html/miniwob/` exists before building.

## Advanced Usage

### Custom Port Configuration

Edit `docker-compose.local.yml` to change ports:

```yaml
ports:
  - "19009:9009"  # Use port 19009 on host
```

Then run kickstart with:
```powershell
python kickstart_assessment.py --green-agent-url http://localhost:19009
```

### Volume Mounting for Development

Add volumes to live-edit code without rebuilding:

```yaml
volumes:
  - ./green-agent/src:/home/agent/src:ro
  - ./green-agent/logs:/home/agent/logs
```

**Note**: Requires container restart to pick up changes.

### Using Docker Desktop

1. Open Docker Desktop
2. Click "Containers" tab
3. Find `weag-green-agent` and `weag-purple-agent`
4. Click container name to view logs
5. Use "Stop" or "Restart" buttons as needed

## Comparison: Local vs Docker

| Aspect | Local (venv) | Docker |
|--------|--------------|--------|
| **Setup** | Activate venv | Build images |
| **Start Time** | ~2 seconds | ~30 seconds |
| **Isolation** | Shared environment | Fully isolated |
| **Debugging** | Direct access | Via logs/exec |
| **MCP Server** | Local process | Container process |
| **Hot Reload** | Immediate | Requires rebuild |
| **Best For** | Development | Testing/CI/CD |

## Next Steps

After successful local Docker testing:

1. Push images to registry: `docker push weag-green-agent:latest`
2. Deploy to cloud (AWS ECS, GCP Cloud Run, etc.)
3. Update URLs in deployment config
4. Run production assessments

## Common Commands Cheat Sheet

```powershell
# Build
docker compose -f docker-compose.local.yml build

# Start
docker compose -f docker-compose.local.yml up -d

# Logs
docker compose -f docker-compose.local.yml logs -f

# Stop
docker compose -f docker-compose.local.yml down

# Restart single service
docker compose -f docker-compose.local.yml restart green-agent

# Shell into container
docker exec -it weag-green-agent bash

# Check health
docker ps
curl http://localhost:9009/health

# Clean up everything
docker compose -f docker-compose.local.yml down -v
docker system prune -a
```
