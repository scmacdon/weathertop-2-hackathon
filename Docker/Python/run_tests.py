import subprocess
import os
import shutil
import sys
import re
import time
import json
import boto3
from datetime import datetime

# === CONFIG ===
CLONE_DIR = "/app/aws-doc-sdk-examples"
REPO_URL = "https://github.com/awsdocs/aws-doc-sdk-examples.git"
ROOT_TEST_DIR = "python/example_code"
S3_BUCKET_NAME = "weathertop2"

# === UTILS ===
def run_command(command, cwd=None, env=None):
    """Run a shell command and capture output."""
    try:
        result = subprocess.run(
            command, cwd=cwd, env=env,
            check=True, text=True, capture_output=True
        )
        return result.returncode, result.stdout
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout + "\n" + e.stderr

def upload_to_s3(local_file, bucket_name, s3_key):
    """Upload file to S3."""
    s3 = boto3.client("s3")
    try:
        s3.upload_file(local_file, bucket_name, s3_key)
        print(f"✅ Uploaded {local_file} to S3 bucket: {bucket_name}/{s3_key}")
    except Exception as e:
        print(f"❌ Failed to upload to S3: {e}")

def parse_pytest_results(output):
    """Parse pytest output summary."""
    passed = failed = skipped = 0
    matches = re.findall(r"(\d+)\s+(passed|failed|skipped)", output)
    for count, label in matches:
        if label == "passed":
            passed += int(count)
        elif label == "failed":
            failed += int(count)
        elif label == "skipped":
            skipped += int(count)
    return passed, failed, skipped

def extract_failures(output, service_name, test_index_start):
    """Extract individual failure blocks from pytest output."""
    failures = []
    blocks = re.split(r"={10,}", output)  # pytest separators
    test_index = test_index_start

    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue
        header_match = re.match(r"(FAILED|ERROR)\s+(\S+)", lines[0])
        if header_match:
            test_name = header_match.group(2)
            message = "\n".join(lines[1:]).strip() or "no failure message captured"
            failures.append({
                "service": service_name,
                "test_name": test_name,
                "status": "failed",
                "message": message
            })
            test_index += 1

    return failures, test_index

# === MAIN ===
def main():
    if os.path.exists(CLONE_DIR):
        print(f"🧹 Removing existing repo directory: {CLONE_DIR}")
        shutil.rmtree(CLONE_DIR)

    print(f"📥 Cloning repo: {REPO_URL}")
    rc, _ = run_command(["git", "clone", REPO_URL, CLONE_DIR])
    if rc != 0:
        print("❌ Failed to clone repo.")
        sys.exit(1)

    total_passed = total_failed = total_skipped = 0
    failed_tests = []
    service_details = []
    no_tests = []
    services_tested = 0
    test_index = 1
    start_time = int(time.time() * 1000)

    # Discover all services dynamically (alphabetical order)
    services = sorted(os.listdir(os.path.join(CLONE_DIR, ROOT_TEST_DIR)))
    for order, service in enumerate(services, start=1):
        service_path = os.path.join(CLONE_DIR, ROOT_TEST_DIR, service)
        if not os.path.isdir(service_path):
            continue

        # Recursively find "test" folders
        test_folders = []
        for root, dirs, _ in os.walk(service_path):
            for d in dirs:
                if d.lower() == "test":
                    test_folders.append(os.path.join(root, d))

        if not test_folders:
            print(f"⚠️ No tests found for: {service}")
            service_details.append({
                "service_name": service.lower(),
                "order_tested": order,
                "tests_run": 0,
                "passed": 0,
                "failed": 0,
                "has_tests": False
            })
            no_tests.append(service.lower())
            continue

        total_service_passed = total_service_failed = total_service_skipped = 0

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{service_path}:{os.path.join(CLONE_DIR, 'python', 'example_code')}:{os.path.join(CLONE_DIR, 'python')}"

        print(f"\n🧪 Running tests for: {service}")
        for test_folder in test_folders:
            rc, output = run_command(
                ["pytest", "-v", "--maxfail=50", "--disable-warnings", "--tb=long"],
                cwd=test_folder,
                env=env
            )
            print(output)

            passed, failed, skipped = parse_pytest_results(output)
            total_service_passed += passed
            total_service_failed += failed
            total_service_skipped += skipped

            if failed > 0:
                failures, test_index = extract_failures(output, service, test_index)
                failed_tests.extend(failures)

        total_passed += total_service_passed
        total_failed += total_service_failed
        total_skipped += total_service_skipped

        service_details.append({
            "service_name": service.lower(),
            "order_tested": order,
            "tests_run": total_service_passed + total_service_failed + total_service_skipped,
            "passed": total_service_passed,
            "failed": total_service_failed,
            "has_tests": True
        })
        services_tested += 1

    stop_time = int(time.time() * 1000)
    total_tests = total_passed + total_failed + total_skipped

    print("\n===== ✅ Final Test Summary =====")
    print(f"Services Scanned: {len(services)}")
    print(f"Services With Tests: {services_tested}")
    print(f"Total Tests: {total_tests} (Passed {total_passed}, Failed {total_failed}, Skipped {total_skipped})")

    schema = {
        "schema-version": "0.0.1",
        "results": {
            "tool": "pytest",
            "summary": {
                "services": len(services),
                "tests": total_tests,
                "passed": total_passed,
                "failed": total_failed,
                "skipped": total_skipped,
                "start_time": start_time,
                "stop_time": stop_time
            },
            "service_details": service_details,
            "tests": failed_tests,
            "no_tests": no_tests
        }
    }

    now = datetime.utcnow().strftime("%Y-%m-%dT%H-%M")
    filename = f"python-{now}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
    print(f"📁 Wrote schema to local file: {filename}")

    upload_to_s3(filename, S3_BUCKET_NAME, filename)

    # Print JSON to console for Docker logs
    print("\n===== 📊 Final JSON Schema =====")
    print(json.dumps(schema, indent=2))


if __name__ == "__main__":
    main()
