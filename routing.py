# Logic & Legacy: The Raw HTTP Routing Engine
# We bypass FastAPI and Flask to build a routing engine from scratch.
# This proves how raw TCP strings are parsed, and how Static vs Dynamic 
# routes are architecturally separated for maximum performance.

import re
from typing import Callable, Dict, Tuple, Any

class HTTPRouter:
    def __init__(self):
        # 1. STATIC ROUTES: O(1) Hash Map lookup. Blistering fast.
        # Format: {"GET:/api/books": handler_function}
        self.static_routes = {}
        
        # 2. DYNAMIC ROUTES: O(N) Regex list lookup (or O(K) Radix tree in modern apps).
        self.dynamic_routes = []

    def add_route(self, method: str, path: str, handler: Callable):
        """Registers a route into the correct architectural bucket."""
        method = method.upper()
        
        if "{" not in path:
            # It's a Static Route (e.g., /api/books)
            self.static_routes[f"{method}:{path}"] = handler
            print(f"[SYSTEM] Registered Static Route:  {method:<6} {path}")
        else:
            # It's a Dynamic Route with Path Params (e.g., /api/books/{id})
            # Convert {id} to a named regex capture group: (?P<id>[^/]+)
            regex_path = re.sub(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', r'(?P<\1>[^/]+)', path)
            pattern = re.compile(f"^{regex_path}$")
            
            self.dynamic_routes.append({
                "method": method,
                "pattern": pattern,
                "handler": handler
            })
            print(f"[SYSTEM] Registered Dynamic Route: {method:<6} {path}")

    def dispatch(self, raw_http_request: str) -> str:
        """
        The Switchboard: Parses a raw incoming TCP string and routes it.
        This answers the hook: How does an API know GET vs POST?
        """
        # 1. Parse the Raw HTTP Request String
        lines = raw_request.strip().split("\r\n")
        request_line = lines[0] # e.g., "GET /api/books HTTP/1.1"
        
        try:
            method, full_path, protocol = request_line.split(" ")
        except ValueError:
            return "400 Bad Request: Malformed Request Line"

        # Separate the Base Path from the Query Parameters (?sort=desc)
        if "?" in full_path:
            path, query_string = full_path.split("?", 1)
        else:
            path, query_string = full_path, ""

        print(f"\n[INBOUND] Parsing: Method='{method}', Path='{path}', Query='{query_string}'")

        # 2. Check Static Routes FIRST (O(1) Speed)
        route_key = f"{method}:{path}"
        if route_key in self.static_routes:
            handler = self.static_routes[route_key]
            return handler(path_params={}, query_string=query_string)

        # 3. Check Dynamic Routes SECOND (O(N) Regex Search)
        for route in self.dynamic_routes:
            if route["method"] == method:
                match = route["pattern"].match(path)
                if match:
                    # Extract the variables (e.g., id="99")
                    path_params = match.groupdict() 
                    return route["handler"](path_params=path_params, query_string=query_string)

        # 4. Fallback if no paths match
        return f"404 Not Found: {method} {path} does not exist."


# ==========================================
# THE DOMAIN LOGIC (Controllers)
# ==========================================

def get_all_books(path_params, query_string):
    return f"200 OK: Returning all books. Applied filters: [{query_string}]"

def create_book(path_params, query_string):
    return "201 Created: Saving new book to database."

def get_single_book(path_params, query_string):
    book_id = path_params.get("id")
    return f"200 OK: Returning details for Book ID: {book_id}"

# ==========================================
# THE BENCHMARK & EXECUTION
# ==========================================

if __name__ == "__main__":
    router = HTTPRouter()
    print("\n--- PHASE 1: BOOTSTRAPPING THE MATRIX ---")
    router.add_route("GET", "/api/books", get_all_books)
    router.add_route("POST", "/api/books", create_book)
    router.add_route("GET", "/api/books/{id}", get_single_book)
    
    print("\n--- PHASE 2: PROCESSING RAW TCP STRINGS ---")
    
    # Simulating raw string payloads arriving over the network socket
    raw_requests = [
        "GET /api/books HTTP/1.1\r\nHost: api.com\r\n\r\n",
        "POST /api/books HTTP/1.1\r\nHost: api.com\r\n\r\n{'title': '1984'}",
        "GET /api/books/99 HTTP/1.1\r\nHost: api.com\r\n\r\n",
        "GET /api/books?sort=author&limit=10 HTTP/1.1\r\nHost: api.com\r\n\r\n"
    ]
    
    for raw_request in raw_requests:
        response = router.dispatch(raw_request)
        print(f"   [RESPONSE] {response}")

"""
=========================================
EXPECTED EXECUTION RESULTS
=========================================
--- PHASE 1: BOOTSTRAPPING THE MATRIX ---
[SYSTEM] Registered Static Route:  GET    /api/books
[SYSTEM] Registered Static Route:  POST   /api/books
[SYSTEM] Registered Dynamic Route: GET    /api/books/{id}

--- PHASE 2: PROCESSING RAW TCP STRINGS ---

[INBOUND] Parsing: Method='GET', Path='/api/books', Query=''
   [RESPONSE] 200 OK: Returning all books. Applied filters: []

[INBOUND] Parsing: Method='POST', Path='/api/books', Query=''
   [RESPONSE] 201 Created: Saving new book to database.

[INBOUND] Parsing: Method='GET', Path='/api/books/99', Query=''
   [RESPONSE] 200 OK: Returning details for Book ID: 99

[INBOUND] Parsing: Method='GET', Path='/api/books', Query='sort=author&limit=10'
   [RESPONSE] 200 OK: Returning all books. Applied filters: [sort=author&limit=10]
"""
