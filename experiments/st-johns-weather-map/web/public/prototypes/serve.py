"""PROTOTYPE server for shell.html: static files from this directory plus a
/api proxy to the live API at localhost:8000 (the API sends no CORS header).
Run: python3 serve.py  then open http://localhost:5199/shell.html
"""
import http.server, urllib.request, os, sys
API = os.environ.get("WEATHER_API", "http://localhost:8000")
PORT = int(os.environ.get("PORT", "5199"))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

class H(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith("/api/"):
            return super().do_GET()
        try:
            with urllib.request.urlopen(API + self.path, timeout=60) as r:
                body = r.read()
                self.send_response(r.status)
                for k, v in r.headers.items():
                    if k.lower() in ("content-type",) or k.lower().startswith("x-weather-"):
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body)
        except urllib.error.HTTPError as e:
            body = e.read(); self.send_response(e.code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        except Exception as e:
            self.send_error(502, str(e))
    def log_message(self, *a): pass

print(f"prototype at http://localhost:{PORT}/shell.html  (api -> {API})", flush=True)
http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
