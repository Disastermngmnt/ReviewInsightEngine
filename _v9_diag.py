
import asyncio
import os
from dotenv import load_dotenv
from core.llm_orchestrator import LLMOrchestrator

async def diag():
    load_dotenv()
    print("--- Environment Check ---")
    print(f"GOOGLE_API_KEY: {'[SET]' if os.getenv('GOOGLE_API_KEY') else '[MISSING]'}")
    print(f"GOOGLE_GEMINI_API_KEY: {'[SET]' if os.getenv('GOOGLE_GEMINI_API_KEY') else '[MISSING]'}")
    print(f"OPENAI_API_KEY: {'[SET]' if os.getenv('OPENAI_API_KEY') else '[MISSING]'}")
    
    orchestrator = LLMOrchestrator()
    print("\n--- Model Selector Check ---")
    for task in ["classification", "scoring", "strategic_plan"]:
        models = orchestrator.selector.select_for_task(task)
        print(f"Task '{task}': {[m['model_id'] for m in models] if models else 'NO MODELS AVAILABLE'}")

    print("\n--- Live Test (Node 0 Style) ---")
    try:
        resp = await orchestrator.query(
            task_type="classification",
            system_prompt="Return JSON {'test': true}",
            user_message="Say hello in JSON",
            options={"json_mode": True}
        )
        print(f"SUCCESS: {resp}")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(diag())
