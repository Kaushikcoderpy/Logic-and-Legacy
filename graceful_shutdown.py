import os
import signal
import asyncio
import logging
from fastapi import FastAPI, Response, status

# Setup logging to see the shutdown sequence clearly
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GracefulShutdown")

app = FastAPI()

class ShutdownState:
    """
    Core logic for state-aware shutdowns. 
    Bypasses high-level framework events to intercept OS signals directly.
    """
    def __init__(self):
        self.is_shutting_down = False
        self.active_tasks = 0

    def start_task(self):
        self.active_tasks += 1

    def finish_task(self):
        self.active_tasks -= 1

state = ShutdownState()

def handle_exit(sig, frame):
    """
    THE SIGNAL INTERCEPTOR.
    Triggered by SIGTERM (K8s) or SIGINT (Ctrl+C).
    """
    logger.info(f"Received signal {sig}. Flipping readFlag to False...")
    state.is_shutting_down = True
    # In a real app, you would NOT exit here. 
    # You let the event loop finish active_tasks.

# Registering signals at the OS level
signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)

@app.get("/healthz")
async def health_check():
    """
    READINESS PROBE: This is the secret sauce.
    K8s stops sending traffic the moment this returns non-200.
    """
    if state.is_shutting_down:
        logger.warning("Healthcheck FAILED: Pod is terminating.")
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return {"status": "alive"}

@app.post("/tasks/submit")
async def submit_task():
    """
    Production Guard: Never accept new work during shutdown.
    """
    if state.is_shutting_down:
        raise HTTPException(status_code=503, detail="Server is shutting down")
    
    state.start_task()
    try:
        logger.info("Processing long-running task...")
        await asyncio.sleep(10) # Simulate AI or Order processing
        return {"message": "Task Completed"}
    finally:
        state.finish_task()

if __name__ == "__main__":
    import uvicorn
    # Note: For signals to work correctly, you must handle the loop carefully.
    uvicorn.run(app, host="0.0.0.0", port=8000)
