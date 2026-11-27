"""Serve privately on localhost and fetch the original IK2ANE workbook on demand."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
SOURCE = "https://www.ik2ane.it/pontixls.xls"
MAX_BYTES = 8 * 1024 * 1024
APP_PATHS = {"/", "/index.html", "/ponti.html", "/data/dx-spots.json"}


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_HEAD(self):
        if urlsplit(self.path).path in APP_PATHS:
            super().do_HEAD()
        else:
            self.send_error(404)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in APP_PATHS:
            super().do_GET()
        elif path == "/api/pontixls":
            self.send_workbook()
        else:
            self.send_error(404)

    def send_workbook(self):
        headers = {}
        previous_date = self.headers.get("If-Modified-Since")
        if previous_date:
            headers["If-Modified-Since"] = previous_date
        try:
            with urlopen(Request(SOURCE, headers=headers), timeout=12) as response:
                modified = response.headers.get("Last-Modified")
                if modified and modified == previous_date:
                    self.send_response(304)
                    self.end_headers()
                    return
                workbook = response.read(MAX_BYTES + 1)
        except HTTPError as error:
            if error.code == 304:
                self.send_response(304)
                self.end_headers()
            else:
                self.send_error(502, "IK2ANE non raggiungibile")
            return
        except (URLError, TimeoutError, OSError):
            self.send_error(502, "IK2ANE non raggiungibile")
            return

        if len(workbook) > MAX_BYTES or not workbook.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
            self.send_error(502, "Foglio XLS non valido")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.ms-excel")
        self.send_header("Content-Length", str(len(workbook)))
        self.send_header("Cache-Control", "no-store")
        if modified:
            self.send_header("Last-Modified", modified)
        self.end_headers()
        self.wfile.write(workbook)


if __name__ == "__main__":
    with ThreadingHTTPServer(("127.0.0.1", 8080), AppHandler) as server:
        print("Apri http://localhost:8080", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
