# Logic & Legacy: The Internal Architecture of Redis
# Instead of importing a Redis client, we build a Mini-Redis from scratch 
# to demonstrate RAM storage, TTL (Time-To-Live), and LRU Eviction.

import time
import asyncio
from collections import OrderedDict

class MiniRedis:
    """
    An in-memory Key-Value store demonstrating how Redis works internally.
    Uses OrderedDict to maintain O(1) LRU eviction tracking.
    """
    def __init__(self, max_keys=3):
        # RAM Storage. OrderedDict tracks access order (Left = Oldest, Right = Newest)
        self.cache = OrderedDict() 
        self.ttl_store = {} # Maps keys to their absolute expiration timestamp
        self.max_keys = max_keys

    def get(self, key):
        """O(1) RAM Lookup with Lazy Eviction."""
        if key not in self.cache:
            return None
        
        # 1. TTL Check (Lazy Eviction: delete it if it expired before returning)
        if key in self.ttl_store and time.time() > self.ttl_store[key]:
            print(f"[SYSTEM] TTL Expired: '{key}' has been purged from RAM.")
            self.delete(key)
            return None
        
        # 2. LRU Update: Move the accessed key to the end (Mark as 'Most Recently Used')
        self.cache.move_to_end(key)
        return self.cache[key]

    def set(self, key, value, ttl_seconds=None):
        """O(1) Insertion with LRU Eviction Policy."""
        
        # 1. LRU Eviction Policy (If RAM is full, drop the oldest key)
        if key not in self.cache and len(self.cache) >= self.max_keys:
            # popitem(last=False) drops the Left-most item (Least Recently Used)
            evicted_key, _ = self.cache.popitem(last=False)
            if evicted_key in self.ttl_store:
                del self.ttl_store[evicted_key]
            print(f"[⚠️ EVICTION] RAM full. Dropped LRU key: '{evicted_key}'.")

        # 2. Store the Value & Update LRU
        self.cache[key] = value
        self.cache.move_to_end(key)
        
        # 3. Store the TTL Timestamp
        if ttl_seconds:
            self.ttl_store[key] = time.time() + ttl_seconds

    def delete(self, key):
        if key in self.cache:
            del self.cache[key]
        if key in self.ttl_store:
            del self.ttl_store[key]


# ==========================================
# THE BENCHMARK: DISK (Postgres) vs RAM (Redis)
# ==========================================

async def simulate_postgres_fetch():
    """Simulates the physical latency of disk I/O and network overhead."""
    await asyncio.sleep(0.015) # 15 milliseconds
    return [{"id": i, "user": f"user_{i}"} for i in range(50)]

async def run_cache_aside_benchmark():
    redis_engine = MiniRedis(max_keys=5)
    cache_key = "users:top_50"
    
    print("\n--- FIRST REQUEST (Expecting Cache Miss) ---")
    start_time = time.perf_counter()
    
    # 1. Ask Cache
    data = redis_engine.get(cache_key)
    if not data:
        print("[❌ CACHE MISS] Hitting physical disk (PostgreSQL)...")
        # 2. Fetch from DB
        data = await simulate_postgres_fetch()
        # 3. Save to RAM with 60s TTL
        redis_engine.set(cache_key, data, ttl_seconds=60)
        
    db_time = time.perf_counter() - start_time
    print(f"--> Response Time (Disk): {db_time * 1000:.3f} ms")


    print("\n--- SECOND REQUEST (Expecting Cache Hit) ---")
    start_time = time.perf_counter()
    
    # 1. Ask Cache
    data = redis_engine.get(cache_key)
    if data:
        print("[✅ CACHE HIT] Served directly from RAM.")
        
    ram_time = time.perf_counter() - start_time
    print(f"--> Response Time (RAM): {ram_time * 1000:.3f} ms")
    
    print(f"\n[CONCLUSION] RAM is {db_time / ram_time:.0f}x faster than Disk I/O.")


    print("\n--- DEMONSTRATING LRU EVICTION ---")
    redis_engine.set("key_1", "A")
    redis_engine.set("key_2", "B")
    redis_engine.set("key_3", "C")
    # Capacity is 5. We currently hold: users:top_50, key_1, key_2, key_3.
    # We are at 4/5 capacity. Let's add 2 more to force an eviction.
    redis_engine.set("key_4", "D")
    redis_engine.set("key_5", "E") # This will trigger the eviction of 'users:top_50'

if __name__ == "__main__":
    asyncio.run(run_cache_aside_benchmark())
