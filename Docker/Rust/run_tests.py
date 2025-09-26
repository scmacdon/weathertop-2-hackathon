import os
import subprocess
import json
import time
import shutil
import re
import boto3
from datetime import datetime

# ================= CONFIG =================
REPO_URL = "https://github.com/awsdocs/aws-doc-sdk-examples.git"
CLONE_DIR = "/app/aws-doc-sdk-examples"
ROOT_TEST_DIR = "rustv1/examples"   # root folder containing service crates
S3_BUCKET = "weathertop2"           # adjust if needed
# ==========================================

def run_cmd(cmd, cwd=None):
    """Run shell command and return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def clone_repo():
    if os.path.exists(CLONE_DIR):
        print(f"🗑️ Removing old repo at {CLONE_DIR}")
        shutil.rmtree(CLONE_DIR)

    print(f"📥 Cloning repo {REPO_URL}...")
    code, out, err = run_cmd(["git", "clone", "--depth", "1", REPO_URL, CLONE_DIR])
    if code != 0:
        raise RuntimeError(f"Git clone failed: {err}")

    root_cargo = os.path.join(CLONE_DIR, ROOT_TEST_DIR, "Cargo.toml")
    if os.path.exists(root_cargo):
        print(f"🗑️ Removing root Cargo.toml at {root_cargo}")
        os.remove(root_cargo)

def discover_services():
    services = []
    for entry in os.scandir(os.path.join(CLONE_DIR, ROOT_TEST_DIR)):
        if entry.is_dir():
            cargo_file = os.path.join(entry.path, "Cargo.toml")
            if os.path.exists(cargo_file):
                services.append(entry.name)
    return sorted(services)

def stage1_build(service):
    service_dir = os.path.join(CLONE_DIR, ROOT_TEST_DIR, service)
    print(f"🔨 Building {service}...")
    return run_cmd(["cargo", "build"], cwd=service_dir)

def stage2_test(service):
    service_dir = os.path.join(CLONE_DIR, ROOT_TEST_DIR, service)
    print(f"🧪 Testing {service}...")
    return run_cmd(["cargo", "test", "--quiet"], cwd=service_dir)

def parse_test_output(output: str):
    """
    Parse cargo test output for counts.
    Example line:
    test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
    """
    summary = {"tests": 0, "passed": 0, "failed": 0, "ignored": 0}
    match = re.search(r"test result: .*? (\d+) passed; (\d+) failed; (\d+) ignored;", output)
    if match:
        passed, failed, ignored = map(int, match.groups())
        summary["tests"] = passed + failed + ignored
        summary["passed"] = passed
        summary["failed"] = failed
        summary["ignored"] = ignored
    return summary

def upload_to_s3(filename, bucket):
    s3 = boto3.client("s3")
    key = f"{os.path.basename(filename)}"
    s3.upload_file(filename, bucket, key)
    print(f"✅ Uploaded {filename} to S3 bucket: {bucket}/{key}")

def main():
    start_time = int(time.time() * 1000)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M")
    results_file = f"rustv1-{timestamp}.json"

    clone_repo()
    services = discover_services()

    summary = {
        "services": 0,
        "tests": 0,
        "passed": 0,
        "failed": 0,
        "ignored": 0,
        "start_time": start_time,
        "stop_time": None
    }

    tests_array = []

    for service in services:
        service_result = {"build": None, "tests": None, "parsed": None}

        # Stage 1: build
        build_code, build_out, build_err = stage1_build(service)
        service_result["build"] = {
            "exit_code": build_code,
            "stdout": build_out,
            "stderr": build_err,
        }

        if build_code != 0:
            print(f"❌ Build failed for {service}")
            summary["failed"] += 1
            summary["services"] += 1
            tests_array.append({
                "service": service,
                "test_name": "build",
                "status": "failed",
                "message": build_err.strip()
            })
            continue

        # Stage 2: test
        test_code, test_out, test_err = stage2_test(service)
        combined_out = test_out + "\n" + test_err
        parsed = parse_test_output(combined_out)

        service_result["tests"] = {
            "exit_code": test_code,
            "stdout": test_out,
            "stderr": test_err,
        }
        service_result["parsed"] = parsed

        summary["services"] += 1
        summary["tests"] += parsed["tests"]
        summary["passed"] += parsed["passed"]
        summary["failed"] += parsed["failed"]
        summary["ignored"] += parsed["ignored"]

        if parsed["tests"] == 0:
            print(f"⚠️  No tests for {service}")
        if parsed["failed"] > 0:
            tests_array.append({
                "service": service,
                "test_name": "result:",
                "status": "failed",
                "message": combined_out.strip()
            })

    summary["stop_time"] = int(time.time() * 1000)

    final_results = {
        "schema-version": "0.0.1",
        "results": {
            "tool": "rust",
            "summary": summary,
            "tests": tests_array
        }
    }

    # Write JSON results
    with open(results_file, "w") as f:
        json.dump(final_results, f, indent=2)

    print(f"\n📊 Final Results written to {results_file}:")
    print(json.dumps(final_results, indent=2))

    # Upload to S3
    upload_to_s3(results_file, S3_BUCKET)

if __name__ == "__main__":
    main()





