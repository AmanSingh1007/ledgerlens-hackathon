"""LedgerLens web app — a browser UI over the real extraction pipeline.

Zero dependencies (Python stdlib only). The LLM engine is the same as the
evaluation harness: the Claude Code CLI (`claude -p`), or the Anthropic API
if ANTHROPIC_API_KEY is set.

Run:    python app.py          then open http://localhost:8765
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from agent import run_agent  # noqa: E402
from memory import VendorMemory  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
INVOICE_DIR = os.path.join(ROOT, "data", "invoices")
MEMORY_PATH = os.path.join(ROOT, "webapp_memory.json")

_memory_lock = threading.Lock()

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>LedgerLens</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root { --bg:#0e1116; --panel:#161b22; --edge:#30383f; --text:#e6edf3; --dim:#8b949e;
        --accent:#4cc2ff; --ok:#7ee787; --err:#ff7b72; --warn:#ffc454; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text);
       font:15px/1.5 "Segoe UI",system-ui,sans-serif; }
header { padding:18px 28px; border-bottom:1px solid var(--edge);
         display:flex; align-items:baseline; gap:14px; }
header h1 { margin:0; font-size:20px; }
header span { color:var(--dim); font-size:13px; }
main { display:grid; grid-template-columns:1fr 1fr; gap:18px; padding:18px 28px;
       max-width:1400px; margin:0 auto; }
@media (max-width:900px) { main { grid-template-columns:1fr; } }
.panel { background:var(--panel); border:1px solid var(--edge); border-radius:10px;
         padding:16px; }
.panel h2 { margin:0 0 10px; font-size:14px; text-transform:uppercase;
            letter-spacing:.06em; color:var(--accent); }
textarea { width:100%; height:320px; background:#0b0e13; color:var(--text);
           border:1px solid var(--edge); border-radius:8px; padding:10px;
           font:13px/1.45 Consolas,monospace; resize:vertical; }
select,button { font:14px "Segoe UI",sans-serif; border-radius:8px;
                border:1px solid var(--edge); padding:8px 14px; }
select { background:#0b0e13; color:var(--text); }
button { background:var(--accent); color:#06202e; font-weight:600; cursor:pointer; }
button:disabled { opacity:.5; cursor:wait; }
.row { display:flex; gap:10px; margin:10px 0; align-items:center; flex-wrap:wrap; }
pre { background:#0b0e13; border:1px solid var(--edge); border-radius:8px;
      padding:10px; font:13px/1.45 Consolas,monospace; overflow:auto;
      white-space:pre-wrap; word-break:break-word; margin:8px 0; }
.step { border-left:3px solid var(--edge); padding:6px 12px; margin:8px 0; }
.step b { font-size:13px; text-transform:uppercase; letter-spacing:.05em; }
.step.ok { border-color:var(--ok); } .step.ok b { color:var(--ok); }
.step.err { border-color:var(--err); } .step.err b { color:var(--err); }
.step.info { border-color:var(--accent); } .step.info b { color:var(--accent); }
.step.warn { border-color:var(--warn); } .step.warn b { color:var(--warn); }
.badge { display:inline-block; padding:2px 10px; border-radius:99px; font-size:12px;
         font-weight:600; }
.badge.ok { background:#1c3527; color:var(--ok); }
.badge.warn { background:#3a2d12; color:var(--warn); }
.dim { color:var(--dim); font-size:13px; }
#spin { display:none; color:var(--dim); }
</style></head><body>
<header><h1>LedgerLens</h1>
<span>agentic invoice extraction &middot; deterministic verification &middot; vendor memory</span></header>
<main>
<section class="panel">
  <h2>1 &middot; Invoice document (OCR text)</h2>
  <div class="row">
    <select id="sample"><option value="">— load a sample invoice —</option></select>
    <button id="run">Extract &amp; verify</button>
    <span id="spin">running the agent pipeline&hellip; (10&ndash;40s)</span>
  </div>
  <textarea id="doc" placeholder="Paste OCR'd invoice text here, or pick a sample."></textarea>
  <p class="dim">Tip: process inv_03 then inv_07 (or inv_13 then inv_14) to watch
  vendor memory learn a vendor's quirks and apply them to the next invoice.</p>
</section>
<section class="panel">
  <h2>2 &middot; Agent pipeline &mdash; live trajectory</h2>
  <div id="steps"><p class="dim">The extractor, validator, corrector, and memory
  events will appear here as the agent works.</p></div>
</section>
<section class="panel">
  <h2>3 &middot; Extraction result</h2>
  <div id="verdict"></div>
  <pre id="result">&mdash;</pre>
</section>
<section class="panel">
  <h2>4 &middot; Vendor memory (learned so far)</h2>
  <pre id="memory">&mdash;</pre>
  <p class="dim">Profiles are written only from extractions that pass the
  validator, so a bad parse can never poison future invoices.</p>
</section>
</main>
<script>
const $ = id => document.getElementById(id);

async function loadSamples() {
  const names = await (await fetch('/api/samples')).json();
  for (const n of names) {
    const o = document.createElement('option'); o.value = n; o.textContent = n;
    $('sample').appendChild(o);
  }
}
$('sample').addEventListener('change', async e => {
  if (!e.target.value) return;
  $('doc').value = await (await fetch('/api/sample/' + e.target.value)).text();
});

async function refreshMemory() {
  const m = await (await fetch('/api/memory')).json();
  $('memory').textContent = m.length ? JSON.stringify(m, null, 1)
                                     : 'empty — no vendors learned yet';
}

function addStep(cls, title, body) {
  const d = document.createElement('div');
  d.className = 'step ' + cls;
  const b = document.createElement('b'); b.textContent = title; d.appendChild(b);
  if (body) { const p = document.createElement('pre'); p.textContent = body; d.appendChild(p); }
  $('steps').appendChild(d);
}

function renderTrajectory(traj) {
  $('steps').innerHTML = '';
  for (const ev of traj) {
    if (ev.step === 'memory_read')
      addStep(ev.content ? 'info' : '', 'memory ' + (ev.content ? 'hit' : 'miss'),
              ev.content ? JSON.stringify(ev.content, null, 1) : 'unknown vendor — extracting cold');
    else if (ev.step === 'prompt')
      addStep('', ev.role + ' prompt' + (ev.attempt ? ' (retry ' + ev.attempt + ')' : ''),
              ev.content.length > 400 ? ev.content.slice(0, 400) + ' …' : ev.content);
    else if (ev.step === 'response')
      addStep('', ev.role + ' reply',
              ev.content.length > 400 ? ev.content.slice(0, 400) + ' …' : ev.content);
    else if (ev.step === 'validation')
      ev.errors.length
        ? addStep('err', 'validator: ' + ev.errors.length + ' error(s)', ev.errors.join('\\n'))
        : addStep('ok', 'validator: all arithmetic checks pass', '');
    else if (ev.step === 'memory_write')
      addStep('info', 'memory updated', 'vendor profile stored: ' + ev.vendor);
    else if (ev.step === 'human_review_flag')
      addStep('warn', 'flagged for human review', ev.errors.join('\\n'));
  }
}

$('run').addEventListener('click', async () => {
  const text = $('doc').value.trim();
  if (!text) { alert('Paste an invoice first.'); return; }
  $('run').disabled = true; $('spin').style.display = 'inline';
  $('steps').innerHTML = '<p class="dim">working…</p>';
  $('result').textContent = '—'; $('verdict').innerHTML = '';
  try {
    const r = await fetch('/api/extract', { method: 'POST', body: text });
    const data = await r.json();
    if (data.error) throw new Error(data.error);
    renderTrajectory(data.trajectory);
    const res = data.result;
    $('result').textContent = JSON.stringify(res, null, 2);
    $('verdict').innerHTML = res.needs_human_review
      ? '<span class="badge warn">needs human review</span>'
      : '<span class="badge ok">verified — arithmetic consistent</span>';
    await refreshMemory();
  } catch (e) {
    $('steps').innerHTML = '';
    addStep('err', 'error', String(e.message || e));
  } finally {
    $('run').disabled = false; $('spin').style.display = 'none';
  }
});

loadSamples(); refreshMemory();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._send(200, PAGE, "text/html")
        elif self.path == "/api/samples":
            names = sorted(f[:-4] for f in os.listdir(INVOICE_DIR) if f.endswith(".txt"))
            self._send(200, json.dumps(names))
        elif self.path.startswith("/api/sample/"):
            name = os.path.basename(self.path.rsplit("/", 1)[1])
            path = os.path.join(INVOICE_DIR, name + ".txt")
            if not os.path.isfile(path):
                self._send(404, json.dumps({"error": "no such sample"}))
                return
            with open(path, encoding="utf-8") as f:
                self._send(200, f.read(), "text/plain")
        elif self.path == "/api/memory":
            profiles = []
            if os.path.exists(MEMORY_PATH):
                with open(MEMORY_PATH, encoding="utf-8") as f:
                    profiles = json.load(f)
            self._send(200, json.dumps(profiles))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path != "/api/extract":
            self._send(404, json.dumps({"error": "not found"}))
            return
        length = int(self.headers.get("Content-Length", 0))
        if not 0 < length <= 100_000:
            self._send(400, json.dumps({"error": "document must be 1–100000 bytes"}))
            return
        document = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            with _memory_lock:
                memory = VendorMemory(MEMORY_PATH)
                result, trajectory = run_agent(document, verify=True, memory=memory, judge=False)
            self._send(200, json.dumps({"result": result, "trajectory": trajectory}))
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}))

    def log_message(self, fmt, *args):
        print(f"[web] {args[0] if args else ''}")


def main():
    port = int(os.environ.get("LEDGERLENS_PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"LedgerLens running at http://localhost:{port}  (Ctrl+C to stop)")
    print(f"Engine: {'Anthropic API' if os.environ.get('ANTHROPIC_API_KEY') else 'Claude Code CLI'}")
    server.serve_forever()


if __name__ == "__main__":
    main()
