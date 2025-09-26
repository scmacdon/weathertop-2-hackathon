import subprocess
import os
import sys
import re
import time
import uuid
import json
import boto3
from datetime import datetime

# Configuration
GIT_REPO = "https://github.com/awsdocs/aws-doc-sdk-examples.git"
CLONE_DIR = "/app/aws-doc-sdk-examples"
ROOT_TEST_DIR = "javav2/example_code"
S3_BUCKET_NAME = "weathertop2"

def run_command(cmd, cwd=None):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(result.stdout)
    return result.returncode, result.stdout

def clone_repo():
    if os.path.exists(CLONE_DIR):
        print("Repo already cloned.")
        return
    result = run_command(["git", "clone", GIT_REPO, CLONE_DIR])
    if result[0] != 0:
        sys.exit("❌ Failed to clone repo.")

def parse_test_results(output):
    passed = failed = skipped = 0
    match = re.search(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)", output)
    if match:
        tests_run = int(match.group(1))
        failures = int(match.group(2))
        errors = int(match.group(3))
        skipped = int(match.group(4))
        passed = tests_run - (failures + errors + skipped)
    return passed, failures + errors, skipped

def has_integration_tests(path):
    for root, _, files in os.walk(path):
        for file in files:
            if file.endswith(".java"):
                with open(os.path.join(root, file), encoding="utf-8") as f:
                    content = f.read()
                    if "@Test" in content and '@Tag("IntegrationTest")' in content:
                        return True
    return False

def extract_failures(output, service_name, test_index_start):
    failures = []
    test_index = test_index_start

    # Extract potential failure sections
    failure_blocks = re.findall(r"(Tests run:.*?)(?=^\[INFO\]|\Z)", output, re.DOTALL | re.MULTILINE)

    for block in failure_blocks:
        # Try to extract a line containing an exception or failure
        lines = block.splitlines()
        log_lines = [line for line in lines if "Exception" in line or "FAILURE" in line or "ERROR" in line]
        if not log_lines:
            continue
        error_log = log_lines[-1].strip()

        failures.append({
            "name": f"test {test_index}",
            "status": "failed",
            "duration": test_index,  # Simulate duration using index
            "message": service_name,
            "log": error_log
        })
        test_index += 1
    return failures, test_index

def run_maven_tests(service_path, service_name, failed_tests, test_index_start):
    print(f"\n🔧 Testing: {service_path}")
    returncode, output = run_command(["mvn", "clean", "test", "-Dgroups=IntegrationTest"], cwd=service_path)
    passed, failed, skipped = parse_test_results(output)

    status = "✅ Passed" if failed == 0 else "❌ Failed"
    print(f"📊 Result: {status} — Passed: {passed}, Failed: {failed}, Skipped: {skipped}")

    next_index = test_index_start
    if failed > 0:
        extracted, next_index = extract_failures(output, service_name, test_index_start)
        failed_tests.extend(extracted)

    return passed, failed, skipped, next_index

def upload_to_s3(local_file, bucket_name, s3_key):
    s3 = boto3.client("s3")
    try:
        s3.upload_file(local_file, bucket_name, s3_key)
        print(f"✅ Uploaded {local_file} to S3 bucket: {bucket_name}/{s3_key}")
    except Exception as e:
        print(f"❌ Failed to upload to S3: {e}")

def main():
    clone_repo()

    total_passed = total_failed = total_skipped = 0
    tested_services = 0
    failed_tests = []
    test_index = 1
    start_time = int(time.time() * 1000)
    run_id = str(uuid.uuid4())

    root_test_path = os.path.join(CLONE_DIR, ROOT_TEST_DIR)
    service_dirs = sorted([d for d in os.listdir(root_test_path) if os.path.isdir(os.path.join(root_test_path, d))])

    for service_name in service_dirs:
        service_path = os.path.join(root_test_path, service_name)
        if os.path.exists(os.path.join(service_path, "pom.xml")) and has_integration_tests(service_path):
            passed, failed, skipped, test_index = run_maven_tests(service_path, service_name, failed_tests, test_index)
            total_passed += passed
            total_failed += failed
            total_skipped += skipped
            tested_services += 1
        else:
            print(f"⚠️ Skipping {service_name}: No integration tests found or no pom.xml.")

    stop_time = int(time.time() * 1000)
    total_tests = total_passed + total_failed + total_skipped

    print("\n===== ✅ Final Test Summary =====")
    print(f"Services Tested: {tested_services}")
    print(f"Total Tests Passed: {total_passed}")
    print(f"Total Tests Failed: {total_failed}")
    print(f"Total Tests Skipped: {total_skipped}")
    print(f"Total Time: {(stop_time - start_time) // 1000} sec")

    # Build result schema
    schema = {
        "schema-version": "0.0.1",
        "results": {
            "tool": "JUnit",
            "summary": {
                "services": tested_services,
                "tests": total_tests,
                "passed": total_passed,
                "failed": total_failed,
                "start_time": start_time,
                "stop_time": stop_time
            },
            "tests": failed_tests
        }
    }

    # Format filename based on UTC timestamp
    now = datetime.utcnow().strftime("%Y-%m-%dT%H-%M")
    filename = f"java-{now}.json"

    # Write to local file
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
    print(f"📁 Wrote schema to local file: {filename}")

    # Upload to S3
    upload_to_s3(filename, S3_BUCKET_NAME, filename)

if __name__ == "__main__":
    main()
