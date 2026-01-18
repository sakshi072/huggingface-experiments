import time
from langchain_core.callbacks import BaseCallbackHandler

_request_log = []

def log_request(event: str):
    """Log all API requests with timestamps"""
    timestamp = time.time()
    _request_log.append((timestamp, event))
    
    # Print recent history
    print(f"\n{'='*60}")
    print(f"📊 REQUEST LOG (last 5 events):")
    print(f"{'='*60}")
    
    for ts, evt in _request_log[-5:]:
        relative_time = ts - _request_log[0][0]
        print(f"  +{relative_time:6.2f}s: {evt}")
    
    print(f"{'='*60}\n")

# In your LLM initialization:
class RequestLogger(BaseCallbackHandler):
    def on_llm_start(self, *args, **kwargs):
        log_request(f"🔥 LLM CALL STARTED")
    
    def on_llm_end(self, *args, **kwargs):
        log_request(f"✅ LLM CALL COMPLETED")
    
    def on_llm_error(self, error, *args, **kwargs):
        log_request(f"❌ LLM CALL FAILED: {error}")
