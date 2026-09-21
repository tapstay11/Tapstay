#!/usr/bin/env python3
"""
TapStay Multi-Worker Reverse Proxy & Round-Robin Load Balancer.
Zero external dependencies: uses Python standard library.

Features:
- Spawns and supervises multiple backend server worker processes
- Distributes incoming HTTP requests via Round-Robin algorithm
- Active background health checks (marks unhealthy workers and fails over)
- Injects load balancer diagnostic headers (X-Load-Balancer, X-Worker-Port)
- Clean shutdown signal handling (SIGINT / SIGTERM)
"""

import http.server
import socketserver
import urllib.request
import urllib.error
import threading
import subprocess
import time
import sys
import os
import signal

LB_PORT = 8080
WORKER_PORTS = [8081, 8082]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class BackendNode:
    def __init__(self, port):
        self.port = port
        self.url = f"http://127.0.0.1:{port}"
        self.is_healthy = True
        self.active_requests = 0
        self.process = None

class LoadBalancerManager:
    def __init__(self, worker_ports):
        self.nodes = [BackendNode(p) for p in worker_ports]
        self._current_idx = 0
        self._lock = threading.Lock()
        self.is_running = True

    def start_workers(self):
        print(f"Starting {len(self.nodes)} backend worker processes...")
        for node in self.nodes:
            cmd = [sys.executable, os.path.join(BASE_DIR, "server.py"), str(node.port)]
            node.process = subprocess.Popen(cmd, cwd=BASE_DIR)
            print(f"  ✓ Spawned worker on port {node.port} (PID: {node.process.pid})")
        # Wait a moment for workers to bind
        time.sleep(1.0)

    def stop_workers(self):
        print("\nStopping backend worker processes...")
        self.is_running = False
        for node in self.nodes:
            if node.process and node.process.poll() is None:
                try:
                    node.process.terminate()
                    node.process.wait(timeout=2)
                except Exception:
                    node.process.kill()

    def get_next_healthy_node(self):
        with self._lock:
            for _ in range(len(self.nodes)):
                node = self.nodes[self._current_idx]
                self._current_idx = (self._current_idx + 1) % len(self.nodes)
                if node.is_healthy:
                    return node
            # Fallback to current node if all marked unhealthy
            return self.nodes[0]

    def health_check_loop(self):
        while self.is_running:
            for node in self.nodes:
                try:
                    req = urllib.request.Request(f"{node.url}/api/stats", headers={"User-Agent": "TapStay-LB-HealthCheck"})
                    with urllib.request.urlopen(req, timeout=1.5) as resp:
                        node.is_healthy = (resp.status == 200)
                except Exception:
                    node.is_healthy = False
            time.sleep(4.0)

LB_MANAGER = None

class LoadBalancerHandler(http.server.BaseHTTPRequestHandler):
    """Proxy HTTP requests to backend workers with round-robin load distribution."""

    def log_message(self, format, *args):
        # Suppress verbose default logging
        pass

    def do_GET(self):
        self.proxy_request("GET")

    def do_POST(self):
        self.proxy_request("POST")

    def do_PUT(self):
        self.proxy_request("PUT")

    def do_DELETE(self):
        self.proxy_request("DELETE")

    def do_OPTIONS(self):
        self.proxy_request("OPTIONS")

    def proxy_request(self, method):
        target_node = LB_MANAGER.get_next_healthy_node()
        target_url = f"{target_node.url}{self.path}"

        headers = {}
        for k, v in self.headers.items():
            if k.lower() not in ("host",):
                headers[k] = v
        headers["X-Forwarded-For"] = self.client_address[0]
        headers["X-Forwarded-Host"] = self.headers.get("Host", f"localhost:{LB_PORT}")

        body = None
        if "Content-Length" in self.headers:
            length = int(self.headers["Content-Length"])
            body = self.rfile.read(length)

        req = urllib.request.Request(target_url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_body = resp.read()
                self.send_response(resp.status)
                for header, val in resp.getheaders():
                    # Pass through response headers
                    if header.lower() not in ("transfer-encoding",):
                        self.send_header(header, val)
                self.send_header("X-Load-Balancer", "TapStay-Cluster")
                self.send_header("X-Worker-Port", str(target_node.port))
                self.end_headers()
                self.wfile.write(resp_body)
        except urllib.error.HTTPError as e:
            err_body = e.read()
            self.send_response(e.code)
            for header, val in e.headers.items():
                if header.lower() not in ("transfer-encoding",):
                    self.send_header(header, val)
            self.send_header("X-Load-Balancer", "TapStay-Cluster")
            self.send_header("X-Worker-Port", str(target_node.port))
            self.end_headers()
            self.wfile.write(err_body)
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(f'{{"error": "Bad Gateway - Worker Unavailable", "details": "{str(e)}"}}'.encode("utf-8"))


class ThreadedLBServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def run_load_balancer(port=LB_PORT):
    global LB_MANAGER
    LB_MANAGER = LoadBalancerManager(WORKER_PORTS)
    LB_MANAGER.start_workers()

    # Start health checking thread
    health_thread = threading.Thread(target=LB_MANAGER.health_check_loop, daemon=True)
    health_thread.start()

    def signal_handler(sig, frame):
        LB_MANAGER.stop_workers()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("=" * 65)
    print("  ✦ TapStay Load Balancer & Reverse Proxy Active ✦")
    print(f"  Front-Facing Load Balancer:  http://localhost:{port}")
    print(f"  Active Workers:             {', '.join([str(p) for p in WORKER_PORTS])}")
    print("=" * 65)

    with ThreadedLBServer(("", port), LoadBalancerHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            signal_handler(None, None)

if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else LB_PORT
    run_load_balancer(p)
