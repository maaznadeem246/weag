"""
A2A Client for Test Purple Agent.

Communicates with Green Agent using proper A2A protocol.
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, ClientFactory, ClientConfig
from a2a.types import Message, Part, TextPart, DataPart, FilePart, Role, TaskState


logger = logging.getLogger(__name__)


class A2AClient:
    """Client for A2A communication with Green Agent."""
    
    def __init__(self, green_agent_url: str, default_timeout: int = 300):
        """
        Initialize A2A client.

        Args:
            green_agent_url: Green Agent A2A endpoint URL
            default_timeout: Default timeout for requests in seconds
        """
        self.green_agent_url = green_agent_url.rstrip("/")
        self.default_timeout = default_timeout
        # Configure timeout for streaming responses
        # - Short connect timeout (10s)
        # - Long read timeout for streaming events
        # - Keep pool timeout reasonable
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=default_timeout,
                write=10.0,
                pool=10.0
            ),
            # # Enable HTTP/2 for better streaming support
            # http2=True,
            # Follow redirects
            follow_redirects=True
        )
    
    def _extract_part_data(self, part: Part, logger) -> Dict[str, Any]:
        """
        Extract data from A2A Part following official A2A SDK pattern.
        
        Handles TextPart, FilePart, and DataPart according to official examples.
        
        Args:
            part: A2A Part object
            logger: Logger instance
            
        Returns:
            Dict with extracted content
        """
        part_dict = {}
        
        if not hasattr(part, 'root'):
            return part_dict
        
        root = part.root
        
        # TextPart - most common for task instructions
        if isinstance(root, TextPart) or (hasattr(root, 'kind') and root.kind == 'text'):
            if hasattr(root, 'text'):
                part_dict["text"] = root.text
                logger.debug(f"Extracted TextPart: {root.text[:200]}...")
        
        # FilePart - for file references
        elif isinstance(root, FilePart) or (hasattr(root, 'kind') and root.kind == 'file'):
            if hasattr(root, 'file'):
                part_dict["file"] = {
                    "name": root.file.name if hasattr(root.file, 'name') else None,
                    "uri": root.file.uri if hasattr(root.file, 'uri') else None,
                    "mime_type": root.file.mime_type if hasattr(root.file, 'mime_type') else None
                }
                logger.debug(f"Extracted FilePart: {root.file.name}")
        
        # DataPart - for structured data
        elif isinstance(root, DataPart) or (hasattr(root, 'kind') and root.kind == 'data'):
            if hasattr(root, 'data'):
                part_dict["data"] = root.data
                logger.debug(f"Extracted DataPart: {type(root.data)}")
        
        return part_dict
        
    async def submit_evaluation_request(
        self,
        task_id: Optional[str] = None,
        benchmark: Optional[str] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Submit evaluation request to Green Agent using A2A protocol.
        
        Args:
            task_id: Task ID (optional, e.g., miniwob.click-test)
            benchmark: Benchmark name (optional, e.g., miniwob)
            timeout: Task timeout in seconds (optional)
            
        Returns:
            Response with task_id and MCP connection details
        """
        try:
            # Step 1: Get Green Agent card
            logger.info(f"Connecting to Green Agent at {self.green_agent_url}")
            resolver = A2ACardResolver(httpx_client=self.client, base_url=self.green_agent_url)

            # Retry fetching agent card with bounded backoff while Green Agent starts
            agent_card = None
            start_ts = time.time()
            timeout = min(self.default_timeout, 30)
            attempt = 0
            backoff = 0.5
            last_exc: Optional[Exception] = None
            while time.time() - start_ts < timeout:
                attempt += 1
                try:
                    agent_card = await resolver.get_agent_card()
                    logger.info(f"Connected to: {agent_card.name} (after {attempt} attempts)")
                    break
                except Exception as exc:
                    last_exc = exc
                    logger.debug(f"Attempt {attempt}: unable to fetch agent card yet: {exc}")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 1.5, 5.0)

            if not agent_card:
                # Raise original exception for upstream handling
                logger.error("Failed to fetch agent card from Green Agent after retries")
                raise last_exc or RuntimeError("Failed to fetch agent card from Green Agent")
            
            # Step 2: Create A2A client with streaming enabled
            # Per AgentBeats tutorial: streaming=True allows receiving artifacts/updates in real-time
            client_config = ClientConfig(httpx_client=self.client, streaming=True)
            factory = ClientFactory(client_config)
            a2a_client = factory.create(agent_card)
            
            # Step 3: Send a simple readiness message to Green Agent
            # Green Agent will reply with task assignment and MCP details via A2A messages
            # We prefer a simple readiness message; task details are optional and may
            # be provided later by the Green Agent via A2A messages.
            text = "I want to evaluate a browser task"
            message = Message(
                kind="message",
                role=Role.user,
                parts=[Part(root=TextPart(text=text))],
                message_id=uuid4().hex,
            )

            logger.info("Sending readiness message via A2A...")
            print("[PURPLE] Sending message to Green Agent (streaming=True)...", flush=True)
            
            # Step 4: Process streaming response following official A2A SDK pattern
            # Official pattern from Context7 examples:
            # - Direct Message response: if isinstance(event, Message)
            # - Streaming tuple response: if isinstance(event, tuple) => (Task, UpdateEvent)
            # - Check task.status.state for completion
            # - Extract text from task.status.message.parts[0].root.text
            
            all_messages: list[Dict[str, Any]] = []
            task_id_response = None

            async for event in a2a_client.send_message(message):
                logger.debug(f"Received A2A event: {type(event)}")
                
                # Pattern 1: Direct Message response (non-streaming agents)
                if isinstance(event, Message):
                    print(f"[PURPLE] Received direct Message with {len(event.parts)} parts", flush=True)
                    msg_dict = {"role": str(event.role), "parts": []}
                    
                    for part in event.parts:
                        part_dict = self._extract_part_data(part, logger)
                        if part_dict:
                            msg_dict["parts"].append(part_dict)
                    
                    all_messages.append(msg_dict)
                    
                    # For direct messages, extract task_id from context
                    if hasattr(event, 'context_id') and event.context_id:
                        task_id_response = event.context_id
                    
                    # Direct messages are complete responses
                    print(f"[PURPLE] Direct message response received", flush=True)
                    continue
                
                # Pattern 2: Streaming (Task, UpdateEvent) tuple (streaming agents)
                elif isinstance(event, tuple) and len(event) >= 2:
                    task, update = event
                    task_state = task.status.state if task.status else TaskState.submitted
                    print(f"[PURPLE] Task update: state={task_state}", flush=True)
                    
                    # Extract task_id
                    if hasattr(task, 'id'):
                        task_id_response = task.id
                    
                    # Check for completion
                    if task_state == TaskState.completed:
                        print(f"[PURPLE] Task completed!", flush=True)
                        
                        # Extract response message from task.status.message
                        if task.status and task.status.message:
                            msg_dict = {"role": "agent", "parts": []}
                            for part in task.status.message.parts:
                                part_dict = self._extract_part_data(part, logger)
                                if part_dict:
                                    msg_dict["parts"].append(part_dict)
                            
                            if msg_dict["parts"]:
                                all_messages.append(msg_dict)
                        
                        # Task complete, exit loop
                        break
                    
                    # Handle other states
                    elif task_state in [TaskState.failed, TaskState.rejected, TaskState.canceled]:
                        print(f"[PURPLE] Task ended: {task_state}", flush=True)
                        
                        # Extract error message if available
                        if task.status and task.status.message:
                            msg_dict = {"role": "agent", "parts": []}
                            for part in task.status.message.parts:
                                part_dict = self._extract_part_data(part, logger)
                                if part_dict:
                                    msg_dict["parts"].append(part_dict)
                            
                            if msg_dict["parts"]:
                                all_messages.append(msg_dict)
                        
                        break
                    
                    # Task is working - check for status messages
                    elif task_state == TaskState.working:
                        from a2a.types import TaskStatusUpdateEvent
                        
                        if isinstance(update, TaskStatusUpdateEvent) and update.status.message:
                            msg_dict = {"role": "agent", "parts": []}
                            for part in update.status.message.parts:
                                part_dict = self._extract_part_data(part, logger)
                                if part_dict:
                                    msg_dict["parts"].append(part_dict)
                            
                            if msg_dict["parts"]:
                                all_messages.append(msg_dict)
                    
                    continue
            
            print(f"[PURPLE] A2A message exchange complete: received {len(all_messages)} message(s)", flush=True)
            
            return {
                "task_id": task_id_response or task_id,
                "benchmark": benchmark,
                "messages": all_messages,
                "status": "accepted",
            }
            
        except Exception as e:
            logger.error(f"Failed to submit evaluation request: {e}")
            raise
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
