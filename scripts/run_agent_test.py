import asyncio
import uuid
from agents.run import Runner
from agents import Agent
from src.green_agent.agent.context import AgentContext
from src.green_agent.agent.guardrails.input_guardrails import validate_evaluation_request_guardrail
from src.green_agent.agent.guardrails.output_guardrails import validate_evaluation_artifact_guardrail
import os


async def main():
    os.environ.setdefault("OPENAI_API_KEY", "test")
    agent = Agent(
        name="BrowserGymEvaluatorTest",
        instructions="Orchestrate evaluation",
        tools=[],
        model="test-model",
        input_guardrails=[validate_evaluation_request_guardrail],
        output_guardrails=[validate_evaluation_artifact_guardrail],
    )
    ctx = AgentContext(
        session_id=str(uuid.uuid4()),
        task_id="miniwob.click-test",
        benchmark="miniwob",
        purple_agent_url="http://localhost:9009",
        start_time=0.0,
        shared_state_manager=object(),
    )
    print('Running Runner.run with agent...')
    try:
        result = await Runner.run(agent, "Orchestrate evaluation", context=ctx)
        print('Runner finished:', result)
    except Exception as e:
        print('Runner raised:', e)

if __name__ == '__main__':
    asyncio.run(main())
