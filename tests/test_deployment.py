from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import time
import tomllib

import httpx


ROOT = Path(__file__).resolve().parent.parent


def test_netlify_publishes_frontend_without_a_build_step():
    config = tomllib.loads((ROOT / "netlify.toml").read_text(encoding="utf-8"))
    assert config["build"]["command"] == ""
    publish = ROOT / config["build"]["publish"]
    assert publish == ROOT / "frontend"
    for asset in ("index.html", "styles.css", "app.js"):
        assert (publish / asset).is_file()
    assert not (publish / "rx.db").exists()
    assert not (publish / ".env").exists()
    assert "redirects" not in config


def test_render_hosts_python_with_persistent_storage():
    config = json.loads((ROOT / "render.yaml").read_text(encoding="utf-8"))
    service, = config["services"]
    assert service["type"] == "web"
    assert service["runtime"] == "python"
    assert service["plan"] == "starter"
    assert service["numInstances"] == 1
    assert service["buildCommand"] == "pip install -r requirements.txt"
    assert service["startCommand"] == (
        "uvicorn backend.main:app --host 0.0.0.0 --port $PORT "
        "--proxy-headers --forwarded-allow-ips='*'"
    )
    assert service["healthCheckPath"] == "/api/health"
    env = {item["key"]: item["value"] for item in service["envVars"]}
    assert env["DB_PATH"] == "/var/data/rx.db"
    assert service["disk"]["mountPath"] == "/var/data"
    assert service["disk"]["sizeGB"] >= 1
    assert (ROOT / ".python-version").read_text().strip() == "3.12"


def test_live_python_host_routes_https_security_and_restart_persistence(tmp_path):
    # Real Uvicorn processes exercise DB_PATH at startup, not a patched test app.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    public_origin = f"https://127.0.0.1:{port}"
    env = {**os.environ, "DB_PATH": str(tmp_path / "rx.db"),
           "ENABLE_OSM": "false", "ENABLE_DEMO": "true"}
    command = [sys.executable, "-m", "uvicorn", "backend.main:app", "--host",
               "127.0.0.1", "--port", str(port), "--proxy-headers",
               "--forwarded-allow-ips", "127.0.0.1"]
    credentials = {"email": "deployment@example.com", "password": "test-password-123"}
    item = {"drug_id": "metformin-500-tab", "qty": 30}
    address = {"label": "Home", "recipient": "Test Person", "line1": "12 Main Road",
               "line2": "", "city": "Hyderabad", "state": "Telangana", "pincode": "500001"}

    for restart in (False, True):
        with (tmp_path / "server.log").open("a", encoding="utf-8") as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                with httpx.Client(base_url=base_url, timeout=5) as client:
                    deadline = time.monotonic() + 30
                    while True:
                        try:
                            health = client.get("/api/health")
                            if health.status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        if process.poll() is not None or time.monotonic() >= deadline:
                            raise AssertionError((tmp_path / "server.log").read_text())
                        time.sleep(0.1)
                    assert health.headers["content-type"].startswith("application/json")
                    assert health.json()["ok"] is True
                    assert client.get("/").status_code == 200
                    assert "python-host-7" in client.get("/").text
                    assert client.get("/app.js?v=python-host-7").status_code == 200
                    assert client.get("/styles.css?v=python-host-7").status_code == 200
                    assert client.get("/api/drugs/search", params={"q": "metformin"}).json()
                    assert len(client.get("/api/drugs").json()) >= 27
                    assert len(client.get("/api/drugs?liquids_only=true").json()) >= 6

                    # Simulate TLS termination by the explicitly trusted local proxy.
                    client.headers.update({"X-Forwarded-Proto": "https", "Origin": public_origin})
                    endpoint = "/api/auth/login" if restart else "/api/auth/register"
                    response = client.post(endpoint, json=credentials)
                    assert response.status_code == (200 if restart else 201), response.text
                    cookie = response.headers["set-cookie"]
                    for flag in ("Secure", "HttpOnly", "SameSite=strict"):
                        assert flag in cookie
                    # HTTP test transport cannot send Secure cookies automatically.
                    client.headers["Cookie"] = cookie.split(";", 1)[0]
                    assert client.get("/api/auth/me").status_code == 200
                    assert client.post("/api/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403
                    if not restart:
                        assert client.put("/api/basket", json=item).status_code == 200
                        assert client.post("/api/addresses", json=address).status_code == 201
                    assert client.get("/api/basket").json()[0]["qty"] == 30
                    assert client.get("/api/addresses").json()[0]["line1"] == address["line1"]
                    if not restart:
                        stream = client.get("/api/prices/stream", params={
                            **item, "lat": 17.38, "lng": 78.48})
                        assert stream.status_code == 200
                        assert stream.headers["content-type"].startswith("text/event-stream")
                        for event in ("meta", "result", "done"):
                            assert f"event: {event}\n" in stream.text
                        assert client.post("/api/auth/logout").status_code == 200
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)