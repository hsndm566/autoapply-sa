#!/usr/bin/env python3
"""task_queue.py — serial governor for a SLOW machine.

RULE (user): never run >1 heavy task at a time. Heavy = web scraping, CV tailoring
batch, GitHub push, email monitoring. When one runs, QUEUE the rest and wait. Ping
Telegram on START and FINISH. No stacking (machine hangs). If a task runs >5 min with
NO output, KILL it, log 'timed-out' in session-state.md, retry a LIGHTER version.
Speed is not the goal. Completion is.

Usage:
  from task_queue import heavy, run_cmd, put, drain
  heavy("scrape", my_scrape_fn, args=(), lighter=my_light_fn)
  run_cmd("push", "git push", lighter_cmd="git push --no-verify")
  put(("label", fn, "fn", lighter_fn)); drain()   # serial queue
"""
import os, time, threading, subprocess, datetime, queue as _queue

BASE = os.path.dirname(os.path.abspath(__file__))
SESSION = os.path.join(BASE, "system", "session-state.md")
Q = _queue.Queue()
HEAVY_TIMEOUT = 300  # 5 min, no-output = kill


def _tg(msg):
    try:
        import orchestrator as O
        O.tg(msg)
    except Exception:
        pass


def _log_timeout(label):
    """Append a timed-out line to session-state.md (create if missing)."""
    try:
        os.makedirs(os.path.dirname(SESSION), exist_ok=True)
        if not os.path.exists(SESSION):
            open(SESSION, "w", encoding="utf-8").write("# SESSION STATE\n\n## Log\n")
        with open(SESSION, "a", encoding="utf-8") as f:
            f.write(f"- {datetime.date.today().isoformat()} | HEAVY TASK '{label}' TIMED-OUT (>5min no output) -> killed, retried lighter version.\n")
    except Exception:
        pass


class _OutputWatcher(threading.Thread):
    """Watches a subprocess; if no stdout for HEAVY_TIMEOUT, flags expired."""
    def __init__(self, proc, label):
        super().__init__(daemon=True)
        self.proc = proc
        self.label = label
        self.last = time.time()

    def run(self):
        try:
            for _ in self.proc.stdout:
                self.last = time.time()
        except Exception:
            pass

    def expired(self):
        return time.time() - self.last > HEAVY_TIMEOUT


def heavy(label, fn, args=(), kwargs=None, lighter=None):
    """Run ONE heavy task with start/finish pings + timeout watchdog.
    If it times out, kill, log, and run `lighter` if provided."""
    kwargs = kwargs or {}
    _tg(f"HEAVY START: {label}")
    t0 = time.time()
    try:
        res = [None]; err = [None]
        def _run():
            try:
                res[0] = fn(*args, **kwargs)
            except Exception as e:
                err[0] = e
        th = threading.Thread(target=_run, daemon=True)
        th.start()
        while th.is_alive():
            if time.time() - t0 > HEAVY_TIMEOUT:
                _tg(f"HEAVY TIMEOUT: {label} (>5min) - killing")
                _log_timeout(label)
                if lighter:
                    _tg(f"Retrying LIGHTER: {label}")
                    return lighter(*args, **(kwargs or {}))
                return None
            time.sleep(2)
        if err[0]:
            raise err[0]
        _tg(f"HEAVY DONE: {label} ({int(time.time()-t0)}s)")
        return res[0]
    except Exception as e:
        _tg(f"HEAVY FAILED: {label} | {type(e).__name__}: {e}")
        if lighter:
            _tg(f"Retrying LIGHTER: {label}")
            try:
                return lighter(*args, **(kwargs or {}))
            except Exception as e2:
                _tg(f"LIGHTER FAILED: {label} | {e2}")
        return None


def run_cmd(label, cmd, lighter_cmd=None):
    """Heavy shell command (scrape/push/monitor). True no-output watchdog."""
    _tg(f"HEAVY START: {label}")
    t0 = time.time()
    try:
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        watcher = _OutputWatcher(proc, label)
        watcher.start()
        while proc.poll() is None:
            if watcher.expired():
                proc.kill()
                _tg(f"HEAVY TIMEOUT: {label} (>5min no output) - killed")
                _log_timeout(label)
                if lighter_cmd:
                    _tg(f"Retrying LIGHTER: {label}")
                    return run_cmd(label + " (light)", lighter_cmd)
                return None
            time.sleep(3)
        out, _ = proc.communicate()
        _tg(f"HEAVY DONE: {label} ({int(time.time()-t0)}s)")
        return out
    except Exception as e:
        _tg(f"HEAVY FAILED: {label} | {e}")
        return None


def put(item):
    """Queue a heavy task: tuple (label, target, kind['fn'|'cmd'], lighter)."""
    Q.put(item)


def drain():
    """Run queued heavy tasks ONE AT A TIME (serial)."""
    while not Q.empty():
        label, target, kind, lighter = Q.get()
        if kind == "cmd":
            run_cmd(label, target, lighter)
        else:
            heavy(label, target, lighter=lighter)


if __name__ == "__main__":
    def fast():
        time.sleep(1); return "ok"
    def slow_timeout():
        time.sleep(400); return "never"
    def light():
        return "light-ok"
    print("r1:", heavy("test-fast", fast))
    print("r2:", heavy("test-timeout", slow_timeout, lighter=light))
    print("done (serial, no stacking)")
