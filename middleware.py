# Logic & Legacy: The Raw Socket Middleware Engine
# Frameworks like FastAPI and Express lie to you. They make middleware look like magic.
# Today, we bypass FastAPI entirely. We open a raw TCP socket to the Operating System.
# We will prove that a Middleware is nothing but a string filter sitting between 
# the network card and your business logic.

import socket
import time
from typing import Tuple

# ==========================================
# 1. THE BUSINESS LOGIC (The Core)
# ==========================================
def handle_endpoint(path: str) -> str:
    """
    This is the center of the onion. It knows NOTHING about IP addresses, 
    security headers, or HTTP protocols. It only knows data.
    """
    if path == "/api/v1/vault":
        # We return the raw HTTP text string required by the browser.
        return "HTTP/1.1 200 OK\r\n\r\n{'status': 'success', 'data': 'highly sensitive payroll data'}"
    
    return "HTTP/1.1 404 Not Found\r\n\r\n{'error': 'Endpoint missing'}"


# ==========================================
# 2. THE TCP SERVER & MIDDLEWARE PIPELINE
# ==========================================
def boot_raw_server():
    # Open a raw TCP socket to the OS network interface
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('127.0.0.1', 8000))
    server.listen(5)
    
    print("\n[SYSTEM] Raw TCP Server listening on port 8000...")
    print("[SYSTEM] Try opening http://127.0.0.1:8000/api/v1/vault in your browser.")
    print("[SYSTEM] (Or trigger the firewall by changing the blocked_ips list below)\n")

    blocked_ips = ["192.168.1.100", "10.0.0.5"] # The blacklist

    while True:
        # The OS hands us the physical connection and the client's IP
        client_socket, client_address = server.accept()
        ip = client_address[0]
        
        # Read the raw byte stream from the network wire
        raw_bytes = client_socket.recv(1024)
        if not raw_bytes:
            client_socket.close()
            continue
            
        request_string = raw_bytes.decode('utf-8')
        
        # Parse the HTTP request line (e.g., "GET /api/v1/vault HTTP/1.1")
        first_line = request_string.split('\r\n')[0]
        try:
            method, path, protocol = first_line.split(' ')
        except ValueError:
            client_socket.close()
            continue

        # ---------------------------------------------------------
        # MIDDLEWARE LAYER 1: THE INBOUND FIREWALL
        # ---------------------------------------------------------
        # We intercept the request BEFORE it ever reaches the core logic.
        if ip in blocked_ips:
            print(f"[BOUNCER] ❌ BLOCKED malicious request from {ip}")
            response = "HTTP/1.1 403 Forbidden\r\n\r\n{'error': 'IP Banned'}"
            client_socket.sendall(response.encode('utf-8'))
            client_socket.close()
            continue # The core logic is never executed.

        # ---------------------------------------------------------
        # MIDDLEWARE LAYER 2: METRICS TIMING (START)
        # ---------------------------------------------------------
        start_time = time.perf_counter()
        print(f"[METRICS] Inbound {method} request to {path} from {ip}")

        # ---------------------------------------------------------
        # THE CORE EXECUTION
        # ---------------------------------------------------------
        # The request survived the skin of the onion. It hits the core.
        raw_response = handle_endpoint(path)

        # ---------------------------------------------------------
        # MIDDLEWARE LAYER 3: OUTBOUND HEADER INJECTION
        # ---------------------------------------------------------
        # The core is finished. It handed back a response.
        # But before we send it to the browser, we rip it open and inject security.
        headers, body = raw_response.split("\r\n\r\n", 1)
        
        # We mathematically force security headers onto every single response.
        injected_headers = headers + "\r\nX-Frame-Options: DENY\r\nX-Content-Type-Options: nosniff"
        final_response = injected_headers + "\r\n\r\n" + body

        # ---------------------------------------------------------
        # MIDDLEWARE LAYER 2: METRICS TIMING (END)
        # ---------------------------------------------------------
        duration = (time.perf_counter() - start_time) * 1000
        print(f"[METRICS] Outbound response generated in {duration:.2f}ms")

        # Shove the modified string back across the physical wire
        client_socket.sendall(final_response.encode('utf-8'))
        client_socket.close()


if __name__ == "__main__":
    boot_raw_server()

"""
=========================================
EXPECTED TERMINAL OUTPUT
=========================================
[SYSTEM] Raw TCP Server listening on port 8000...
[SYSTEM] Try opening http://127.0.0.1:8000/api/v1/vault in your browser.

[METRICS] Inbound GET request to /api/v1/vault from 127.0.0.1
[METRICS] Outbound response generated in 0.01ms

[BOUNCER] ❌ BLOCKED malicious request from 192.168.1.100
"""
