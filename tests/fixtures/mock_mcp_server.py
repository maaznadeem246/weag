"""
Mock MCP server for testing Purple agent.

Provides a simple MCP server that responds to tool calls without actual BrowserGym.
Implements T007: Mock MCP server for testing.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional


class MockMCPServer:
    """
    Mock MCP server for testing.
    
    Simulates MCP server responses without BrowserGym environment.
    """
    
    def __init__(self):
        """Initialize mock MCP server."""
        self.tools = [
            {
                "name": "execute_actions",
                "description": "Execute actions in environment",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "actions": {"type": "array"}
                    },
                    "required": ["actions"]
                }
            },
            {
                "name": "get_observation",
                "description": "Get current observation",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "observation_mode": {"type": "string"}
                    }
                }
            }
        ]
        self.session_id: Optional[str] = "mock-session-123"
        self.initialized = True  # Auto-initialized by Green Agent
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        List available tools.
        
        Returns:
            List of tool definitions
        """
        return self.tools
    
    async def call_tool(self, tool_name: str, arguments: dict) -> Dict[str, Any]:
        """
        Simulate tool call.
        
        Args:
            tool_name: Name of tool to call
            arguments: Tool arguments
            
        Returns:
            Mock tool response
        """
        if tool_name == "execute_actions":
            return await self._execute_actions(arguments)
        elif tool_name == "get_observation":
            return await self._get_observation(arguments)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")
    
    async def _execute_actions(self, args: dict) -> Dict[str, Any]:
        """Mock execute_actions."""
        if not self.initialized:
            return {"status": "error", "error": "Environment not initialized"}
        
        actions = args.get("actions", [])
        return {
            "status": "success",
            "actions_executed": len(actions),
            "terminated": False,
            "truncated": False,
            "reward": 0.0
        }
    
    async def _get_observation(self, args: dict) -> Dict[str, Any]:
        """Mock get_observation."""
        if not self.initialized:
            return {"status": "error", "error": "Environment not initialized"}
        
        return {
            "status": "success",
            "observation": {
                "axtree_txt": "Mock AXTree: Button[Click Me]",
                "screenshot": None,
                "dom": "<html><body><button>Click Me</button></body></html>"
            },
            "token_count": 50
        }


__all__ = ["MockMCPServer"]
