# BrowserGym Green Agent - Research & Implementation Plan

## 📋 Executive Summary

This document outlines the complete research analysis and implementation plan for developing a BrowserGym Green Agent that manages the gymnasium environment while achieving optimal computational efficiency through the C, L, and F mandates.

---

## 🔬 Part 1: Research & Analysis

### 1.1 Problem Statement

**Objective**: Build a Green Agent that:
1. Manages BrowserGym environment for web agent evaluation
2. Exposes services for White/Purple Agent interaction
3. Minimizes computational costs (tokens, latency, resources)
4. Integrates with AgentBeats platform
5. Achieves high task success with efficiency optimization

**Challenges Identified**:
- Cross-agent tool use standardization
- Observation data size management
- Network round-trip latency
- Resource cleanup guarantees
- Protocol translation complexity

---

### 1.2 Architecture Analysis

#### Green Agent Role in System

```
┌─────────────────────────────────────────────────────┐
│                 AgentBeats Platform                  │
└─────────────────────────────────────────────────────┘
                         │
                         │ A2A Protocol
                         ▼
┌─────────────────────────────────────────────────────┐
│              Green Agent (Environment Manager)       │
│  ┌──────────────────────────────────────────────┐  │
│  │  • Observation Filtering (C)                 │  │
│  │  • Action Batching (L)                       │  │
│  │  • Resource Management (F)                   │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                         │
                         │ Gymnasium API
                         ▼
┌─────────────────────────────────────────────────────┐
│              BrowserGym Environment                  │
│  ┌──────────────────────────────────────────────┐  │
│  │  MiniWoB | WebArena | VisualWebArena         │  │
│  │  WorkArena | AssistantBench | WebLINX        │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                         │
                         │ Playwright
                         ▼
              ┌─────────────────┐
              │  Chromium       │
              │  (Headless)     │
              └─────────────────┘
```

#### Data Flow Architecture

```
Purple Agent                  Green Agent                 BrowserGym
    │                             │                           │
    │ 1. Request batch           │                           │
    │   of actions               │                           │
    ├───────────────────────────>│                           │
    │                             │ 2. For each action:       │
    │                             ├──────────────────────────>│
    │                             │   env.step(action)        │
    │                             │                           │
    │                             │<──────────────────────────┤
    │                             │   raw_observation         │
    │                             │                           │
    │                             │ 3. Filter observation (C) │
    │                             │    - Extract AXTree       │
    │                             │    - Remove DOM/screenshot│
    │                             │    - Keep essential data  │
    │                             │                           │
    │ 4. Send filtered batch     │                           │
    │    observations            │                           │
    │<───────────────────────────┤                           │
    │                             │                           │
```

---

### 1.3 Computational Efficiency Research

#### Mandate C: Token Cost Analysis

**Research Findings**:

1. **Typical BrowserGym Observation Size**:
   - Raw observation: ~50,000-100,000 characters
   - AXTree alone: ~20,000-40,000 characters
   - Full DOM: ~30,000-60,000 characters
   - Screenshot (base64): ~100,000+ characters

2. **Token Conversion**:
   - Approximate ratio: 1 token ≈ 4 characters
   - Raw observation: ~12,500-25,000 tokens per step
   - Filtered observation: ~2,000-5,000 tokens per step
   - **Reduction**: 60-80% token savings

3. **Key Optimization Strategies**:
   - Use `flatten_axtree_to_str` utility
   - Extract only interactive elements (bids)
   - Remove decorative/structural elements
   - Exclude metadata unless needed
   - Conditional inclusion of high-cost data

**Target**: < 5,000 tokens per observation

---

#### Mandate L: Latency Analysis

**Research Findings**:

1. **Network Round-Trip Costs**:
   - Typical A2A round-trip: 50-200ms (local)
   - Cloud round-trip: 100-500ms
   - Per-action latency (without batching): cumulative
   - Example: 20 actions × 150ms = 3 seconds total

2. **Batching Benefits**:
   - Single batch of 5 actions: 1 round-trip
   - Without batching: 5 round-trips
   - **Latency reduction**: 80% (5 actions example)

3. **Implementation Strategy**:
   - Accept action lists from Purple Agent
   - Execute all actions in internal loop
   - Single response with batch results
   - Early termination on task completion

**Target**: < 2 seconds total latency for typical task

---

#### Mandate F: Compute Footprint Analysis

**Research Findings**:

1. **Resource Consumption**:
   - Chromium process: ~200-400 MB RAM
   - Playwright overhead: ~50-100 MB RAM
   - Headless vs. headed: ~50% memory reduction
   - Process cleanup critical for long-running systems

2. **Common Issues**:
   - Zombie Chromium processes
   - Memory leaks from improper cleanup
   - Thread accumulation
   - File descriptor leaks

3. **Cleanup Requirements**:
   - `env.close()` - Closes connections
   - `env.unwrapped.teardown()` - Terminates browser
   - Process verification with psutil
   - Timeout-based force termination if needed

**Target**: 0 orphaned processes, < 500 MB peak memory

---

### 1.4 Interface Design Research

#### Challenge 1: Cross-Agent Tool Use

**Problem**: How should Purple Agent specify actions?

**Options Analyzed**:

1. **Direct Gymnasium String Format**
   - Example: `"click('123')"`
   - Pros: No translation needed
   - Cons: Purple Agent must know BrowserGym syntax

2. **Structured JSON Format** ⭐ (Recommended)
   - Example: `{"action_type": "click", "bid": "123"}`
   - Pros: Agent-friendly, standardized, extensible
   - Cons: Requires translation layer

3. **MCP Protocol**
   - Example: Tool call with parameters
   - Pros: Standardized across agents
   - Cons: Requires dynamic discovery, complex setup

**Decision**: Structured JSON with translation layer
- Best balance of simplicity and flexibility
- Allows Purple Agent to use natural action format
- Green Agent handles BrowserGym specifics

---

#### Challenge 2: Observation Representation

**Problem**: What should be sent to Purple Agent?

**Research Results**:

| Component | Size (chars) | Tokens | Include? |
|-----------|--------------|--------|----------|
| AXTree (filtered) | 8,000 | 2,000 | ✅ Always |
| URL | 100 | 25 | ✅ Always |
| Goal | 200 | 50 | ✅ Always |
| Last Action | 100 | 25 | ✅ Always |
| Full DOM | 40,000 | 10,000 | ❌ Rarely |
| Screenshot | 120,000 | 30,000 | ❌ Rarely |
| Raw AXTree | 30,000 | 7,500 | ❌ Never |

**Decision**: Filtered AXTree + Essential Metadata
- Provides sufficient context for action selection
- Reduces token usage by 70-80%
- Can include DOM/screenshot on failure for debugging

---

### 1.5 Technology Stack Research

#### Core Technologies

**1. AgentBeats Framework**
- **Version**: Latest from PyPI (earthshaker)
- **Purpose**: Agent orchestration and A2A protocol
- **Key Classes**: `GreenExecutor`, task management
- **Decision**: Use as base class for Green Agent

**2. BrowserGym**
- **Version**: Latest from GitHub
- **Purpose**: Benchmark environments
- **Installation**: Clone + `pip install -e .`
- **Decision**: Use MiniWoB for development, all benchmarks in production

**3. Gymnasium**
- **Version**: >= 0.29.0
- **Purpose**: RL environment interface
- **API**: `make()`, `reset()`, `step()`, `close()`
- **Decision**: Standard interface for environment interaction

**4. Playwright**
- **Version**: >= 1.40.0
- **Purpose**: Browser automation
- **Mode**: Headless for F mandate
- **Decision**: Required by BrowserGym, use headless mode

**5. FastAPI + Uvicorn**
- **Purpose**: HTTP API for potential extensions
- **Decision**: Optional, use if building standalone API

---

## 🛠️ Part 2: Implementation Plan

### Phase 1: Foundation (Steps 1-3)

#### Step 1: Environment Setup

**Tasks**:
1. Install uv and create virtual environment
2. Install all dependencies
3. Verify BrowserGym installation
4. Test basic environment creation

**Commands**:
```bash
# Setup
uv venv
source .venv/bin/activate
uv pip install gymnasium browsergym[all] playwright earthshaker

# Verify
python -c "import gymnasium; import browsergym; print('✅ OK')"
playwright install chromium
```

**Deliverable**: Working Python environment with all dependencies

**Success Criteria**:
- [ ] All imports work
- [ ] Can create BrowserGym environment
- [ ] Playwright browser launches

---

#### Step 2: Project Structure

**Tasks**:
1. Create directory structure
2. Set up configuration files
3. Initialize Git repository
4. Create base classes

**Directory Structure**:
```
browsergym-green-agent/
├── .env
├── .gitignore
├── main.py
├── run.sh
├── requirements.txt
├── config/
│   └── agent-card.json
├── green_agent/
│   ├── __init__.py
│   ├── green_executor.py
│   ├── observation_filter.py
│   ├── action_executor.py
│   ├── metrics_tracker.py
│   └── resource_manager.py
└── tests/
    ├── __init__.py
    ├── test_observation_filter.py
    ├── test_action_executor.py
    └── test_integration.py
```

**Deliverable**: Complete project structure with placeholders

---

#### Step 3: Base Green Agent Class

**Tasks**:
1. Implement `BrowserGymGreenAgent` class
2. Add initialization logic
3. Implement try...finally for cleanup (F mandate)
4. Add basic logging

**Code Milestone**:
```python
class BrowserGymGreenAgent(GreenExecutor):
    def __init__(self, config):
        super().__init__(config)
        self.env = None
        self.metrics_tracker = MetricsTracker()
    
    async def handle_assessment(self, task_config):
        try:
            await self._initialize_environment(task_config)
            result = await self._execute_task(task_config)
            return result
        finally:
            await self._cleanup_resources()
```

**Deliverable**: Working base class with F mandate compliance

**Success Criteria**:
- [ ] Class inherits from GreenExecutor
- [ ] Cleanup guaranteed in finally block
- [ ] Logging functional

---

### Phase 2: Observation Filtering (Steps 4-6)

#### Step 4: Filter Implementation (C Mandate)

**Tasks**:
1. Create `ObservationFilter` class
2. Implement AXTree extraction
3. Add token estimation
4. Test with sample observations

**Code Milestone**:
```python
class ObservationFilter:
    @staticmethod
    def filter_observation(raw_obs):
        filtered = {}
        
        # Extract essential AXTree
        filtered['axtree'] = flatten_axtree_to_str(
            raw_obs.get('axtree_object')
        )
        
        # Add metadata
        filtered['url'] = raw_obs.get('url')
        filtered['goal'] = raw_obs.get('goal')
        
        return filtered
```

**Deliverable**: Functioning observation filter

**Success Criteria**:
- [ ] Reduces observation size by 70%+
- [ ] Preserves actionable information
- [ ] Token estimation accurate

---

#### Step 5: Integration & Testing

**Tasks**:
1. Integrate filter into Green Agent
2. Add token counting
3. Write unit tests
4. Test with real BrowserGym tasks

**Test Cases**:
```python
def test_token_reduction():
    raw_obs = create_large_observation()
    filtered = filter_observation(raw_obs)
    
    assert estimate_tokens(filtered) < estimate_tokens(raw_obs) * 0.3
```

**Deliverable**: Tested and integrated filter

---

#### Step 6: Optimization

**Tasks**:
1. Profile filter performance
2. Optimize AXTree extraction
3. Add conditional high-cost data inclusion
4. Document C mandate compliance

**Deliverable**: Optimized filter with < 5,000 tokens/observation

---

### Phase 3: Action Batching (Steps 7-9)

#### Step 7: Action Executor (L Mandate)

**Tasks**:
1. Create `ActionExecutor` class
2. Implement batch execution loop
3. Add action translation
4. Implement latency tracking

**Code Milestone**:
```python
class ActionExecutor:
    def execute_batch(self, actions):
        start_time = time.time()
        results = []
        
        for action in actions:
            gym_action = self._translate_action(action)
            obs, reward, term, trunc, info = self.env.step(gym_action)
            results.append({...})
            
            if term or trunc:
                break
        
        latency = time.time() - start_time
        return results, latency
```

**Deliverable**: Working action executor with batching

**Success Criteria**:
- [ ] Processes action lists
- [ ] Tracks latency per batch
- [ ] Terminates early on completion

---

#### Step 8: Action Translation

**Tasks**:
1. Implement JSON to Gymnasium translation
2. Support all action types
3. Add error handling
4. Test with various action formats

**Action Types to Support**:
- click(bid)
- fill(bid, text)
- goto(url)
- scroll(direction)
- press(key)

**Deliverable**: Complete action translation layer

---

#### Step 9: Integration & Optimization

**Tasks**:
1. Integrate executor into Green Agent
2. Test batch processing
3. Measure latency reduction
4. Document L mandate compliance

**Target Metrics**:
- Latency reduction: > 70% (vs. per-action)
- Batch size: 3-10 actions typical
- Total latency: < 2 seconds

**Deliverable**: Integrated and tested action batching

---

### Phase 4: Metrics & Scoring (Steps 10-12)

#### Step 10: Metrics Tracker

**Tasks**:
1. Create `MetricsTracker` class
2. Implement C, L, F tracking
3. Add efficiency penalty calculation
4. Test penalty formula

**Code Milestone**:
```python
class MetricsTracker:
    def calculate_final_score(self, task_success):
        token_penalty = self.lambda_c * math.log(self.token_count)
        latency_penalty = self.lambda_l * self.latency_total
        
        efficiency = max(0, 1 - token_penalty - latency_penalty)
        return task_success * efficiency
```

**Deliverable**: Functioning metrics tracker

---

#### Step 11: Resource Manager (F Mandate)

**Tasks**:
1. Create `ResourceManager` class
2. Implement resource monitoring
3. Add cleanup verification
4. Test with psutil

**Features**:
- Memory usage tracking
- Process verification
- Cleanup validation
- Resource reporting

**Deliverable**: Complete resource management

---

#### Step 12: Final Integration

**Tasks**:
1. Integrate all components
2. Implement `_generate_final_score()`
3. Create artifact payload
4. End-to-end testing

**Deliverable**: Complete scoring system

---

### Phase 5: Testing & Validation (Steps 13-15)

#### Step 13: Unit Tests

**Tasks**:
1. Write tests for each component
2. Test edge cases
3. Achieve > 80% code coverage
4. Fix identified bugs

**Test Categories**:
- Observation filtering
- Action execution
- Metrics tracking
- Resource cleanup

**Deliverable**: Comprehensive unit test suite

---

#### Step 14: Integration Tests

**Tasks**:
1. Test with real BrowserGym tasks
2. Verify C, L, F compliance
3. Test with MiniWoB benchmark
4. Measure efficiency metrics

**Test Scenarios**:
- Simple click task
- Multi-step form filling
- Navigation task
- Error handling

**Deliverable**: Passing integration tests

---

#### Step 15: Performance Testing

**Tasks**:
1. Run multiple tasks in sequence
2. Measure resource usage
3. Verify no memory leaks
4. Test cleanup reliability

**Metrics to Verify**:
- Token count < 5,000 per obs
- Latency < 2s total
- Memory < 500 MB peak
- 0 orphaned processes

**Deliverable**: Performance benchmarks

---

### Phase 6: AgentBeats Integration (Steps 16-18)

#### Step 16: Agent Card & Controller

**Tasks**:
1. Create agent-card.json
2. Test with AgentBeats controller
3. Verify endpoint accessibility
4. Test proxy URL

**Commands**:
```bash
agentbeats run_ctrl
curl http://localhost:8000/.well-known/agent-card.json
```

**Deliverable**: Working AgentBeats integration

---

#### Step 17: A2A Protocol Testing

**Tasks**:
1. Test A2A message format
2. Verify Purple Agent communication
3. Test action batch requests
4. Debug integration issues

**Test Tools**:
- A2A Inspector
- curl commands
- AgentBeats UI

**Deliverable**: Verified A2A communication

---

#### Step 18: Local End-to-End Test

**Tasks**:
1. Run complete assessment flow
2. Test with sample Purple Agent
3. Verify metrics reporting
4. Review final scores

**Deliverable**: Working end-to-end system

---

### Phase 7: Deployment (Steps 19-21)

#### Step 19: Deployment Preparation

**Tasks**:
1. Create Procfile
2. Generate requirements.txt
3. Configure environment variables
4. Test locally with production settings

**Files to Create**:
- Procfile
- .env.production
- Deployment documentation

**Deliverable**: Deployment-ready codebase

---

#### Step 20: Container Deployment

**Tasks**:
1. Build container image
2. Deploy to Google Cloud Run
3. Configure networking
4. Set up HTTPS

**Commands**:
```bash
gcloud builds submit --tag gcr.io/PROJECT/green-agent
gcloud run deploy green-agent \
  --image gcr.io/PROJECT/green-agent \
  --allow-unauthenticated
```

**Deliverable**: Publicly accessible Green Agent

---

#### Step 21: Publishing

**Tasks**:
1. Verify public accessibility
2. Test agent card endpoint
3. Submit to AgentBeats platform
4. Monitor initial usage

**Deliverable**: Published agent on AgentBeats

---

### Phase 8: Optimization & Documentation (Steps 22-25)

#### Step 22-23: Performance Optimization

**Tasks**:
1. Profile slow operations
2. Optimize hot paths
3. Reduce token usage further
4. Improve latency

**Target Improvements**:
- 10% token reduction
- 20% latency reduction
- Better error handling

**Deliverable**: Optimized agent

---

#### Step 24-25: Documentation

**Tasks**:
1. Complete API documentation
2. Write usage guide
3. Document mandate compliance
4. Create troubleshooting guide

**Documents to Create**:
- API.md
- USAGE.md
- COMPLIANCE.md
- TROUBLESHOOTING.md

**Deliverable**: Complete documentation

---

## 📊 Part 3: Success Metrics & Evaluation

### 3.1 Mandate Compliance Metrics

#### C Mandate (Token Cost)
- **Target**: < 5,000 tokens per observation
- **Measurement**: `len(json.dumps(obs)) // 4`
- **Success Criteria**: 70%+ reduction from raw observation

#### L Mandate (Latency)
- **Target**: < 2 seconds total for typical task
- **Measurement**: Sum of all `time.time()` deltas
- **Success Criteria**: 70%+ reduction vs. non-batched

#### F Mandate (Compute Footprint)
- **Target**: 0 orphaned processes, < 500 MB RAM
- **Measurement**: `psutil` monitoring
- **Success Criteria**: 100% cleanup success rate

---

### 3.2 Task Success Metrics

**Benchmark Targets**:
- MiniWoB: > 60% task success
- WebArena: > 40% task success
- VisualWebArena: > 35% task success

**Efficiency Score**:
- Final Score > 0.7 after penalties
- Shows benefit of efficiency optimization

---

### 3.3 System Reliability Metrics

- **Uptime**: > 99%
- **Error Rate**: < 1%
- **Response Time**: < 500ms (non-task)
- **Resource Leaks**: 0

---

## 🔄 Part 4: Iteration & Improvement Strategy

### Week 1-3: Initial Implementation
Focus on core functionality and mandate compliance

### Week 4-6: Testing & Refinement
Thorough testing and bug fixes

### Week 7-8: Optimization
Performance tuning and efficiency improvements

### Week 9-10: Deployment & Monitoring
Cloud deployment and real-world testing

### Ongoing: Maintenance
Bug fixes, updates, and improvements based on feedback

---

## 📝 Part 5: Risk Analysis & Mitigation

### Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| BrowserGym installation issues | Medium | High | Document setup thoroughly, test on multiple platforms |
| Resource cleanup failures | Medium | High | Comprehensive testing, timeout-based force kill |
| Observation filtering too aggressive | Low | Medium | Keep essential data, add fallback to raw obs |
| Latency target not met | Low | Medium | Optimize batch processing, reduce overhead |
| Integration with AgentBeats fails | Low | High | Early testing, follow tutorial closely |

### Operational Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Cloud deployment costs | Low | Medium | Use free tier, monitor usage |
| Agent becomes unreachable | Low | High | Health checks, monitoring, auto-restart |
| Memory leaks in production | Medium | High | Resource monitoring, periodic restarts |
| Incompatible updates | Low | Medium | Pin dependency versions |

---

## ✅ Part 6: Completion Checklist

### Implementation Checklist

**Foundation**:
- [ ] Environment setup complete
- [ ] Project structure created
- [ ] Base class implemented
- [ ] F mandate compliance (try...finally)

**Observation Filtering (C Mandate)**:
- [ ] Filter class implemented
- [ ] AXTree extraction working
- [ ] Token counting accurate
- [ ] 70%+ token reduction achieved

**Action Batching (L Mandate)**:
- [ ] Executor class implemented
- [ ] Batch processing working
- [ ] Action translation complete
- [ ] 70%+ latency reduction achieved

**Metrics & Scoring**:
- [ ] Metrics tracker implemented
- [ ] Resource manager working
- [ ] Efficiency penalty calculation correct
- [ ] Artifact generation complete

**Testing**:
- [ ] Unit tests passing (>80% coverage)
- [ ] Integration tests passing
- [ ] Performance targets met
- [ ] No resource leaks

**Deployment**:
- [ ] AgentBeats integration complete
- [ ] Cloud deployment successful
- [ ] Agent card accessible
- [ ] Published on platform

**Documentation**:
- [ ] Code documented
- [ ] API docs complete
- [ ] Usage guide written
- [ ] Compliance verified

---

## 🎯 Final Goals

1. **Functional Green Agent**: Manages BrowserGym environment successfully
2. **Efficiency Optimized**: Meets all C, L, F mandate targets
3. **Platform Integrated**: Works with AgentBeats platform
4. **Well Documented**: Complete documentation for users
5. **Production Ready**: Deployed and accessible

---

**Timeline**: 25 days from start to completion
**Effort**: ~40-60 hours total
**Outcome**: Production-ready Green Agent for BrowserGym

*Research completed and implementation plan ready for execution! 🚀*
