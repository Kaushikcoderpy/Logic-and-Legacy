# Logic & Legacy: FastAPI Routing Internal Architecture
# This script simulates how FastAPI and Starlette process HTTP requests under the hood,
# including Route Priority, Decorators, and the Sync/Async Execution pools.

import asyncio
import re
import inspect
from concurrent.futures import ThreadPoolExecutor

class APIRouter:
    """
    Simulates FastAPI's APIRouter.
    A mini-application object to group related routes.
    """
    def __init__(self):
        # FastAPI evaluates routes IN THE ORDER THEY ARE DEFINED.
        self.routes = []
        # A ThreadPool for executing synchronous 'def' functions without blocking the async loop.
        self.thread_pool = ThreadPoolExecutor()

    def _add_route(self, method, path, endpoint):
        """Translates a path like /users/{user_id} into a Regex capture group."""
        regex_path = re.sub(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', r'(?P<\1>[^/]+)', path)
        pattern = re.compile(f"^{regex_path}$")
        self.routes.append({
            "method": method.upper(), 
            "pattern": pattern, 
            "endpoint": endpoint, 
            "original_path": path
        })

    def get(self, path):
        """Decorator mapping a GET request to a function."""
        def decorator(endpoint):
            self._add_route("GET", path, endpoint)
            return endpoint
        return decorator

    def post(self, path):
        """Decorator mapping a POST request to a function."""
        def decorator(endpoint):
            self._add_route("POST", path, endpoint)
            return endpoint
        return decorator

    async def dispatch(self, method: str, path: str):
        """The core Request Lifecycle executed when a URL hits the server."""
        print(f"\n[INBOUND] {method} {path}")
        
        # 1. MATCHING (The Starlette Phase)
        for route in self.routes:
            if route["method"] == method.upper():
                match = route["pattern"].match(path)
                if match:
                    print(f"  [MATCH] Route '{route['original_path']}' caught the request.")
                    
                    # 2. RESOLUTION (Extracting Path Params & Dependencies)
                    path_params = match.groupdict()
                    endpoint = route["endpoint"]
                    
                    # 3. EXECUTION (The FastAPI Magic)
                    if inspect.iscoroutinefunction(endpoint):
                        # It is an 'async def'. Run directly on the Event Loop.
                        print("  [EXECUTION] Detected 'async def'. Running on Event Loop...")
                        result = await endpoint(**path_params)
                    else:
                        # It is a standard 'def'. Run in a separate Thread to prevent blocking!
                        print("  [EXECUTION] Detected 'def'. Dispatching to ThreadPoolExecutor...")
                        loop = asyncio.get_running_loop()
                        result = await loop.run_in_executor(
                            self.thread_pool, 
                            lambda: endpoint(**path_params)
                        )
                    
                    # 4. SERIALIZATION (Simulating Pydantic)
                    print(f"  [SERIALIZATION] Validating & converting to JSON: {result}")
                    return result
        
        print("  [ERROR] 404 Not Found")
        return None

# ==========================================
# THE APPLICATION (Using the Router)
# ==========================================

router = APIRouter()

# ⚠️ ROUTE ORDER PRIORITY DEMONSTRATION ⚠️
# Fixed/Static paths MUST be defined before dynamic paths!

@router.get("/users/me")
async def get_current_user():
    """Static Route. Executed natively on the Event Loop."""
    return {"user_id": "current_admin", "status": "active"}

@router.get("/users/{user_id}")
def get_user_by_id(user_id: str):
    """Dynamic Route. Executed in a ThreadPool because it is a synchronous 'def'."""
    return {"user_id": user_id, "status": "fetched_from_db"}

@router.post("/api/books")
async def create_book():
    """A completely different HTTP method on the same path structure."""
    return {"status": "success", "message": "Book created."}


# ==========================================
# THE BENCHMARK & EXECUTION
# ==========================================

async def run_server_simulation():
    # 1. Routing based on HTTP Verb (POST vs GET)
    await router.dispatch("POST", "/api/books")
    
    # 2. The Route Order Priority Test
    # This hits the static route because it was registered FIRST.
    await router.dispatch("GET", "/users/me")
    
    # 3. Dynamic Variable Extraction & ThreadPool dispatch
    await router.dispatch("GET", "/users/99")

if __name__ == "__main__":
    asyncio.run(run_server_simulation())

"""
=========================================
EXPECTED EXECUTION RESULTS
=========================================

[INBOUND] POST /api/books
  [MATCH] Route '/api/books' caught the request.
  [EXECUTION] Detected 'async def'. Running on Event Loop...
  [SERIALIZATION] Validating & converting to JSON: {'status': 'success', 'message': 'Book created.'}

[INBOUND] GET /users/me
  [MATCH] Route '/users/me' caught the request.
  [EXECUTION] Detected 'async def'. Running on Event Loop...
  [SERIALIZATION] Validating & converting to JSON: {'user_id': 'current_admin', 'status': 'active'}

[INBOUND] GET /users/99
  [MATCH] Route '/users/{user_id}' caught the request.
  [EXECUTION] Detected 'def'. Dispatching to ThreadPoolExecutor...
  [SERIALIZATION] Validating & converting to JSON: {'user_id': '99', 'status': 'fetched_from_db'}
"""
