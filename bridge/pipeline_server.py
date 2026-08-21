#!/usr/bin/env python3
"""Pipeline 服务：把文本步骤包成可查询、可取消的后台作业，供前端一键调用。
- POST /pipeline/<step>  body={"pid":"...","model":"glm-4.6"}  → {job_id}
- GET  /pipeline/jobs/<job_id>  → {status: queued|running|awaiting_confirmation|cancelling|cancelled|done|error, log, error}
- POST /pipeline/jobs/<job_id>/cancel → 请求终止作业
- POST /pipeline/jobs/<job_id>/confirm-repair → 用户确认导演问题后继续修正
step ∈ visual-dict | shot-breakdown | unit-gen
纯标准库；作业串行(一次一个)，每项在独立子进程执行，以便真正终止运行中的任务。
启动：python pipeline_server.py  (默认 5280)
"""
from __future__ import annotations
import json, os, subprocess, sys, threading, time, urllib.error, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BRIDGE_DIR = Path(__file__).resolve().parent
STEPS = {
    "extract-setup": [sys.executable, "-u", str(BRIDGE_DIR / "extract_setup.py")],
    "visual-dict": [sys.executable, "-u", str(BRIDGE_DIR / "visual_dict.py")],
    "shot-breakdown": [sys.executable, "-u", str(BRIDGE_DIR / "shot_breakdown.py")],
    "unit-gen": [sys.executable, "-u", str(BRIDGE_DIR / "unit_gen.py")],
}
JOBS: dict[str, dict] = {}
PROCESSES: dict[str, subprocess.Popen[str]] = {}
RUN_LOCK = threading.Lock()  # 保持原有串行语义，避免多项 pipeline 同时改写项目数据。
JOBS_LOCK = threading.Lock()
REPAIR_MARKER = "SHOTCAT_REPAIR_REQUIRED:"
JOBS_FILE = BRIDGE_DIR / "pipeline-jobs.json"
BACKEND = os.getenv("SHOTCAT_BACKEND_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
PIPELINE_HOST = os.getenv("SHOTCAT_PIPELINE_HOST", "127.0.0.1")
PIPELINE_PORT = int(os.getenv("SHOTCAT_PIPELINE_PORT", "5280"))
REVISION_STEP = {
    "extract-setup": "brain",
    "visual-dict": "cast",
    "shot-breakdown": "storyboard",
    "unit-gen": "frames",
}
COMPLETED_STEP = {
    "extract-setup": "cast", "visual-dict": "cast",
    "shot-breakdown": "storyboard", "unit-gen": "frames",
}


def _load_jobs() -> dict[str, dict]:
    try:
        value = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    for job in value.values():
        if isinstance(job, dict) and job.get("status") in {"queued", "running", "cancelling"}:
            job["status"] = "error"
            job["error"] = "Pipeline 服务曾中断；原任务未继续执行，可重新发起。"
    return {str(key): item for key, item in value.items() if isinstance(item, dict)}


def _persist_jobs_locked() -> None:
    temp = JOBS_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(JOBS, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(JOBS_FILE)


def _capture_revision(pid: str, step: str, job_id: str, repair: bool = False) -> str:
    payload = json.dumps({
        "source_step": REVISION_STEP[step],
        "reason": f"{'导演定向修正' if repair else '执行 Pipeline 步骤'}：{step}",
        "source_task_id": job_id,
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{BACKEND}/studio/projects/{pid}/workflow/revisions",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法保存重做前快照，已停止执行：{exc}") from exc
    revision_id = str((body.get("data") or {}).get("id") or "")
    if not revision_id:
        raise RuntimeError("无法保存重做前快照，后端未返回版本编号")
    return revision_id


def _complete_step(pid: str, step: str) -> None:
    payload = json.dumps({"step": COMPLETED_STEP[step]}).encode("utf-8")
    request = urllib.request.Request(
        f"{BACKEND}/studio/projects/{pid}/workflow/complete",
        data=payload, method="POST", headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15):
        return None


JOBS.update(_load_jobs())


def _job_snapshot(job_id: str) -> dict | None:
    """返回可序列化的作业快照，避免 HTTP 线程直接读取正在变化的字典。"""
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None


def _repair_payload(log: str) -> dict | None:
    """从子进程日志末尾读取分镜修正标记，供任务状态和前端确认弹窗使用。"""
    for line in reversed(str(log or "").splitlines()):
        if not line.startswith(REPAIR_MARKER):
            continue
        try:
            value = json.loads(line[len(REPAIR_MARKER):])
        except (json.JSONDecodeError, ValueError):
            return None
        return value if isinstance(value, dict) else None
    return None


def _run(job_id: str, step: str, pid: str, model: str, repair: bool = False):
    """在独立子进程中执行一步 pipeline；取消接口可安全终止该进程。"""
    with RUN_LOCK:
        with JOBS_LOCK:
            job = JOBS[job_id]
            if job.get("cancel_requested"):
                job["status"] = "cancelled"
                _persist_jobs_locked()
                return
            job["status"] = "running"
            _persist_jobs_locked()
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            revision_id = _capture_revision(pid, step, job_id, repair)
            with JOBS_LOCK:
                JOBS[job_id]["revision_id"] = revision_id
                JOBS[job_id].setdefault("revision_ids", []).append(revision_id)
                _persist_jobs_locked()
            command = [*STEPS[step], pid, "--model", model]
            if repair and step == "shot-breakdown":
                command.append("--repair")
            process = subprocess.Popen(
                command,
                cwd=BRIDGE_DIR,
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
            with JOBS_LOCK:
                PROCESSES[job_id] = process
                cancel_now = bool(JOBS[job_id].get("cancel_requested"))
            if cancel_now:
                process.terminate()
            if process.stdout is not None:
                for line in process.stdout:
                    with JOBS_LOCK:
                        JOBS[job_id]["log"] += line
                        _persist_jobs_locked()
            return_code = process.wait()
            with JOBS_LOCK:
                job = JOBS[job_id]
                if job.get("cancel_requested"):
                    job["status"] = "cancelled"
                    job["error"] = "任务已取消"
                elif step == "shot-breakdown" and return_code == 42:
                    payload = _repair_payload(job["log"]) or {}
                    job["status"] = "awaiting_confirmation"
                    job["issues"] = list(payload.get("issues") or [])
                    job["error"] = f"导演校验发现 {payload.get('count') or len(job['issues'])} 个关键问题"
                elif return_code == 0:
                    job["status"] = "done"
                    try:
                        _complete_step(pid, step)
                    except (OSError, urllib.error.URLError):
                        job["log"] += "\n警告：任务已完成，但工作流完成状态回写失败。\n"
                else:
                    job["status"] = "error"
                    job["error"] = job["log"].strip().splitlines()[-1] if job["log"].strip() else f"子进程退出码 {return_code}"
                _persist_jobs_locked()
        except Exception as e:  # noqa: BLE001
            with JOBS_LOCK:
                job = JOBS[job_id]
                if job.get("cancel_requested"):
                    job["status"] = "cancelled"
                    job["error"] = "任务已取消"
                else:
                    job["status"] = "error"
                    job["error"] = f"{type(e).__name__}: {e}"
                _persist_jobs_locked()
        finally:
            with JOBS_LOCK:
                PROCESSES.pop(job_id, None)


def _cancel_job(job_id: str) -> dict | None:
    """登记取消请求；排队任务立即取消，运行任务终止对应子进程。"""
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return None
        if job.get("status") in {"done", "error", "cancelled"}:
            return dict(job)
        job["cancel_requested"] = True
        process = PROCESSES.get(job_id)
        if process is None and job.get("status") in {"queued", "awaiting_confirmation"}:
            job["status"] = "cancelled"
            job["error"] = "任务已取消"
        elif process is not None:
            job["status"] = "cancelling"
        snapshot = dict(job)
        _persist_jobs_locked()
    if process is not None and process.poll() is None:
        process.terminate()
    return snapshot


def _confirm_repair(job_id: str) -> dict | None:
    """把等待确认的分镜任务恢复为排队状态，并在同一任务中启动定向修正。"""
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return None
        if job.get("status") != "awaiting_confirmation":
            return dict(job)
        job["status"] = "queued"
        job["error"] = ""
        job["issues"] = []
        job["repair_round"] = int(job.get("repair_round") or 0) + 1
        step = str(job["step"])
        pid = str(job["pid"])
        model = str(job["model"])
        snapshot = dict(job)
        _persist_jobs_locked()
    threading.Thread(target=_run, args=(job_id, step, pid, model, True), daemon=True).start()
    return snapshot


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        if self.path == "/pipeline/jobs" or self.path.startswith("/pipeline/jobs?"):
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            params = dict(item.split("=", 1) for item in query.split("&") if "=" in item)
            pid = params.get("pid", "")
            with JOBS_LOCK:
                jobs = [dict({"job_id": job_id}, **job) for job_id, job in JOBS.items() if not pid or job.get("pid") == pid]
            return self._send(200, {"items": jobs})
        if self.path.startswith("/pipeline/jobs/"):
            jid = self.path.rsplit("/", 1)[-1]
            job = _job_snapshot(jid)
            return self._send(200 if job else 404, job or {"error": "job not found"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.startswith("/pipeline/jobs/") and self.path.endswith("/cancel"):
            jid = self.path.split("/")[-2]
            job = _cancel_job(jid)
            return self._send(200 if job else 404, job or {"error": "job not found"})
        if self.path.startswith("/pipeline/jobs/") and self.path.endswith("/confirm-repair"):
            jid = self.path.split("/")[-2]
            job = _confirm_repair(jid)
            return self._send(200 if job else 404, job or {"error": "job not found"})
        if not self.path.startswith("/pipeline/"):
            return self._send(404, {"error": "not found"})
        step = self.path.split("/")[-1]
        if step not in STEPS:
            return self._send(400, {"error": f"unknown step {step}"})
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or "{}") if length else {}
        except (json.JSONDecodeError, ValueError):
            return self._send(400, {"error": "invalid JSON body"})
        pid = body.get("pid")
        if not pid:
            return self._send(400, {"error": "pid required"})
        model = body.get("model", "glm-4.6")
        jid = uuid.uuid4().hex
        with JOBS_LOCK:
            JOBS[jid] = {
                "status": "queued", "log": "", "error": "", "step": step, "pid": pid,
                "model": model, "cancel_requested": False, "issues": [], "repair_round": 0,
                "created_at": int(time.time() * 1000),
            }
            _persist_jobs_locked()
        threading.Thread(target=_run, args=(jid, step, pid, model), daemon=True).start()
        self._send(200, {"job_id": jid})

    def log_message(self, *a):  # 静音访问日志
        pass


if __name__ == "__main__":
    print(f"pipeline server on http://{PIPELINE_HOST}:{PIPELINE_PORT}  (steps: {', '.join(STEPS)})")
    ThreadingHTTPServer((PIPELINE_HOST, PIPELINE_PORT), H).serve_forever()
