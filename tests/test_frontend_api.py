import shutil
import subprocess
from pathlib import Path

import pytest


def test_frontend_api_reports_html_and_preserves_json_errors():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to execute the frontend API helper")
    app = Path(__file__).resolve().parent.parent / "frontend" / "app.js"
    # Execute the actual helper without requiring a browser DOM or new dependencies.
    script = r'''
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const source = fs.readFileSync(process.argv[1], "utf8");
const helper = source.slice(source.indexOf("  async function api("), source.indexOf("  const safeLink"));
const context = vm.createContext({ Response, state: { user: null }, updateAccount() {} });
vm.runInContext(helper, context);
(async () => {
  for (const status of [200, 404, 502]) {
    context.fetch = async () => new Response("<!DOCTYPE html><html></html>", {
      status, headers: { "Content-Type": "text/html" }
    });
    await assert.rejects(context.api("/api/drugs"), /Python backend.*Netlify/);
  }
  context.fetch = async () => new Response('{"ok":true}', { headers: { "Content-Type": "application/json; charset=utf-8" } });
  assert.equal((await context.api("/api/health")).ok, true);
  context.fetch = async () => new Response('{"detail":"Invalid credentials"}', { status: 401, headers: { "Content-Type": "application/json" } });
  await assert.rejects(context.api("/api/auth/login", "POST", {}), /Invalid credentials/);
  context.fetch = async () => new Response("broken", { headers: { "Content-Type": "application/json" } });
  await assert.rejects(context.api("/api/drugs"), /invalid JSON/);
  context.fetch = async () => { throw new Error("network error"); };
  await assert.rejects(context.api("/api/health"), /Could not reach the API server/);
  assert.ok(source.includes('await api(`/api/drugs/search?q='));
  assert.ok(source.includes('await api("/api/health")'));
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, "-e", script, str(app)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr