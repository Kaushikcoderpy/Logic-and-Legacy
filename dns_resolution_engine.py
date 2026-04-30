# Logic & Legacy: DNS Resolution Architecture
# Demonstrates three tiers of DNS resolution in Python:
# 1. Synchronous OS-level (socket)
# 2. Deep Record Analysis (dnspython)
# 3. High-Concurrency Asynchronous (aiodns)
#
# Requirements:
# pip install dnspython aiodns

import socket
import asyncio
import time

try:
    import dns.resolver
except ImportError:
    print("[WARNING] dnspython not installed. Run: pip install dnspython")

try:
    import aiodns
except ImportError:
    print("[WARNING] aiodns not installed. Run: pip install aiodns")


# ==========================================
# TIER 1: THE NATIVE SHORTCUT (Built-in)
# ==========================================
def resolve_native_socket(domain: str):
    """
    Uses the underlying Operating System's DNS resolver.
    Blocks the thread. Excellent for simple health checks.
    """
    print(f"\n--- TIER 1: Native Socket Resolution ({domain}) ---")
    try:
        # Resolves A record (IPv4)
        ip_address = socket.gethostbyname(domain)
        print(f"[✅ SUCCESS] IPv4 Address: {ip_address}")
    except socket.gaierror as e:
        print(f"[❌ FAILED] OS could not resolve {domain}: {e}")


# ==========================================
# TIER 2: THE ARCHITECT'S TOOLKIT (dnspython)
# ==========================================
def resolve_advanced_records(domain: str):
    """
    Uses the industry-standard dnspython library to query specific
    DNS records like MX (Mail Exchange) and TXT (Text/SPF rules).
    """
    print(f"\n--- TIER 2: Deep Record Analysis ({domain}) ---")
    try:
        # 1. Fetching MX Records (Who handles the email for this domain?)
        mx_answers = dns.resolver.resolve(domain, 'MX')
        print("[📧 MX RECORDS]")
        for rdata in mx_answers:
            print(f"  - Priority {rdata.preference}: {rdata.exchange}")

        # 2. Fetching TXT Records (Security policies, SPF, DKIM)
        txt_answers = dns.resolver.resolve(domain, 'TXT')
        print("[🛡️ TXT RECORDS]")
        for rdata in txt_answers:
            print(f"  - {rdata.strings[0].decode('utf-8')[:80]}...") # Truncating for readability

    except dns.resolver.NoAnswer:
        print(f"[❌ FAILED] No records found for {domain}.")
    except dns.resolver.NXDOMAIN:
        print(f"[❌ FAILED] Domain {domain} does not exist.")
    except Exception as e:
        print(f"[❌ FAILED] Exception: {e}")


# ==========================================
# TIER 3: THE ASYNCHRONOUS SWARM (aiodns)
# ==========================================
async def resolve_async_swarm(domains: list):
    """
    Uses aiodns to resolve thousands of domains concurrently without 
    blocking the Python Event Loop. Critical for web crawlers.
    """
    print(f"\n--- TIER 3: High-Concurrency Async Swarm ---")
    
    # Initialize the asynchronous DNS resolver
    resolver = aiodns.DNSResolver()

    async def fetch_ip(domain):
        try:
            # Query the 'A' record asynchronously
            result = await resolver.query(domain, 'A')
            ip = result[0].host
            print(f"  [✅] {domain:<20} -> {ip}")
            return ip
        except aiodns.error.DNSError as e:
            print(f"  [❌] {domain:<20} -> Failed: {e.args[1]}")

    start_time = time.perf_counter()
    
    # Gather and execute all tasks simultaneously
    tasks = [fetch_ip(domain) for domain in domains]
    await asyncio.gather(*tasks)
    
    duration = time.perf_counter() - start_time
    print(f"[SYSTEM] Swarm completed in {duration * 1000:.2f} ms")


# ==========================================
# EXECUTION
# ==========================================
if __name__ == "__main__":
    target_domain = "logicandlegacy.com"
    
    # 1. Basic Ping
    resolve_native_socket(target_domain)
    
    # 2. Advanced Security/Email Recon
    resolve_advanced_records(target_domain)
    
    # 3. High-Speed Asynchronous Batch
    mass_domains = [
        "github.com", "python.org", "cloudflare.com", 
        "amazon.com", "fake-domain-that-fails.xyz"
    ]
    asyncio.run(resolve_async_swarm(mass_domains))

"""
EXPECTED OUTPUT (Proof of Concept):
--- TIER 1: Native Socket Resolution (logicandlegacy.com) ---
[✅ SUCCESS] IPv4 Address: 192.0.2.42

--- TIER 2: Deep Record Analysis (logicandlegacy.com) ---
[📧 MX RECORDS]
  - Priority 10: mail.logicandlegacy.com.
[🛡️ TXT RECORDS]
  - v=spf1 include:_spf.google.com ~all...

--- TIER 3: High-Concurrency Async Swarm ---
  [✅] cloudflare.com       -> 104.21.60.40
  [✅] github.com           -> 140.82.112.3
  [✅] amazon.com           -> 52.119.168.48
  [✅] python.org           -> 151.101.129.223
  [❌] fake-domain-that-fails.xyz -> Failed: Domain name not found
[SYSTEM] Swarm completed in 45.12 ms
"""
