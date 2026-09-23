import time
import requests
import json
from backend.models.ollama_client import OLLAMA_HOST, default_options
from backend.models.registry import resolve_model_name
from backend.orchestrator.agent_loop import CHAT_TOOLS, _tools_for_chat, _SYSTEM_PROMPT

model = resolve_model_name("reasoning-model")
tools = _tools_for_chat()

print(f"Model resolved: {model}")
print(f"Tools count: {len(tools)}")
print("Tool names:", [t["function"]["name"] for t in tools])

messages = [
    {"role": "system", "content": _SYSTEM_PROMPT},
    {"role": "user", "content": "Draft an Excel spreadsheet containing a comparison table of MFI values across polymer batches from the QC sources and save it to storage/outputs/mfi_comparison.xlsx"}
]

print("Sending POST request to Ollama...")
t0 = time.perf_counter()

try:
    resp = requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "tools": tools,
            "stream": True,
            "options": default_options(),
        },
        timeout=30,
        stream=True
    )
    print(f"[{time.perf_counter() - t0:.2f}s] Response status: {resp.status_code}")
    for line in resp.iter_lines():
        if line:
            print(f"[{time.perf_counter() - t0:.2f}s] Frame: {line.decode('utf-8')[:150]}")
            break
except Exception as e:
    print(f"[{time.perf_counter() - t0:.2f}s] Error: {type(e).__name__}: {e}")
