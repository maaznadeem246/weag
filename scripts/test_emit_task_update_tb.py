import asyncio,traceback
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.utils import new_agent_text_message, new_task
from src.green_agent.a2a.message_handler import emit_task_update

async def main():
    eq = EventQueue()
    msg = new_agent_text_message("Test task message")
    task = new_task(msg)
    await eq.enqueue_event(task)
    updater = TaskUpdater(event_queue=eq, task_id=task.id, context_id=task.context_id)
    try:
        await emit_task_update(updater, "initialization", "Evaluation initialized, MCP server spawned")
        print('emit_task_update succeeded')
    except Exception as e:
        print('Exception repr:', repr(e))
        traceback.print_exc()

if __name__=='__main__':
    asyncio.run(main())
