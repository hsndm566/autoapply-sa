#!/usr/bin/env python3
import json
import time
from greenhouse_submit import submit_greenhouse
from ashby_submit import submit_ashby
from lever_submit import submit_lever

# Candidate data
CANDIDATE = {
    "first_name": "Hassan",
    "last_name": "Adam",
    "email": "hasanadam506@gmail.com",
    "phone": "+966571448656",
    "cv_path": "/home/ubuntu/upload/HasanAdamcvindustrialengineering.pdf",
    "location": "Jeddah, Saudi Arabia",
    "gender": "Male",
    "nationality": "Saudi"
}

def run_loop():
    with open('/home/ubuntu/autoapply-autonomous/discovered_jobs_ksa_2026-08-14.json', 'r') as f:
        jobs = json.load(f)
    
    results = []
    count = 0
    for job in jobs:
        if count >= 10:
            break
            
        print(f"Processing {job['title']} at {job['company']} ({job['platform']})...")
        
        if job['platform'] == 'greenhouse':
            res = submit_greenhouse(job['url'], CANDIDATE)
        elif job['platform'] == 'ashby':
            res = submit_ashby(job['url'], CANDIDATE)
        elif job['platform'] == 'lever':
            res = submit_lever(job['url'], CANDIDATE)
        else:
            continue
            
        results.append(res)
        if res.get('submitted'):
            count += 1
            print(f"SUCCESS: Applied to {job['company']}")
        else:
            print(f"FAILED: {res.get('error', 'Unknown error')}")
        
        # Avoid rate limiting
        time.sleep(5)
    
    with open('/home/ubuntu/autoapply-autonomous/application_results_2026-08-14.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Finished. Total applications submitted: {count}")

if __name__ == "__main__":
    run_loop()
