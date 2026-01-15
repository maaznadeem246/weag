# WEAG Purple Agent - Baseline Web Automation Agent

A baseline Purple Agent (participant) for the [AgentBeats](https://agentbeats.dev) platform that demonstrates how to interact with the WEAG Green Agent for BrowserGym evaluation.

## Abstract

This Purple Agent serves as a reference implementation for teams building web automation agents. It connects to the Green Agent via A2A protocol, receives MCP server details, and executes web tasks using the BrowserGym environment tools.

## Features

- **A2A Protocol**: Compliant Agent-to-Agent communication
- **MCP Client**: Connects to Green Agent's MCP server for browser control
- **OpenAI Agents SDK**: Uses modern agent framework for task execution
- **Minimal Dependencies**: Lightweight implementation for easy customization

## Project Structure

```
src/
├── main.py              # A2A server entry point
├── executor.py          # A2A request handling
├── agent/               # Agent implementation
│   ├── agent_factory.py # Agent creation
│   ├── context.py       # Agent context
│   └── instructions.py  # System prompts
├── tools/               # MCP proxy tools
└── utils/               # Logging utilities
tests/
└── test_agent.py        # A2A conformance tests
```

## Running Locally

```bash
# Install dependencies
uv sync

# Set environment variables (copy from sample.env)
cp ../sample.env .env
# Edit .env with your API keys

# Run the Purple Agent server
uv run src/main.py --host 127.0.0.1 --port 9010
```

## Running with Docker

```bash
# Build the image
docker build -t weag-purple-agent .

# Run the container
docker run -p 9010:9010 \
  -e GEMINI_API_KEY=your-key \
  weag-purple-agent --port 9010
```

## Testing

```bash
# Install test dependencies
uv sync --extra test

# Start the agent (in another terminal)
uv run src/main.py --host 127.0.0.1 --port 9010

# Run A2A conformance tests
uv run pytest --agent-url http://localhost:9010
```

## Agent Capabilities

The Purple Agent receives task instructions from the Green Agent and uses MCP tools to:
- Observe the current page state (accessibility tree, screenshots)
- Execute browser actions (click, type, scroll, navigate)
- Submit task completion artifacts

## Environment Variables

See `../sample.env` for required environment variables:
- `GEMINI_API_KEY` - Google Gemini API key (or other LLM provider)

## Customization

To build your own Purple Agent:
1. Fork this repository
2. Modify `src/agent/instructions.py` for your task strategy
3. Update `src/agent/agent_factory.py` for custom tools
4. Test against the Green Agent

## License

MIT License
