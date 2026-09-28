"""Exercise a truncated HTTPS response locally, with no provider calls or secrets."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from pathlib import Path
import ssl
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread


class TruncatedResponse(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.send_header("Content-Length", "100")
        self.end_headers()
        self.wfile.write(b"{")

    def log_message(self, *args):
        pass


with TemporaryDirectory() as directory:
    root = Path(directory)
    cert, key, frame = root / "cert.pem", root / "key.pem", root / "frame.jpg"
    frame.write_bytes(b"\xff\xd8\xff\xd9")
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
        "-keyout", str(key), "-out", str(cert),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    with HTTPServer(("127.0.0.1", 0), TruncatedResponse) as server:
        server.socket = context.wrap_socket(server.socket, server_side=True)
        worker = Thread(target=server.handle_request, daemon=True)
        worker.start()
        subprocess.run([
            sys.executable, "-c",
            "from pathlib import Path; from foxcam.classify import classify; import sys; "
            "assert classify('nous/truncated', [Path(sys.argv[1])] * 4) == ('unclassified', 0.0)",
            str(frame),
        ], check=True, timeout=10, env=os.environ | {
            "SSL_CERT_FILE": str(cert), "NOUS_API_KEY": "local-check-no-secret",
            "NOUS_BASE_URL": f"https://localhost:{server.server_port}",
        })
        worker.join(timeout=2)
print("Truncated HTTPS response: unclassified, confidence=0.0 (PASS)")
