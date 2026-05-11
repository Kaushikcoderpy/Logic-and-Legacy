import inspect
import asyncio
from functools import wraps
from typing import Callable, Any, Dict
from fastapi import FastAPI, HTTPException
import uvicorn

app = FastAPI(title="Kurukshetra DI Engine")

# =====================================================================
# 1. THE CUSTOM DEPENDENCY INJECTION CONTAINER (The Armory)
# =====================================================================
class KurukshetraArmory:
    """
    A custom DI Container. We are banning fastapi.Depends.
    This reads function signatures, resolves nested dependencies recursively, 
    and caches instances per-request to avoid redundant DB calls.
    """
    def __init__(self):
        self._providers: Dict[str, Callable] = {}

    def register(self, param_name: str, provider_func: Callable):
        """Registers a function to be injected when 'param_name' is requested."""
        self._providers[param_name] = provider_func

    async def resolve(self, func: Callable, request_cache: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively inspects the function signature and resolves dependencies.
        `request_cache` ensures dependencies (like DBs) are instantiated only ONCE per HTTP request.
        """
        sig = inspect.signature(func)
        kwargs = {}
        
        for param_name in sig.parameters:
            if param_name in self._providers:
                # 1. Check if we already resolved this during the current request
                if param_name in request_cache:
                    kwargs[param_name] = request_cache[param_name]
                    continue
                
                provider = self._providers[param_name]
                
                # 2. CHAINING: Recursively resolve the dependencies of the provider itself!
                provider_kwargs = await self.resolve(provider, request_cache)
                
                # 3. Execute the provider with its resolved dependencies
                if inspect.iscoroutinefunction(provider):
                    result = await provider(**provider_kwargs)
                else:
                    result = provider(**provider_kwargs)
                
                # 4. Cache the result for this specific HTTP request lifecycle
                request_cache[param_name] = result
                kwargs[param_name] = result
                
        return kwargs

# Initialize our global container
armory = KurukshetraArmory()

def inject(func: Callable):
    """
    The decorator that replaces FastAPI's native DI system.
    Wraps an endpoint, provisions dependencies, and merges them with FastAPI kwargs.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Create a fresh cache for THIS specific HTTP request
        request_cache = {}
        
        # Let the armory fetch everything this endpoint needs
        resolved_deps = await armory.resolve(func, request_cache)
        
        # Merge DI kwargs with FastAPI's native kwargs (like path/query params)
        final_kwargs = {**kwargs, **resolved_deps}
        return await func(*args, **final_kwargs)
    
    return wrapper

# =====================================================================
# 2. DEFINING THE HIERARCHICAL DEPENDENCIES
# =====================================================================

# LEVEL 0 DEPENDENCY: The Database (No dependencies of its own)
def get_divya_astra_db():
    print("--> [DB] Opening connection to Divya Astra Database...")
    return {"status": "connected", "pool_id": "pg_992"}

# LEVEL 1 DEPENDENCY: The Charioteer (Requires the DB)
def get_charioteer(get_divya_astra_db):
    db = get_divya_astra_db
    if db["status"] != "connected":
        raise HTTPException(status_code=500, detail="Database offline")
    
    print("--> [AUTH] Verifying Charioteer context...")
    return {"name": "Krishna", "role": "Divine Guide"}

# LEVEL 2 DEPENDENCY: The Warrior (Requires BOTH Charioteer AND the DB)
# Notice how both Charioteer and Warrior ask for the DB. 
# Our request_cache will ensure the DB is only opened ONCE.
async def get_maharathi_warrior(get_charioteer, get_divya_astra_db):
    guide = get_charioteer
    db = get_divya_astra_db
    
    print(f"--> [BIZ LOGIC] Provisioning Warrior with Guide: {guide['name']} using DB: {db['pool_id']}")
    return {"name": "Arjuna", "rank": "Maharathi", "weapon": "Gandiva", "guide": guide}

# Register all providers with our custom engine
armory.register("get_divya_astra_db", get_divya_astra_db)
armory.register("get_charioteer", get_charioteer)
armory.register("get_maharathi_warrior", get_maharathi_warrior)

# =====================================================================
# 3. THE FASTAPI ENDPOINTS
# =====================================================================

@app.get("/battlefield/strike")
@inject  # OUR custom decorator, NOT FastAPI's system
async def launch_astra(get_maharathi_warrior, target: str = "Karna"):
    """
    Notice the signature: `get_maharathi_warrior` is automatically resolved.
    FastAPI handles `target` via query parameters. 
    Our `@inject` wrapper merges them together flawlessly.
    """
    warrior = get_maharathi_warrior
    
    if warrior["name"] != "Arjuna":
        raise HTTPException(status_code=403, detail="Only Arjuna can wield this.")
        
    return {
        "message": f"SUCCESS: {warrior['name']} fires the {warrior['weapon']} at {target}!", 
        "warrior_context": warrior
    }

if __name__ == "__main__":
    print("Starting Kurukshetra Server...")
    print("Try: curl 'http://127.0.0.1:8000/battlefield/strike?target=Bheeshma'")
    uvicorn.run(app, host="127.0.0.1", port=8000)
