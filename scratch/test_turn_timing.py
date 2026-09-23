import time
import sys
import logging

logging.basicConfig(level=logging.INFO)

from backend.orchestrator.agent_loop import run_turn

request = "Draft an Excel spreadsheet containing a comparison table of MFI values across polymer batches from the QC sources and save it to storage/outputs/mfi_comparison.xlsx"

print(f"Starting test turn for request: {request}")
start_time = time.perf_counter()

try:
    for event in run_turn(request):
        elapsed = time.perf_counter() - start_time
        print(f"[{elapsed:6.2f}s] Event: {event.get('type')} - {str(event)[:150]}")
except Exception as e:
    elapsed = time.perf_counter() - start_time
    print(f"[{elapsed:6.2f}s] Exception: {type(e).__name__}: {e}")

print(f"Total time elapsed: {time.perf_counter() - start_time:.2f}s")
