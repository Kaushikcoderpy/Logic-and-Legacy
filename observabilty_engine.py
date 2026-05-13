import time
import uuid
import logging
from contextvars import ContextVar
from fastapi import FastAPI, Request, Response
import uvicorn

# =====================================================================
# 1. THE RAW CONTEXT STATE (No Magic)
# =====================================================================
# ContextVars are critical in async Python. Unlike threading.local(), 
# they safely preserve state across async/await boundaries.
_trace_id_ctx_var: ContextVar[str] = ContextVar("trace_id", default="system")

class TraceInjectingFilter(logging.Filter):
    """
    A custom logging filter that reaches into the active async context,
    pulls the trace_id, and attaches it to every single log record natively.
    """
    def filter(self, record):
        record.trace_id = _trace_id_ctx_var.get()
        return True

# =====================================================================
# 2. LOGGER CONFIGURATION
# =====================================================================
logger = logging.getLogger("RawObserver")
logger.setLevel(logging.INFO)

# Notice the %(trace_id)s in the formatter. This doesn't exist by default!
formatter = logging.Formatter(
    fmt="[%(asctime)s] [%(levelname)s] [Trace: %(trace_id)s] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

handler = logging.StreamHandler()
handler.setFormatter(formatter)
handler.addFilter(TraceInjectingFilter()) # Attach our custom context filter
logger.addHandler(handler)

# =====================================================================
# 3. THE RAW METRICS REGISTRY
# =====================================================================
class RawMetricsRegistry:
    """An in-memory counter to simulate what Prometheus does under the hood."""
    def __init__(self):
        self.request_counts = {}
        self.response_times = []

    def inc_request(self, path: str, status: int):
        key = f"{path}_{status}"
        self.request_counts[key] = self.request_counts.get(key, 0) + 1

    def observe_time(self, duration: float):
        self.response_times.append(duration)

metrics = RawMetricsRegistry()

# =====================================================================
# 4. THE APPLICATION & MIDDLEWARE
# =====================================================================
app = FastAPI()

@app.middleware("http")
async def raw_observability_middleware(request: Request, call_next):
    """
    The heart of the observability engine. 
    1. Generates Trace ID.
    2. Starts Timer.
    3. Executes request.
    4. Records Metrics.
    """
    # 1. Identity
    trace_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    
    # Set the ContextVar. This attaches the ID to the current asyncio task.
    token = _trace_id_ctx_var.set(trace_id)
    
    start_time = time.perf_counter()
    
    try:
        logger.info(f"Incoming Request: {request.method} {request.url.path}")
        response = await call_next(request)
        
        # 2. Timing & Metrics
        process_time = time.perf_counter() - start_time
        metrics.inc_request(request.url.path, response.status_code)
        metrics.observe_time(process_time)
        
        logger.info(f"Request Completed. Status: {response.status_code}. Time: {process_time:.4f}s")
        
        # Inject the trace ID back to the client so they can report it to support
        response.headers["X-Trace-ID"] = trace_id
        return response
    
    finally:
        # ALWAYS clean up ContextVars to prevent memory leaks in long-running loops
        _trace_id_ctx_var.reset(token)

# =====================================================================
# 5. BUSINESS LOGIC
# =====================================================================
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    # Notice we don't pass `trace_id` here. The logger knows it automatically.
    logger.info(f"Fetching data for user {user_id} from database...")
    return {"user_id": user_id, "status": "active"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
