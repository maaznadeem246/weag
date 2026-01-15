# Docker Deployment Guide

This guide explains how to deploy Green Agent and Purple Agent in different scenarios.

## Deployment Scenarios

### 1. Local Testing (Both Agents Together)
Use `docker-compose.local.yml` - already configured.

```bash
docker compose -f docker-compose.local.yml up
```

### 2. Competition/Production (Separate Deployment)

When submitting agents separately, each agent runs in its own environment and needs proper configuration.

---

## Green Agent Standalone Deployment

### Option A: Using Environment Variables (Recommended)

```bash
# Build image
docker build -t my-green-agent ./green-agent

# Run with environment variables
docker run -d \
  -p 9009:9009 \
  -p 8001:8001 \
  -e AGENT_CARD_URL="https://my-green-agent.example.com/" \
  -e MCP_EXTERNAL_URL="https://my-green-agent.example.com:8001/mcp" \
  -e OPENROUTER_API_KEY="your-key-here" \
  -e BROWSER_HEADLESS="true" \
  my-green-agent
```

### Option B: Using Command Line Arguments

```bash
# Build image
docker build -t my-green-agent ./green-agent

# Run with CLI args
docker run -d \
  -p 9009:9009 \
  -p 8001:8001 \
  -e OPENROUTER_API_KEY="your-key-here" \
  -e BROWSER_HEADLESS="true" \
  my-green-agent \
  --host 0.0.0.0 \
  --port 9009 \
  --card-url "https://my-green-agent.example.com/" \
  --mcp-url "https://my-green-agent.example.com:8001/mcp"
```

### Green Agent Configuration Reference

| Variable | CLI Argument | Purpose | Example |
|----------|-------------|---------|---------|
| `AGENT_CARD_URL` | `--card-url` | External URL for agent card discovery | `https://green-agent.com/` |
| `MCP_EXTERNAL_URL` | `--mcp-url` | MCP server URL for Purple Agent connections | `https://green-agent.com:8001/mcp` |
| `OPENROUTER_API_KEY` | N/A | LLM API key (required) | `sk-or-v1-...` |
| `BROWSER_HEADLESS` | `--headless` | Run browser in headless mode | `true` or `false` |

**Priority**: CLI argument > Environment variable > Default

---

## Purple Agent Standalone Deployment

### Option A: Using Environment Variables (Recommended)

```bash
# Build image
docker build -t my-purple-agent ./purple-agent

# Run with environment variables
docker run -d \
  -p 9010:9010 \
  -e AGENT_CARD_URL="https://my-purple-agent.example.com/" \
  -e OPENROUTER_API_KEY="your-key-here" \
  my-purple-agent
```

### Option B: Using Command Line Arguments

```bash
# Build image
docker build -t my-purple-agent ./purple-agent

# Run with CLI args
docker run -d \
  -p 9010:9010 \
  -e OPENROUTER_API_KEY="your-key-here" \
  my-purple-agent \
  --host 0.0.0.0 \
  --port 9010 \
  --card-url "https://my-purple-agent.example.com/"
```

### Purple Agent Configuration Reference

| Variable | CLI Argument | Purpose | Example |
|----------|-------------|---------|---------|
| `AGENT_CARD_URL` | `--card-url` | External URL for agent card discovery | `https://purple-agent.com/` |
| `OPENROUTER_API_KEY` | N/A | LLM API key (required) | `sk-or-v1-...` |

**Priority**: CLI argument > Environment variable > Default

---

## Cloud Deployment Examples

### AWS ECS

**Green Agent Task Definition:**
```json
{
  "containerDefinitions": [{
    "name": "green-agent",
    "image": "your-repo/green-agent:latest",
    "portMappings": [
      {"containerPort": 9009},
      {"containerPort": 8001}
    ],
    "environment": [
      {"name": "AGENT_CARD_URL", "value": "https://green.example.com/"},
      {"name": "MCP_EXTERNAL_URL", "value": "https://green.example.com:8001/mcp"},
      {"name": "BROWSER_HEADLESS", "value": "true"}
    ],
    "secrets": [
      {"name": "OPENROUTER_API_KEY", "valueFrom": "arn:aws:secretsmanager:..."}
    ]
  }]
}
```

**Purple Agent Task Definition:**
```json
{
  "containerDefinitions": [{
    "name": "purple-agent",
    "image": "your-repo/purple-agent:latest",
    "portMappings": [
      {"containerPort": 9010}
    ],
    "environment": [
      {"name": "AGENT_CARD_URL", "value": "https://purple.example.com/"}
    ],
    "secrets": [
      {"name": "OPENROUTER_API_KEY", "valueFrom": "arn:aws:secretsmanager:..."}
    ]
  }]
}
```

### Kubernetes

**Green Agent Deployment:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: green-agent
spec:
  template:
    spec:
      containers:
      - name: green-agent
        image: your-repo/green-agent:latest
        ports:
        - containerPort: 9009
        - containerPort: 8001
        env:
        - name: AGENT_CARD_URL
          value: "https://green.example.com/"
        - name: MCP_EXTERNAL_URL
          value: "https://green.example.com:8001/mcp"
        - name: BROWSER_HEADLESS
          value: "true"
        - name: OPENROUTER_API_KEY
          valueFrom:
            secretKeyRef:
              name: api-keys
              key: openrouter
```

**Purple Agent Deployment:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: purple-agent
spec:
  template:
    spec:
      containers:
      - name: purple-agent
        image: your-repo/purple-agent:latest
        ports:
        - containerPort: 9010
        env:
        - name: AGENT_CARD_URL
          value: "https://purple.example.com/"
        - name: OPENROUTER_API_KEY
          valueFrom:
            secretKeyRef:
              name: api-keys
              key: openrouter
```

---

## Important Notes

### MCP URL Configuration (Green Agent Only)

**Why it matters:**
- Purple Agent needs to connect to Green Agent's MCP server
- In Docker networking, `localhost` doesn't work between containers
- The MCP URL must be reachable from Purple Agent's network

**Local Testing (docker-compose):**
```bash
--mcp-url "http://green-agent:8001/mcp"  # Uses Docker network name
```

**Production (separate hosts):**
```bash
--mcp-url "https://green-agent.example.com:8001/mcp"  # Uses public URL
```

### Agent Card URL

**Why it matters:**
- Required for A2A agent discovery protocol
- Must be the public/accessible URL, not internal Docker names

**When to set:**
- ✅ Always set for production deployments
- ✅ Set in docker-compose for multi-container testing
- ❌ Not needed for local development (defaults to localhost)

### Security Considerations

1. **Never hardcode API keys** - use environment variables or secrets management
2. **Use HTTPS in production** - especially for MCP server (sensitive browser data)
3. **Validate agent cards** - ensure Purple Agent only connects to trusted Green Agents
4. **Network isolation** - use firewalls/security groups to limit access

---

## Testing Deployment

### Verify Green Agent

```bash
# Health check
curl http://your-green-agent:9009/health

# Agent card
curl http://your-green-agent:9009/.well-known/agent-card.json

# MCP server (should be reachable)
curl http://your-green-agent:8001/
```

### Verify Purple Agent

```bash
# Health check
curl http://your-purple-agent:9010/health

# Agent card
curl http://your-purple-agent:9010/.well-known/agent-card.json
```

### End-to-End Test

Use the kickstart script to test the complete flow:

```bash
python kickstart_assessment.py \
  --green-agent-url http://your-green-agent:9009 \
  --purple-agent-url http://your-purple-agent:9010 \
  --task miniwob.click-test
```

---

## Troubleshooting

### Purple Agent can't connect to MCP server

**Symptom:** `McpError: Connection closed`

**Solution:**
1. Verify `--mcp-url` is set correctly in Green Agent
2. Ensure port 8001 is accessible from Purple Agent's network
3. Check firewall rules allow Purple → Green on port 8001

### Agent card not found

**Symptom:** `404 Not Found` on `/.well-known/agent-card.json`

**Solution:**
1. Verify `--card-url` matches the actual external URL
2. Ensure agent is fully started (check health endpoint)
3. Verify DNS/load balancer routing

### API key errors

**Symptom:** `Authentication failed` or `Invalid API key`

**Solution:**
1. Set `OPENROUTER_API_KEY` environment variable
2. Verify API key is valid and has sufficient credits
3. Check logs for detailed error messages
