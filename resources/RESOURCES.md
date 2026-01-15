# BrowserGym Green Agent - Resources Document

## 📚 Overview

This document contains all resources, links, tools, documentation, and references needed for developing the BrowserGym Green Agent for the AgentBeats competition.

---

## 🎯 Project Information

### Project Type
- **Agent Role**: Green Agent (Environment Manager)
- **Benchmark**: BrowserGym (6-in-1 web agent benchmark)
- **Competition Level**: L3
- **Primary Capability**: Web Browsing ✅

### Key Objectives
1. Manage BrowserGym gymnasium environment
2. Expose services for White/Purple Agents
3. Comply with computational efficiency mandates (C, L, F)
4. Deploy with public accessibility
5. Integrate with AgentBeats platform

---

## 📖 Official Documentation

### AgentBeats Platform
- **Main Documentation**: [https://docs.agentbeats.org/](https://docs.agentbeats.org/)
  - Core framework documentation
  - API references
  - Integration guides
  
- **Official Tutorial**: [https://agentbeats.dev/tutorial](https://agentbeats.dev/tutorial)
  - End-to-end getting started guide
  - Local runner and scenarios
  - Green/Purple agent examples
  
- **Competition Overview**: [https://rdi.berkeley.edu/agentx-agentbeats](https://rdi.berkeley.edu/agentx-agentbeats)
  - AgentX and AgentBeats initiative overview
  - Competition structure and rules
  
- **Info Session Slides**: [https://rdi.berkeley.edu/assets/agentbeats-competition-info-session-deck.pdf](https://rdi.berkeley.edu/assets/agentbeats-competition-info-session-deck.pdf)
  - Competition guidelines
  - Technical requirements
  - Submission process

### Educational Resources
- **Agentic AI Learning Portal**: [https://agenticai-learning.org/f25](https://agenticai-learning.org/f25)
  - Fall 2025 curriculum
  - Learning materials
  - Best practices

### Videos
- **AgentBeats Overview / Info Session**: [https://www.youtube.com/watch?v=ZmBnC4xTyRU](https://www.youtube.com/watch?v=ZmBnC4xTyRU)
  - Competition overview and requirements
  - Platform walkthrough and example scenarios

---

## 💻 GitHub Repositories

### Primary Repositories

#### 1. BrowserGym Framework
- **URL**: [https://github.com/ServiceNow/BrowserGym](https://github.com/ServiceNow/BrowserGym)
- **Purpose**: Main benchmark repository
- **Contains**:
  - 6 benchmark implementations
  - Environment interfaces
  - Utilities and tools
  - Example usage

#### 2. AgentBeats Tutorial
- **URL**: [https://github.com/agentbeats/tutorial](https://github.com/agentbeats/tutorial)
- **Purpose**: Official getting started guide
- **Contains**:
  - Setup instructions
  - Example implementations
  - Integration patterns
  - tau2_evaluator.py reference

### Key Files to Review
From `agentbeats-tutorial` repository:
- `tau2_evaluator.py` - Reference implementation for Green Agent structure
- Example assessor/assessee patterns
- MCP integration examples

---

## 🔧 Tools & Technologies

### Core Framework Stack

#### Python Environment Management
- **uv** - Fast Python package installer
  - Installation: `pip install uv`
  - Usage: `uv venv`, `uv pip install`
  
#### Required Python Packages
```
earthshaker          # AgentBeats framework
gymnasium           # RL environment interface
browsergym[all]     # BrowserGym benchmark
playwright          # Browser automation
fastapi             # Web API framework
uvicorn             # ASGI server
python-dotenv       # Environment management
pydantic            # Data validation
psutil              # Resource monitoring
```

### BrowserGym Components

#### Available Benchmarks
1. **MiniWoB** - Mini World of Bits
   - Simple web interaction tasks
   - Quick iteration and testing
   
2. **WebArena** - Realistic web scenarios
   - Complex multi-step tasks
   - E-commerce, forums, etc.
   
3. **VisualWebArena** - Visual-based tasks
   - Image understanding required
   - Visual element interaction
   
4. **WorkArena** - Work-related tasks
   - Office productivity scenarios
   - Enterprise applications
   
5. **AssistantBench** - Assistant evaluation
   - General assistant capabilities
   - Multi-domain tasks
   
6. **WebLINX** - Web interaction tasks
   - Extended web workflows
   - Complex navigation

#### BrowserGym Utilities
- `browsergym.utils.obs.flatten_axtree_to_str` - Compress AXTree (C mandate)
- `browsergym.core.env.BrowserEnv` - Base environment class
- Observation/action interfaces

### Development Tools

#### Browser Automation
- **Playwright** - Browser control
  - Installation: `playwright install`
  - Browsers: Chromium (required for headless mode)
  
#### API Development
- **FastAPI** - Modern web framework
- **Uvicorn** - ASGI server
- **A2A Protocol** - Agent-to-Agent communication

#### Testing & Debugging
- **pytest** - Testing framework
- **OpenAI Agents SDK** - For building OpenAI-powered agents (https://openai.github.io/openai-agents-python/)
- **A2A Inspector** - Agent card testing

---

## 📊 Computational Efficiency Mandates

### Mandate C: Token Cost Minimization

**Objective**: Minimize token usage in communications

**Key Concepts**:
- Token estimation: ~1 token per 4 characters
- AXTree compression using `flatten_axtree_to_str`
- Exclude raw DOM and screenshots by default
- Track cumulative token count

**Reference Formula**:
```
C = Σ(tokens_sent) + Σ(tokens_received)
```

**Tools**:
- `browsergym.utils.obs.flatten_axtree_to_str` - Essential for C optimization
- JSON serialization for size estimation

---

### Mandate L: Latency Minimization

**Objective**: Minimize network round-trip latency

**Key Concepts**:
- Action batching - process multiple actions per network trip
- Internal execution loops
- Fast termination on task completion
- Latency tracking per batch

**Reference Formula**:
```
L = Σ(Δt_network) for all round trips
```

**Implementation Pattern**:
```python
# Record start time
start = time.time()

# Execute batch of actions
for action in action_batch:
    env.step(action)

# Record latency
latency = time.time() - start
```

---

### Mandate F: Compute Footprint Minimization

**Objective**: Minimize resource usage and ensure cleanup

**Key Concepts**:
- Headless browser mode: `gym.make(task_id, headless=True)`
- Guaranteed cleanup with try...finally
- Process verification with psutil
- Resource monitoring

**Required Cleanup**:
```python
try:
    # Environment execution
    env = gym.make(task_id, headless=True)
finally:
    # Guaranteed cleanup
    env.close()
    env.unwrapped.teardown()
```

**Verification**:
- Check for running Chromium/Playwright processes
- Monitor memory usage
- Verify thread termination

---

### Efficiency Penalty Formula

**Final Score Calculation**:
```
Final Score = Task Success × (1 - λ_C × log(C) - λ_L × L)
```

**Default Parameters**:
- λ_C = 0.01 (token penalty coefficient)
- λ_L = 0.1 (latency penalty coefficient)

---

## 🌐 Deployment Resources

### Containerization

Use Docker to package and run the agent reproducibly.

**Docker Commands**:
```bash
# Build image (linux/amd64 recommended)
docker build --platform linux/amd64 -t green-agent:latest .

# Run locally
docker run --rm -p 8000:8000 --env-file .env green-agent:latest

# Tag and push (example: GitHub Container Registry)
docker tag green-agent:latest ghcr.io/USERNAME/green-agent:latest
docker push ghcr.io/USERNAME/green-agent:latest
```

Ensure the image defines an ENTRYPOINT that starts the agent server and accepts `--host`, `--port`, and optionally `--card-url`.

---

### AgentBeats Integration

#### AgentBeats Controller
- **Installation**: `pip install earthshaker`
- **Start Controller**: `agentbeats run_ctrl`

**What You Get**:
- Local management page for monitoring
- Proxy URL for accessing agent
- Agent card endpoint testing
- State management
- Auto-restart capabilities

#### Agent Card Requirements
Must be accessible at: `/.well-known/agent-card.json`

**Required Fields**:
```json
{
  "name": "BrowserGym Green Agent",
  "version": "1.0.0",
  "agent_type": "green_agent",
  "capabilities": ["environment_management", "web_browsing"],
  "benchmarks": ["miniwob", "webarena", ...],
  "mandates": {
    "C_token_optimization": true,
    "L_latency_optimization": true,
    "F_resource_cleanup": true
  }
}
```

---

## 🔍 Helpful Materials & References

### Protocol Documentation
- **A2A Protocol**: [https://a2a-protocol.org/latest/](https://a2a-protocol.org/latest/)
  - Agent-to-Agent communication standard
  - Message formats
  - Integration patterns

### Learning Resources
- **OpenAI Agents SDK Docs** - For OpenAI agent integration (https://openai.github.io/openai-agents-python/)
  - Logging and debugging patterns
  - Agent creation patterns
  
- **MCP (Model Context Protocol)** - Alternative to direct tool use
  - Dynamic service discovery
  - Standardized agent interfaces

### Code Examples

#### From Slides & Tutorials
1. **Kickoff Script Pattern**
   - Send initial message to assessor
   - Include task configuration
   - Specify agent URL/route

2. **Assessor Agent Pattern (OpenAI Agents SDK)**
   ```python
   # Example using OpenAI Agents SDK
   from openai import OpenAI
   
   client = OpenAI()
   
   # Define basic agent behavior (pseudo-interface)
   def assess(input_messages: list[dict]):
     response = client.chat.completions.create(
       model="gpt-4o-mini",
       messages=input_messages,
     )
     return response.choices[0].message.content
   ```

3. **MCP-based Implementation**
   - Different from direct completion interface
   - Requires dynamic discovery
   - Provides as MCP server

---

## 🧪 Testing & Validation

### Testing Tools

#### Local Testing
- **curl** - API endpoint testing
  ```bash
  curl http://localhost:8000/health
  curl http://localhost:8000/.well-known/agent-card.json
  ```

- **pytest** - Unit and integration testing
  ```bash
  pytest tests/ -v
  ```

#### A2A Testing
- **A2A Inspector** - Test RTCP requests and view agent card
- **Proxy URL Testing** - Verify accessibility through AgentBeats

### Validation Checklist
- [ ] Environment creation successful
- [ ] Observation filtering reduces tokens (C mandate)
- [ ] Action batching reduces latency (L mandate)
- [ ] Resources cleaned up properly (F mandate)
- [ ] Agent card accessible
- [ ] Metrics tracking accurate
- [ ] Final score calculation correct

---

## 📝 Configuration Templates

### Environment Variables (.env)
```env
# Efficiency Parameters
LAMBDA_C=0.01
LAMBDA_L=0.1
MAX_STEPS=100

# Server
HOST=0.0.0.0
PORT=8000

# BrowserGym
DEFAULT_BENCHMARK=miniwob
HEADLESS=true

# Logging
LOG_LEVEL=INFO
```

### Requirements File
```txt
earthshaker>=1.0.0
gymnasium>=0.29.0
browsergym[all]>=0.1.0
playwright>=1.40.0
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-dotenv>=1.0.0
pydantic>=2.5.0
psutil>=5.9.0
```

### Procfile (for Cloud Deployment)
```
web: agentbeats run_ctrl
```

---

## 🚨 Troubleshooting Guide

### Common Issues

#### BrowserGym Installation
**Problem**: Cannot find BrowserGym environments
**Solution**:
```bash
cd BrowserGym
pip install -e .
playwright install chromium
playwright install-deps  # Linux only
```

#### Playwright Issues
**Problem**: Browser fails to launch
**Solution**:
- Ensure headless=True for production
- Install system dependencies: `playwright install-deps`
- Check for conflicting Chrome/Chromium installations

#### Resource Cleanup
**Problem**: Chromium processes remain after env.close()
**Solution**:
- Always call `env.unwrapped.teardown()`
- Use `psutil` to verify process termination
- Implement timeout-based force kill if needed

#### Port Conflicts
**Problem**: Port 8000 already in use
**Solution**:
- Change PORT in .env
- Kill existing process: `lsof -ti:8000 | xargs kill`

---

## 📞 Community & Support

### Getting Help

#### Official Channels
- AgentBeats documentation issues
- GitHub repository discussions
- Competition Discord (check official docs for link)

#### Debugging Resources
- OpenAI Agents SDK logging/docs
- AgentBeats controller UI at `http://localhost:PORT`
- BrowserGym GitHub issues

### Feedback & Reporting
- Use thumbs down in AgentBeats UI for feedback
- Report bugs on respective GitHub repositories
- Submit questions to competition organizers

---

## 🎓 Learning Path

### Recommended Study Order

1. **Week 1: Foundation**
   - [ ] Read AgentBeats documentation
   - [ ] Review competition info slides
   - [ ] Study BrowserGym README
   - [ ] Understand the 6 benchmarks

2. **Week 2: Tutorial & Examples**
   - [ ] Work through AgentBeats tutorial
   - [ ] Study tau2_evaluator.py
   - [ ] Review code examples
   - [ ] Test local BrowserGym installation

3. **Week 3: Implementation**
   - [ ] Set up project structure
   - [ ] Implement F mandate (resource management)
   - [ ] Implement C mandate (observation filtering)
   - [ ] Implement L mandate (action batching)

4. **Week 4: Testing & Deployment**
   - [ ] Write unit tests
   - [ ] Test with local AgentBeats controller
   - [ ] Deploy to cloud
   - [ ] Publish to AgentBeats platform

---

## 📋 Quick Reference

### Essential Commands
```bash
# Setup
uv venv
uv pip install -r requirements.txt
playwright install chromium

# Run
agentbeats run_ctrl        # Start controller
./run.sh                   # Start green agent

# Test
pytest tests/ -v
curl http://localhost:8000/health

# Deploy
gcloud builds submit --tag gcr.io/PROJECT/green-agent
gcloud run deploy green-agent --image gcr.io/PROJECT/green-agent
```

### Key URLs
- Docs: https://docs.agentbeats.org/
- Tutorial: https://github.com/agentbeats/tutorial
- BrowserGym: https://github.com/ServiceNow/BrowserGym
- Competition: https://rdi.berkeley.edu/agentx-agentbeats

### Important File Paths
- Agent card: `/.well-known/agent-card.json`
- Config: `config/agent-card.json`
- Main entry: `main.py`
- Green agent: `green_agent/green_executor.py`

---

## ✅ Resources Checklist

### Documentation
- [x] AgentBeats official docs
- [x] BrowserGym repository
- [x] Competition guidelines
- [x] Tutorial repository
- [x] A2A protocol docs

### Tools
- [x] uv (package manager)
- [x] earthshaker (AgentBeats)
- [x] gymnasium (RL interface)
- [x] browsergym (benchmark)
- [x] playwright (browser automation)

### Mandates
- [x] C (Token Cost) - Resources and utilities identified
- [x] L (Latency) - Batching pattern documented
- [x] F (Compute Footprint) - Cleanup requirements defined

### Deployment
- [x] Cloud platforms identified
- [x] AgentBeats controller documented
- [x] Configuration templates provided
- [x] Testing procedures outlined

---

**All resources compiled and ready for implementation! 🚀**

*Last Updated: December 2025*
