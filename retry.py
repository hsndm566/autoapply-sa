#!/usr/bin/env python3
"""
retry.py — shared retry + backoff + dead-letter for ALL external calls.
Wraps Groq/DeepSeek/SMTP/Browserbase. On exhaustion -> dead_letter, not silent drop.
"""
import time, random, functools, traceback

def with_retry(max_attempts=4, base_delay=2.0, stage="unknown", client_id="system"):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    last = e
                    if attempt == max_attempts:
                        break
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    time.sleep(min(delay, 30))
            # exhausted -> dead letter
            try:
                import db
                db.dead_letter(client_id, "n/a", stage, f"{fn.__name__}: {last}\n{traceback.format_exc()[:300]}")
            except Exception:
                pass
            return None
        return wrapper
    return decorator
