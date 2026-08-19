"""UI launcher.

A small page to pick a bank (dropdown or type a URL), open its portal, and run the
automated login → OTP → statement-download flow, showing live per-stage progress and a
link to the downloaded PDF.

The run is kicked off as a background task and reported through a job registry, so the
browser can poll `/progress/{job_id}` and draw a real progress bar instead of blocking on
a synchronous POST for the ~10s the automation takes.
"""

from __future__ import annotations

import asyncio
import glob
import json
import os
import re
import time
import uuid
from pathlib import Path

import yaml
from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from ..banks.registry import BANKS, bank_url
from ..harness.agent import run_job

_ROOT = Path(__file__).resolve().parents[1]
_CFG = yaml.safe_load((_ROOT / "config.yaml").read_text(encoding="utf-8"))
_BANKS_BASE = f"http://{_CFG['banks']['host']}:{_CFG['banks']['port']}"

app = FastAPI(title="Bank Statement Agent — Launcher")

# --- job registry -----------------------------------------------------------------------
# Single-process, in-memory: jobs live for seconds and nothing needs to survive a restart.
_STAGE_LABELS = {
    "login": "Log in to the portal",
    "otp": "Read the one-time code from email",
    "statement": "Download the latest statement",
}
# Bar position for each (stage, state). "running" lands partway so the bar advances the
# moment a stage begins, rather than sitting still until it completes.
_PCT = {
    ("login", "running"): 10, ("login", "done"): 33,
    ("otp", "running"): 45, ("otp", "done"): 66,
    ("statement", "running"): 80, ("statement", "done"): 100,
}
_JOBS: dict[str, dict] = {}
_TASKS: set[asyncio.Task] = set()      # strong refs; without these tasks can be GC'd mid-run
_MAX_JOBS = 50


def _new_job(bank: str, user: str) -> dict:
    if len(_JOBS) >= _MAX_JOBS:        # prune oldest; this is a dev tool, not a queue
        for stale in sorted(_JOBS, key=lambda k: _JOBS[k]["started"])[:_MAX_JOBS // 2]:
            _JOBS.pop(stale, None)
    job = {
        "id": uuid.uuid4().hex[:12],
        "bank": bank,
        "user": user,
        "state": "running",                                  # running | done | error
        "stages": {s: "pending" for s in _STAGE_LABELS},     # pending | running | done | failed
        "percent": 0,
        "detail": "starting browser…",
        "started": time.time(),
        "result": None,
    }
    _JOBS[job["id"]] = job
    return job


async def _run_and_record(job: dict) -> None:
    def on_progress(stage: str, state: str, detail: str = "") -> None:
        job["stages"][stage] = state
        job["percent"] = _PCT.get((stage, state), job["percent"])
        job["detail"] = detail or _STAGE_LABELS.get(stage, stage)

    try:
        result = await run_job(job["bank"], job["user"], _CFG, headless=True,
                               on_progress=on_progress)
        job["result"] = {
            "status": result.status,
            "stage_reached": result.stage_reached,
            "reason": result.reason,
            "has_file": bool(result.statement_path),
            "duration_ms": result.duration_ms,
        }
        job["percent"] = 100 if result.status == "SUCCESS" else job["percent"]
        job["state"] = "done"
    except Exception as exc:            # surface crashes in the UI instead of a dead bar
        job["state"] = "error"
        job["detail"] = f"{type(exc).__name__}: {exc}"
    finally:
        job["elapsed"] = round(time.time() - job["started"], 1)


# --- page -------------------------------------------------------------------------------
# Placeholders are __NAME__ and substituted with str.replace, not str.format — the CSS and
# JS below are full of braces and escaping every one of them is a needless hazard.
_PAGE = """
<!doctype html><html><head><meta charset="utf-8"><title>Statement Agent</title>
<style>
 body{font-family:system-ui,Arial;background:#0f172a;color:#e2e8f0;margin:0}
 main{max-width:640px;margin:48px auto;padding:0 20px}
 h1{color:#38bdf8} label{display:block;margin:16px 0 4px}
 select,input{width:100%;padding:10px;border-radius:8px;border:1px solid #334155;background:#1e293b;color:#e2e8f0}
 .row{display:flex;gap:10px} .row>*{flex:1}
 button,.btn{margin-top:18px;padding:11px 18px;border:0;border-radius:8px;background:#22c55e;color:#04210f;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block;text-align:center}
 button[disabled]{opacity:.5;cursor:not-allowed}
 .ghost{background:#334155;color:#e2e8f0}
 .result{margin-top:24px;padding:16px;border-radius:10px;background:#1e293b}
 .ok{color:#22c55e} .bad{color:#f87171} a{color:#38bdf8}

 /* progress */
 .panel{margin-top:24px;padding:16px 18px;border-radius:10px;background:#1e293b}
 .track{height:10px;border-radius:999px;background:#334155;overflow:hidden}
 .fill{height:100%;width:0;border-radius:999px;background:linear-gradient(90deg,#38bdf8,#22c55e);
       transition:width .45s cubic-bezier(.4,0,.2,1)}
 .fill.bad{background:#f87171}
 .steps{list-style:none;padding:0;margin:16px 0 0}
 .steps li{display:flex;align-items:center;gap:10px;padding:5px 0;color:#94a3b8;font-size:15px}
 .steps li .dot{width:9px;height:9px;border-radius:50%;background:#475569;flex:0 0 auto}
 .steps li.running{color:#e2e8f0} .steps li.running .dot{background:#38bdf8;animation:pulse 1s infinite}
 .steps li.done{color:#22c55e} .steps li.done .dot{background:#22c55e}
 .steps li.failed{color:#f87171} .steps li.failed .dot{background:#f87171}
 @keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
 .note{color:#94a3b8;font-size:13px;margin:12px 0 0}
</style></head><body><main>
 <h1>Bank Statement Agent</h1>
 <p>Pick a bank portal, open it, or run the automated login + OTP + statement download.</p>
 <p>Doing a manual login via <b>Open portal</b>? The OTP goes to the mailbox for this user —
    <a href="/mailbox" target="_blank">📬 open the Mailbox</a> to read the current code.</p>
 <form id="form" method="post" action="/run">
   <label>Bank portal</label>
   <select name="bank" id="bank" onchange="sync()">
     __OPTIONS__
   </select>
   <label>…or paste a portal link</label>
   <input id="url" name="url" value="__FIRST_URL__" oninput="document.getElementById('open').href=this.value">
   <label>User</label>
   <input name="user" id="user" value="user1">
   <div class="row">
     <a class="btn ghost" id="open" href="__FIRST_URL__" target="_blank">Open portal</a>
     <button type="submit" id="go">Run automation</button>
   </div>
 </form>

 <div class="panel" id="progress" hidden>
   <div class="track"><div class="fill" id="fill"></div></div>
   <ul class="steps">
     <li id="st-login"><span class="dot"></span>Log in to the portal</li>
     <li id="st-otp"><span class="dot"></span>Read the one-time code from email</li>
     <li id="st-statement"><span class="dot"></span>Download the latest statement</li>
   </ul>
   <p class="note" id="detail"></p>
 </div>

 <div id="result"></div>
</main>
<script>
 const base = "__BANKS_BASE__";
 function sync(){
   const id = document.getElementById('bank').value;
   const u = base + "/bank/" + id + "/";
   document.getElementById('url').value = u;
   document.getElementById('open').href = u;
 }

 const $ = (id) => document.getElementById(id);
 let timer = null;

 function paint(job){
   $('fill').style.width = (job.percent || 0) + "%";
   $('fill').classList.toggle('bad', job.state === 'error' ||
       (job.result && job.result.status !== 'SUCCESS'));
   for (const [stage, state] of Object.entries(job.stages || {})){
     const li = $('st-' + stage);
     if (li) li.className = state === 'pending' ? '' : state;
   }
   const secs = ((Date.now() - startedAt) / 1000).toFixed(1);
   $('detail').textContent = (job.detail || '') + "  ·  " + secs + "s";
 }

 function finish(job){
   clearInterval(timer); timer = null;
   $('go').disabled = false;
   const r = job.result;
   if (job.state === 'error' || !r){
     $('result').innerHTML =
       '<div class="result"><h3 class="bad">ERROR</h3><p>' + (job.detail || 'run failed') + '</p></div>';
     return;
   }
   const cls = r.status === 'SUCCESS' ? 'ok' : 'bad';
   const link = r.has_file
     ? '<p><a href="/file?bank=' + encodeURIComponent(job.bank) +
       '&user=' + encodeURIComponent(job.user) + '">Download the fetched statement PDF</a></p>'
     : '';
   $('result').innerHTML =
     '<div class="result"><h3 class="' + cls + '">' + r.status + '</h3>' +
     '<p>' + job.bank + ' / ' + job.user + ' — stage <b>' + r.stage_reached + '</b>' +
     ' · ' + (r.duration_ms / 1000).toFixed(1) + 's</p>' +
     '<p>' + r.reason + '</p>' + link + '</div>';
 }

 let startedAt = 0;

 async function poll(id){
   try {
     const res = await fetch('/progress/' + id);
     if (!res.ok) throw new Error('lost the job');
     const job = await res.json();
     paint(job);
     if (job.state !== 'running') finish(job);
   } catch (e) {
     clearInterval(timer); timer = null; $('go').disabled = false;
     $('result').innerHTML = '<div class="result"><h3 class="bad">ERROR</h3><p>' + e + '</p></div>';
   }
 }

 $('form').addEventListener('submit', async (ev) => {
   ev.preventDefault();
   $('go').disabled = true;
   $('result').innerHTML = '';
   $('progress').hidden = false;
   startedAt = Date.now();
   for (const s of ['login','otp','statement']) $('st-' + s).className = '';
   $('fill').style.width = '0%'; $('fill').classList.remove('bad');
   $('detail').textContent = 'starting…';

   const body = new URLSearchParams({bank: $('bank').value, user: $('user').value});
   const res = await fetch('/run', {method: 'POST', body});
   const {job_id} = await res.json();
   poll(job_id);
   timer = setInterval(() => poll(job_id), 400);
 });
</script>
</body></html>
"""


_MAILBOX = """
<!doctype html><html><head><meta charset="utf-8"><title>Mailbox</title>
<meta http-equiv="refresh" content="4">
<style>
 body{{font-family:system-ui,Arial;background:#0f172a;color:#e2e8f0;margin:0}}
 main{{max-width:680px;margin:40px auto;padding:0 20px}}
 h1{{color:#38bdf8}} table{{width:100%;border-collapse:collapse;margin-top:16px}}
 td,th{{border:1px solid #334155;padding:10px;text-align:left}} a{{color:#38bdf8}}
 .note{{color:#94a3b8;font-size:14px}}
</style></head><body><main>
 <h1>📬 Mailbox <span class="note">(backend: {backend}, auto-refresh 4s)</span></h1>
 <p class="note">{caption}</p>
 <table><tr><th>OTP</th><th>Bank</th><th>To</th><th>Time</th></tr>{rows}</table>
 <p><a href="/">← back to launcher</a></p>
</main></body></html>
"""


def _options() -> str:
    return "".join(
        f'<option value="{b.id}">{b.name} — {b.variant} ({b.id})</option>'
        for b in BANKS.values()
    )


def _page() -> str:
    first = next(iter(BANKS))
    return (_PAGE
            .replace("__OPTIONS__", _options())
            .replace("__FIRST_URL__", bank_url(_BANKS_BASE, first))
            .replace("__BANKS_BASE__", _BANKS_BASE))


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(_page())


@app.post("/run")
async def run(bank: str = Form(...), user: str = Form("user1")):
    """Start a job and return its id immediately; progress is polled from /progress."""
    job = _new_job(bank, user)
    task = asyncio.create_task(_run_and_record(job))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return JSONResponse({"job_id": job["id"]})


@app.get("/progress/{job_id}")
def progress(job_id: str):
    job = _JOBS.get(job_id)
    if job is None:
        return JSONResponse({"error": "unknown job"}, status_code=404)
    return JSONResponse(job)


@app.get("/mailbox", response_class=HTMLResponse)
def mailbox():
    """Show recent OTP emails from the local mailbox so manual logins can read the code.
    Auto-refreshes every few seconds. Only meaningful when mail.backend == 'local' — on the
    gmail backend the codes live in the real inbox, not here."""
    backend = _CFG["mail"]["backend"]
    maildir = _ROOT / _CFG["mail"]["maildir"]
    files = sorted(glob.glob(str(maildir / "*" / "*.json")), key=os.path.getmtime, reverse=True)[:25]
    rows = ""
    for f in files:
        m = json.loads(Path(f).read_text(encoding="utf-8"))
        match = re.search(r"\b(\d{4,8})\b", m["body"])
        code = match.group(1) if match else "?"
        when = time.strftime("%H:%M:%S", time.localtime(m["ts"]))
        rows += (f'<tr><td style="font-size:22px;font-weight:700;color:#22c55e">{code}</td>'
                 f'<td>{m["bank"]}</td><td>{m["to"]}</td><td>{when}</td></tr>')
    if not rows:
        rows = '<tr><td colspan="4">No OTP emails yet — log in to a bank to generate one.</td></tr>'
    caption = ("OTP emails delivered locally. Newest first. Use the top code for a manual login."
               if backend == "local" else
               "⚠️ mail.backend is 'gmail' — new codes are delivered to the real inbox, not here. "
               "Anything below is left over from an earlier local-backend run.")
    return HTMLResponse(_MAILBOX.format(rows=rows, backend=backend, caption=caption))


@app.get("/file")
def file(bank: str, user: str):
    folder = _ROOT / _CFG["downloads_dir"] / bank / user
    pdfs = sorted(folder.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pdfs:
        return HTMLResponse("no statement downloaded yet", status_code=404)
    return FileResponse(str(pdfs[0]), media_type="application/pdf", filename=pdfs[0].name)
