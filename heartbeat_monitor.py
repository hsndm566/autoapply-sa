#!/usr/bin/env python3
import os
import time
import subprocess
import re

LOG_FILE = "/home/ubuntu/autoapply-autonomous/autonomous_loop_output.txt"
LOOP_SCRIPT = "autonomous_loop.py"
CHECK_INTERVAL = 10 # seconds

def get_loop_pid():
    try:
        output = subprocess.check_output(["pgrep", "-f", LOOP_SCRIPT]).decode().strip()
        return output.split('\n')[0] if output else None
    except:
        return None

def monitor():
    print(f"Starting Heartbeat Monitor for {LOOP_SCRIPT}...")
    last_size = 0
    stuck_count = 0
    
    while True:
        pid = get_loop_pid()
        
        if not pid:
            print("WARNING: Loop process not found. Restarting...")
            subprocess.Popen(f"cd /home/ubuntu/autoapply-autonomous && python3 -u {LOOP_SCRIPT} >> {LOG_FILE} 2>&1", shell=True)
            stuck_count = 0
        else:
            # Check if log is growing
            if os.path.exists(LOG_FILE):
                current_size = os.path.getsize(LOG_FILE)
                if current_size == last_size:
                    stuck_count += 1
                else:
                    stuck_count = 0
                    last_size = current_size
                
                # If stuck for more than 2 minutes (12 * 10s)
                if stuck_count > 12:
                    print(f"WARNING: Loop seems stuck (PID {pid}). Killing and restarting...")
                    subprocess.run(["kill", "-9", pid])
                    stuck_count = 0
        
        # Check for common errors in last 5 lines
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, 'r') as f:
                    lines = f.readlines()[-5:]
                    log_text = "".join(lines)
                    if "Protocol error" in log_text or "Timeout" in log_text:
                        print("Detected error in log. Monitoring for recovery...")
            except:
                pass

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    monitor()
