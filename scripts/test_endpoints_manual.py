#!/usr/bin/env python3
"""
Manual test script for new API endpoints.
Run this against a live scheduler instance to verify all endpoints work.

Usage:
    python test_endpoints_manual.py [API_BASE_URL] [API_TOKEN]
    
Example:
    python test_endpoints_manual.py http://localhost:8000 your-token-here
"""

import sys
import json
import requests
from typing import Dict, Any


def test_endpoints(base_url: str, token: str):
    """Test all new endpoints."""
    headers = {"x-api-key": token, "Content-Type": "application/json"}
    
    print(f"Testing API at {base_url}")
    print("=" * 60)
    
    # Test 1: Create a test job
    print("\n1. Creating test job...")
    job_payload = {
        "name": "test-endpoint-job",
        "user": "test-user",
        "affinity": {"os": ["linux"], "tags": [], "allowed_users": []},
        "executor": {
            "type": "shell",
            "script": "echo 'test job'",
            "shell": "bash"
        },
        "schedule": {
            "mode": "interval",
            "interval_seconds": 3600,
            "enabled": True
        },
        "retries": 0,
        "timeout": 60,
        "priority": 5
    }
    
    resp = requests.post(f"{base_url}/jobs/", json=job_payload, headers=headers)
    if resp.status_code == 200:
        job = resp.json()
        job_id = job["_id"]
        print(f"✓ Created job: {job_id}")
    else:
        print(f"✗ Failed to create job: {resp.status_code} - {resp.text}")
        return
    
    # Test 2: Get stats overview
    print("\n2. Getting stats overview...")
    resp = requests.get(f"{base_url}/stats/overview", headers=headers)
    if resp.status_code == 200:
        stats = resp.json()
        print(f"✓ Stats: {stats['total_jobs']} jobs, {stats['total_workers']} workers")
    else:
        print(f"✗ Failed to get stats: {resp.status_code}")
    
    # Test 3: Pause job
    print("\n3. Pausing job...")
    resp = requests.post(f"{base_url}/jobs/{job_id}/pause", headers=headers)
    if resp.status_code == 200:
        result = resp.json()
        print(f"✓ Job paused: {result['status']}")
    else:
        print(f"✗ Failed to pause: {resp.status_code} - {resp.text}")
    
    # Test 4: Resume job
    print("\n4. Resuming job...")
    resp = requests.post(f"{base_url}/jobs/{job_id}/resume", headers=headers)
    if resp.status_code == 200:
        result = resp.json()
        print(f"✓ Job resumed: {result['status']}")
    else:
        print(f"✗ Failed to resume: {resp.status_code} - {resp.text}")
    
    # Test 5: Patch job (partial update)
    print("\n5. Patching job...")
    patch_payload = {"priority": 8, "timeout": 120}
    resp = requests.patch(f"{base_url}/jobs/{job_id}", json=patch_payload, headers=headers)
    if resp.status_code == 200:
        updated = resp.json()
        print(f"✓ Job patched: priority={updated['priority']}, timeout={updated['timeout']}")
    else:
        print(f"✗ Failed to patch: {resp.status_code} - {resp.text}")
    
    # Test 6: List workers (check if specific worker endpoint exists)
    print("\n6. Listing workers...")
    resp = requests.get(f"{base_url}/workers/", headers=headers)
    if resp.status_code == 200:
        workers = resp.json()
        print(f"✓ Found {len(workers)} workers")
        if workers:
            worker_id = workers[0]["worker_id"]
            # Test getting specific worker
            resp = requests.get(f"{base_url}/workers/{worker_id}", headers=headers)
            if resp.status_code == 200:
                print(f"✓ Got specific worker: {worker_id}")
            else:
                print(f"✗ Failed to get specific worker: {resp.status_code}")
    else:
        print(f"✗ Failed to list workers: {resp.status_code}")
    
    # Test 7: List runs with filters
    print("\n7. Listing runs...")
    resp = requests.get(f"{base_url}/runs/?limit=10", headers=headers)
    if resp.status_code == 200:
        result = resp.json()
        print(f"✓ Listed runs: {len(result['runs'])} of {result['total']} total")
    else:
        print(f"✗ Failed to list runs: {resp.status_code}")
    
    # Test 8: Bulk job creation
    print("\n8. Creating jobs in bulk...")
    bulk_payload = [
        {
            "name": f"bulk-test-{i}",
            "user": "bulk-user",
            "affinity": {"os": ["linux"], "tags": [], "allowed_users": []},
            "executor": {
                "type": "shell",
                "script": f"echo 'bulk job {i}'",
                "shell": "bash"
            },
            "schedule": {"mode": "immediate", "enabled": False},
            "retries": 0,
            "timeout": 30,
            "priority": 5
        }
        for i in range(3)
    ]
    
    resp = requests.post(f"{base_url}/jobs/bulk", json=bulk_payload, headers=headers)
    if resp.status_code == 200:
        created = resp.json()
        bulk_ids = [j["_id"] for j in created]
        print(f"✓ Created {len(created)} jobs in bulk")
    else:
        print(f"✗ Failed to create bulk: {resp.status_code} - {resp.text}")
        bulk_ids = []
    
    # Test 9: Delete bulk jobs
    print("\n9. Cleaning up bulk jobs...")
    for jid in bulk_ids:
        resp = requests.delete(f"{base_url}/jobs/{jid}", headers=headers)
        if resp.status_code == 200:
            print(f"✓ Deleted job: {jid}")
        else:
            print(f"✗ Failed to delete {jid}: {resp.status_code}")
    
    # Test 10: Delete test job
    print("\n10. Cleaning up test job...")
    resp = requests.delete(f"{base_url}/jobs/{job_id}", headers=headers)
    if resp.status_code == 200:
        print(f"✓ Deleted test job: {job_id}")
    else:
        print(f"✗ Failed to delete: {resp.status_code} - {resp.text}")
    
    print("\n" + "=" * 60)
    print("Testing complete!")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    
    base_url = sys.argv[1].rstrip("/")
    token = sys.argv[2]
    
    try:
        test_endpoints(base_url, token)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
