"""
Integration test: Dummy Purple Agent + Green Agent
Simulates complete A2A assessment flow with MCP tool invocation.

This script:
1. Starts Green Agent A2A server
2. Starts Dummy Purple Agent that responds to A2A requests
3. Purple agent discovers and invokes MCP tools
4. Simulates correct and incorrect actions
5. Verifies complete evaluation flow
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import httpx
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Message,
    Part,
    TextPart,
    Role,
)
from a2a.client import ClientFactory, ClientConfig, A2ACardResolver
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
import uvicorn

from src.green_agent.utils.models import EvalRequest
from src.green_agent.main import BrowserGymGreenAgent, create_agent_card
from src.green_agent.a2a.executor import GreenExecutor

print("=" * 70)
print("Integration Test: Green Agent + Dummy Purple Agent")
print("=" * 70)


class DummyPurpleAgent(AgentExecutor):
    """
    Dummy purple agent that simulates real agent behavior.
    
    Flow:
    1. Receives MCP connection details from green agent
    2. Spawns MCP client to invoke tools
    3. Simulates task execution (some correct, some incorrect)
    4. Returns results
    """
    
    def __init__(self, scenario: str = "success"):
        """
        Initialize dummy purple agent.
        
        Args:
            scenario: "success" (all correct), "failure" (all wrong), or "mixed"
        """
        self.scenario = scenario
        self.mcp_process = None
        
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute dummy purple agent behavior."""
        user_input = context.get_user_input()
        
        print(f"\n[Purple Agent] Received input: {user_input[:100]}...")
        
        # Parse MCP connection details from green agent
        try:
            # In real implementation, green agent streams MCP details via A2A updates
            # For now, we'll simulate MCP tool invocations
            await self._simulate_mcp_interaction(event_queue)
        except Exception as e:
            print(f"[Purple Agent] Error: {e}")
            raise
    
    async def _simulate_mcp_interaction(self, event_queue: EventQueue):
        """Simulate MCP tool invocations."""
        
        print("\n[Purple Agent]  Discovering MCP tools...")
        await asyncio.sleep(0.5)
        print("[Purple Agent]  Found 2 base tools: execute_actions, get_observation")
        print("[Purple Agent]  Note: Environment already initialized by Green Agent")
        
        # Step 1: Get observation
        print("\n[Purple Agent]  Step 1: Getting observation (axtree mode)")
        await self._send_response(event_queue, {
            "tool": "get_observation",
            "params": {"observation_mode": "axtree"},
            "status": "called"
        })
        await asyncio.sleep(0.5)
        print("[Purple Agent]  Observation received (~4500 tokens)")
        
        # Step 2: Execute actions based on scenario
        if self.scenario == "success":
            await self._simulate_success_scenario(event_queue)
        elif self.scenario == "failure":
            await self._simulate_failure_scenario(event_queue)
        else:  # mixed
            await self._simulate_mixed_scenario(event_queue)
        
        # Green Agent handles cleanup automatically when task completes
        print("\n[Purple Agent]  Task execution complete - Green Agent will cleanup")
        await asyncio.sleep(0.5)
        print("[Purple Agent]  Cleanup complete, 0 orphaned processes")
        
        # Final response
        await self._send_response(event_queue, {
            "status": "completed",
            "evaluation_result": "Task attempted" if self.scenario == "failure" else "Task completed"
        })
    
    async def _simulate_success_scenario(self, event_queue: EventQueue):
        """Simulate correct action sequence."""
        print("\n[Purple Agent]  Step 3: Executing actions (SUCCESS scenario)")
        
        actions = [
            {"action": "click", "bid": "submit-button", "description": "Click submit button"},
            {"action": "scroll", "direction": "down", "description": "Scroll to view result"}
        ]
        
        await self._send_response(event_queue, {
            "tool": "execute_actions",
            "params": {"actions": actions},
            "status": "called"
        })
        await asyncio.sleep(1.5)
        print("[Purple Agent]  Actions executed successfully")
        print("[Purple Agent]   - Action 1: click(submit-button) → success, reward=1.0")
        print("[Purple Agent]   - Action 2: scroll(down) → task completed, done=True")
        print("[Purple Agent]  Task completed successfully!")
    
    async def _simulate_failure_scenario(self, event_queue: EventQueue):
        """Simulate incorrect action sequence."""
        print("\n[Purple Agent]  Step 3: Executing actions (FAILURE scenario)")
        
        actions = [
            {"action": "click", "bid": "wrong-button", "description": "Click wrong button"},
            {"action": "click", "bid": "another-wrong-button", "description": "Click another wrong button"},
            {"action": "noop", "description": "Give up"}
        ]
        
        await self._send_response(event_queue, {
            "tool": "execute_actions",
            "params": {"actions": actions},
            "status": "called"
        })
        await asyncio.sleep(1.5)
        print("[Purple Agent]  Actions executed but task failed")
        print("[Purple Agent]   - Action 1: click(wrong-button) → no reward, reward=0.0")
        print("[Purple Agent]   - Action 2: click(another-wrong-button) → no reward")
        print("[Purple Agent]   - Action 3: noop → truncated=True (gave up)")
        print("[Purple Agent]  Task failed - wrong actions taken")
    
    async def _simulate_mixed_scenario(self, event_queue: EventQueue):
        """Simulate partially correct sequence."""
        print("\n[Purple Agent]  Step 3: Executing actions (MIXED scenario)")
        
        # First batch: wrong actions
        actions_batch1 = [
            {"action": "click", "bid": "wrong-link", "description": "Try wrong link"},
            {"action": "scroll", "direction": "up", "description": "Scroll wrong direction"}
        ]
        
        await self._send_response(event_queue, {
            "tool": "execute_actions",
            "params": {"actions": actions_batch1},
            "status": "called"
        })
        await asyncio.sleep(1)
        print("[Purple Agent]   Batch 1: Some actions failed")
        
        # Get observation again
        print("\n[Purple Agent]  Step 4a: Re-analyzing observation")
        await self._send_response(event_queue, {
            "tool": "get_observation",
            "params": {"observation_mode": "axtree"},
            "status": "called"
        })
        await asyncio.sleep(0.5)
        
        # Second batch: correct actions
        actions_batch2 = [
            {"action": "click", "bid": "submit-button", "description": "Found correct button!"},
        ]
        
        print("\n[Purple Agent]  Step 4b: Correcting approach")
        await self._send_response(event_queue, {
            "tool": "execute_actions",
            "params": {"actions": actions_batch2},
            "status": "called"
        })
        await asyncio.sleep(1)
        print("[Purple Agent]  Final action succeeded!")
        print("[Purple Agent]  Task completed after correction")
    
    async def _send_response(self, event_queue: EventQueue, data: dict):
        """Send response back via A2A."""
        message = Message(
            kind="message",
            role=Role.assistant,
            parts=[Part(root=TextPart(kind="text", text=json.dumps(data, indent=2)))],
            message_id=f"purple-{datetime.now().timestamp()}",
        )
        await event_queue.enqueue_event(message)
    
    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        """Cancel execution."""
        print("[Purple Agent] Cancellation requested")


def create_purple_agent_card(url: str) -> AgentCard:
    """Create agent card for dummy purple agent."""
    skill = AgentSkill(
        id="web_navigation",
        name="Web Navigation",
        description="Navigates websites and completes tasks",
        tags=["browsergym", "web"],
        examples=[]
    )
    
    return AgentCard(
        name="Dummy Purple Agent",
        description="Test purple agent that simulates task execution",
        url=url,
        version="0.1.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )


async def start_purple_agent_server(host: str, port: int, scenario: str):
    """Start dummy purple agent A2A server."""
    agent_url = f"http://{host}:{port}/"
    
    print(f"\n[Purple Agent Server] Starting on {agent_url}")
    print(f"[Purple Agent Server] Scenario: {scenario.upper()}")
    
    purple_agent = DummyPurpleAgent(scenario=scenario)
    agent_card = create_purple_agent_card(agent_url)
    
    request_handler = DefaultRequestHandler(
        agent_executor=purple_agent,
        task_store=InMemoryTaskStore(),
    )
    
    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )
    
    config = uvicorn.Config(
        server.build(),
        host=host,
        port=port,
        log_level="error"  # Suppress uvicorn logs
    )
    server_instance = uvicorn.Server(config)
    
    # Run in background task
    asyncio.create_task(server_instance.serve())
    await asyncio.sleep(2)  # Wait for server to start
    print(f"[Purple Agent Server]  Ready on port {port}")


async def start_green_agent_server(host: str, port: int):
    """Start green agent A2A server."""
    agent_url = f"http://{host}:{port}/"
    
    print(f"\n[Green Agent Server] Starting on {agent_url}")
    
    green_agent = BrowserGymGreenAgent()
    executor = GreenExecutor(green_agent)
    agent_card = create_agent_card(agent_url)
    
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )
    
    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )
    
    config = uvicorn.Config(
        server.build(),
        host=host,
        port=port,
        log_level="error"
    )
    server_instance = uvicorn.Server(config)
    
    # Run in background task
    asyncio.create_task(server_instance.serve())
    await asyncio.sleep(2)
    print(f"[Green Agent Server]  Ready on port {port}")


async def send_assessment_request(
    green_url: str,
    purple_url: str,
    task_id: str = "miniwob.click-test",
    max_steps: int = 20
):
    """Send A2A assessment request to green agent using A2A client."""
    print(f"\n[Test Client]  Sending assessment request to green agent")
    print(f"[Test Client]   Purple agent: {purple_url}")
    print(f"[Test Client]   Task: {task_id}")
    print(f"[Test Client]   Max steps: {max_steps}")
    
    request = {
        "participants": {
            "purple_agent": purple_url
        },
        "config": {
            "task_id": task_id,
            "max_steps": max_steps,
            "seed": 42
        }
    }
    
    try:
        # Create A2A client
        async with httpx.AsyncClient(timeout=120.0) as httpx_client:
            resolver = A2ACardResolver(httpx_client=httpx_client, base_url=green_url)
            agent_card = await resolver.get_agent_card()
            
            print(f"[Test Client]  Connected to: {agent_card.name}")
            
            config = ClientConfig(httpx_client=httpx_client, streaming=True)
            factory = ClientFactory(config)
            client = factory.create(agent_card)
            
            # Create message using helper
            from uuid import uuid4
            from a2a.client import helpers
            message = Message(
                kind="message",
                role=Role.user,
                parts=[Part(root=TextPart(kind="text", text=json.dumps(request)))],
                message_id=uuid4().hex
            )
            
            print(f"[Test Client]  Sending message...")
            
            # Send message and collect events
            task_id_received = None
            async for event in client.send_message(message):
                # Event can be Message, (Task, Update), or just Task
                if isinstance(event, tuple):
                    task, update = event
                    event_type = type(update).__name__ if update else "Task"
                    print(f"[Test Client]  Event: {event_type}")
                    
                    if hasattr(task, 'task_id'):
                        task_id_received = task.task_id
                        print(f"[Test Client]   Task ID: {task_id_received}")
                    
                    if hasattr(task, 'status'):
                        print(f"[Test Client]   Status: {task.status.state.value}")
                    
                    # Check for artifact
                    if hasattr(task, 'artifacts') and task.artifacts:
                        print(f"[Test Client]  Artifact received!")
                        for artifact in task.artifacts:
                            for part in artifact.parts:
                                if hasattr(part.root, 'data'):
                                    artifact_data = part.root.data
                                    print(f"[Test Client]   Task success: {artifact_data.get('task_success')}")
                                    print(f"[Test Client]   Final score: {artifact_data.get('final_score', 0):.4f}")
                                    print(f"[Test Client]   Total tokens: {artifact_data.get('total_tokens')}")
                                    print(f"[Test Client]   Total latency: {artifact_data.get('total_latency_ms')}ms")
                elif isinstance(event, Message):
                    print(f"[Test Client]  Message received")
                else:
                    print(f"[Test Client]  Event: {type(event).__name__}")
            
            print(f"[Test Client]  Assessment complete")
            return True
            
    except Exception as e:
        print(f"[Test Client]  Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_integration_test(scenario: str = "success"):
    """
    Run complete integration test.
    
    Args:
        scenario: "success", "failure", or "mixed"
    """
    GREEN_HOST = "127.0.0.1"
    GREEN_PORT = 9009
    PURPLE_HOST = "127.0.0.1"
    PURPLE_PORT = 9019
    
    green_url = f"http://{GREEN_HOST}:{GREEN_PORT}"
    purple_url = f"http://{PURPLE_HOST}:{PURPLE_PORT}"
    
    try:
        # Start servers
        await start_green_agent_server(GREEN_HOST, GREEN_PORT)
        await start_purple_agent_server(PURPLE_HOST, PURPLE_PORT, scenario)
        
        print("\n" + "=" * 70)
        print(" Starting Assessment")
        print("=" * 70)
        
        # Send assessment request
        success = await send_assessment_request(
            green_url=green_url,
            purple_url=purple_url,
            task_id="miniwob.click-test",
            max_steps=20
        )
        
        print("\n" + "=" * 70)
        if success:
            print(f" Integration Test PASSED ({scenario.upper()} scenario)")
        else:
            print(f" Integration Test FAILED ({scenario.upper()} scenario)")
        print("=" * 70)
        
        # Keep servers running for a moment to complete processing
        await asyncio.sleep(5)
        
        return success
        
    except KeyboardInterrupt:
        print("\n\n[Test] Interrupted by user")
    except Exception as e:
        print(f"\n\n[Test]  Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main entry point."""
    print("\n[INFO] Available scenarios:")
    print("  1. success - Purple agent executes correct actions, task succeeds")
    print("  2. failure - Purple agent executes wrong actions, task fails")
    print("  3. mixed   - Purple agent makes mistakes then corrects (realistic)")
    
    # For automated testing, run success scenario
    # You can change this to "failure" or "mixed" to test different flows
    scenario = "mixed"  # Change to "success", "failure", or "mixed"
    
    print(f"\n[INFO] Running scenario: {scenario.upper()}\n")
    
    success = await run_integration_test(scenario=scenario)
    
    if success:
        print("\n[SUCCESS] All integration tests passed!")
        print("\n[INFO] Next steps:")
        print("  - Run with different scenarios: 'success', 'failure', 'mixed'")
        print("  - Test with real BrowserGym environment (Phase 7)")
        print("  - Add proper MCP client in purple agent")
        print("  - Deploy to Docker (Phase 9)")
    else:
        print("\n[FAILED] Integration test failed")
        print("Check logs above for details")


if __name__ == "__main__":
    asyncio.run(main())

