import json
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = os.environ.get('APP_VERSION', 'unknown')
POD = os.environ.get('HOSTNAME', os.uname().nodename)
PORT = int(os.environ.get('PORT', '8080'))
ready = threading.Event()
ready.set()
stopping = threading.Event()

class Server(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True
    allow_reuse_address = True

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def send_json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):
        if self.path == '/':
            self.send_json(200, {'message': 'hello', 'version': VERSION, 'pod': POD})
        elif self.path == '/live':
            self.send_json(200, {'live': True})
        elif self.path == '/ready':
            state = ready.is_set() and not stopping.is_set()
            self.send_json(200 if state else 503, {'ready': state})
        else:
            self.send_json(404, {'error': 'not found'})

    def do_POST(self):
        if self.path == '/unready':
            ready.clear()
            self.send_json(200, {'ready': False})
        elif self.path == '/ready-on':
            if not stopping.is_set():
                ready.set()
            self.send_json(200, {'ready': ready.is_set()})
        else:
            self.send_json(404, {'error': 'not found'})

    def log_message(self, fmt, *args):
        print(f'{time.strftime("%Y-%m-%dT%H:%M:%S")} {self.client_address[0]} {fmt % args}', flush=True)


def main():
    server = Server(('0.0.0.0', PORT), Handler)

    def terminate(signum, frame):
        # A signal handler must not call server.shutdown() on the serving thread.
        stopping.set()
        ready.clear()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    print(f'listening on {PORT}, version={VERSION}, pod={POD}', flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()  # waits for active non-daemon request handlers
        print('graceful shutdown finished', flush=True)

if __name__ == '__main__':
    main()
