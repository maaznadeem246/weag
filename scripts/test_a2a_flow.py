"""
Test script to trigger A2A evaluation flow.

This script sends an evaluation request to Green Agent, which triggers:
1. Green Agent receives request with Purple Agent URL
2. Green Agent initializes MCP server
3. Green Agent sends task + MCP details TO Purple Agent (via A2A message)
4. Purple Agent receives message, connects to MCP, executes task
5. Purple Agent sends result back to Green Agent
6. Green Agent generates final artifact

Prerequisites:
- Green Agent running on port 9009
- Purple Agent running on port 9010  
- MCP Server running on port 8001
"""

import asyncio
import httpx
import json
from uuid import uuid4


async def send_evaluation_request(
    task_id: str = "miniwob.click-test",
    benchmark: str = "miniwob",
    green_agent_url: str = "http://127.0.0.1:9009/",
    purple_agent_url: str = "http://127.0.0.1:9010/"
):
    """
    Send evaluation request to Green Agent.
    
    Args:
        task_id: Task ID (e.g., "miniwob.click-test")
        benchmark: Benchmark name (e.g., "miniwob")
        green_agent_url: Green Agent A2A server URL
        purple_agent_url: Purple Agent A2A server URL
    """
    
    # Create evaluation request per EvalRequest model
    eval_request = {
        "participants": {
            "purple_agent": purple_agent_url
        },
        "config": {
            "task_id": task_id,
            "benchmark": benchmark,
            "description": f"Evaluate {task_id} via A2A protocol"
        }
    }
    
    # Create A2A message/send request
    a2a_request = {
        "jsonrpc": "2.0",
        "id": str(uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": f"Start evaluation for {task_id}"
                    },
                    {
                        "kind": "data",
                        "data": eval_request
                    }
                ],
                "messageId": uuid4().hex
            }
        }
    }
    
    print("=" * 70)
    print("🚀 Triggering A2A Evaluation Flow")
    print("=" * 70)
    print(f"Green Agent:  {green_agent_url}")
    print(f"Purple Agent: {purple_agent_url}")
    print(f"Task:         {task_id} ({benchmark})")
    print("=" * 70)
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            print("\n📤 Sending request to Green Agent...")
            response = await client.post(
                green_agent_url,
                json=a2a_request,
                headers={"Content-Type": "application/json"}
            )
            
            print(f"✓ Response received: HTTP {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print("\n📋 Response:")
                print(json.dumps(result, indent=2))
                
                # Check if task was created
                if "result" in result:
                    result_data = result["result"]
                    if isinstance(result_data, dict):
                        if "type" in result_data and result_data["type"] == "task":
                            task_id = result_data.get("id")
                            status = result_data.get("status", {}).get("state", "unknown")
                            print(f"\n✅ Task Created: {task_id}")
                            print(f"   Status: {status}")
                            print("\n🔄 Green Agent is now:")
                            print("   1. Initializing MCP server (port 8001)")
                            print("   2. Calling send_mcp_details_to_purple_agent tool")
                            print("   3. Sending A2A message TO Purple Agent with:")
                            print("      - Task assignment (task_id, benchmark)")
                            print("      - MCP connection details (URL, transport)")
                            print("\n🟣 Purple Agent will:")
                            print("   1. Receive A2A message from Green Agent")
                            print("   2. Extract task and MCP details")
                            print("   3. Connect to MCP server")
                            print("   4. Execute task using proxy tools")
                            print("   5. Send result back to Green Agent")
                            print("\n👀 Check the agent terminal logs to see the flow!")
                            return True
                        elif "type" in result_data and result_data["type"] == "message":
                            print("\n✅ Message received from Green Agent")
                            print("   (Task may be running in background)")
                            return True
                            
                print("\n⚠️  Unexpected response format")
                return False
            else:
                print(f"\n❌ Error: HTTP {response.status_code}")
                print(response.text)
                return False
                
        except httpx.ConnectError:
            print("\n❌ Could not connect to Green Agent")
            print("\nMake sure servers are running:")
            print("  Terminal 1: python -m src.green_agent.main --port 9009")
            print("  Terminal 2: python -m src.purple_agent.main --port 9010")
            print("  Terminal 3: python scripts/run_mcp_server_standalone.py")
            return False
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Trigger A2A evaluation flow")
    parser.add_argument("--task-id", default="miniwob.click-test", help="Task ID")
    parser.add_argument("--benchmark", default="miniwob", help="Benchmark name")
    parser.add_argument("--green-url", default="http://127.0.0.1:9009/", help="Green Agent URL")
    parser.add_argument("--purple-url", default="http://127.0.0.1:9010/", help="Purple Agent URL")
    
    args = parser.parse_args()
    
    success = await send_evaluation_request(
        task_id=args.task_id,
        benchmark=args.benchmark,
        green_agent_url=args.green_url,
        purple_agent_url=args.purple_url
    )
    
    if success:
        print("\n✅ Request sent successfully!")
    else:
        print("\n❌ Request failed")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())

