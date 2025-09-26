import os
import subprocess
import json
import time
import uuid
import boto3
import shutil
from datetime import datetime
import re

REPO_URL = "https://github.com/awsdocs/aws-doc-sdk-examples.git"
CLONE_DIR = "/app/aws-doc-sdk-examples"
ROOT_TEST_DIR = "dotnetv4"
S3_BUCKET_NAME = "weathertop2"

def run_command(command, cwd=None):
    try:
        result = subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)
        return result.returncode, result.stdout
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout + "\n" + e.stderr

def parse_dotnet_test_results(output):
    passed = failed = skipped = 0
    summary_pattern = re.compile(r"Failed:\s*(\d+),\s*Passed:\s*(\d+),\s*Skipped:\s*(\d+)")
    for line in output.splitlines():
        match = summary_pattern.search(line)
        if match:
            failed = int(match.group(1))
            passed = int(match.group(2))
            skipped = int(match.group(3))
            break
    return passed, failed, skipped

def extract_failures(output, service_name, order_tested):
    failures = []
    lines = output.splitlines()
    failure_start_pattern = re.compile(r"^\s*Failed\s+([\w\.]+)\s+\[.*\]")
    test_result_pattern = re.compile(r"^\s*(Passed|Failed|Skipped)\s+([\w\.]+)\s+\[.*\]")

    in_failure = False
    current_failure_lines = []
    current_test_name = None

    for line in lines:
        match = failure_start_pattern.match(line)
        if match:
            if in_failure and current_failure_lines:
                failures.append({
                    "service": service_name.lower(),
                    "test_name": current_test_name or "unknown",
                    "status": "failed",
                    "message": "\n".join(current_failure_lines).strip(),
                    "order_tested": order_tested
                })
                current_failure_lines = []
            in_failure = True
            current_test_name = match.group(1)

        if in_failure:
            current_failure_lines.append(line)
            if test_result_pattern.match(line) and not failure_start_pattern.match(line):
                in_failure = False

    if current_failure_lines:
        failures.append({
            "service": service_name.lower(),
            "test_name": current_test_name or "unknown",
            "status": "failed",
            "message": "\n".join(current_failure_lines).strip(),
            "order_tested": order_tested
        })

    return failures

def has_trait_annotation(service_path):
    for root, _, files in os.walk(service_path):
        for file in files:
            if file.endswith(".cs"):
                with open(os.path.join(root, file), encoding="utf-8") as f:
                    content = f.read()
                    if '[Trait("Category", "Integration")]' in content:
                        return True
    return False

def run_dotnet_tests(service_path, service_name, order_tested, failed_tests):
    has_trait = has_trait_annotation(service_path)
    test_project = None

    for root, _, files in os.walk(service_path):
        for file in files:
            if file.endswith(".csproj") and "Test" in root:
                test_project = os.path.join(root, file)
                break
        if test_project:
            break

    if not has_trait or not test_project:
        print(f"⚠️ Skipping {service_name}: No matching integration tests found.")
        return 0, 0, 0, False

    print(f"🔧 Testing: {service_name}")
    returncode, output = run_command(["dotnet", "test", test_project, "--filter", "Category=Integration"], cwd=service_path)
    print(output)

    passed, failed, skipped = parse_dotnet_test_results(output)
    print(f"📊 Result: {'✅ Passed' if failed == 0 else '❌ Failed'} — Passed: {passed}, Failed: {failed}, Skipped: {skipped}")

    if failed > 0:
        extracted = extract_failures(output, service_name, order_tested)
        failed_tests.extend(extracted)

    return passed, failed, skipped, True

def upload_to_s3(local_file, bucket_name, s3_key):
    s3 = boto3.client("s3")
    try:
        s3.upload_file(local_file, bucket_name, s3_key)
        print(f"✅ Uploaded {local_file} to S3 bucket: {bucket_name}/{s3_key}")
    except Exception as e:
        print(f"❌ Failed to upload to S3: {e}")

def main():
    if os.path.exists(CLONE_DIR):
        print(f"🧹 Removing existing repo directory: {CLONE_DIR}")
        shutil.rmtree(CLONE_DIR)

    print(f"📥 Cloning repo: {REPO_URL}")
    returncode, output = run_command(["git", "clone", REPO_URL, CLONE_DIR])
    if returncode != 0:
        print("❌ Failed to clone repo.")
        return

    root_test_path = os.path.join(CLONE_DIR, ROOT_TEST_DIR)
    service_dirs = sorted([
        d for d in os.listdir(root_test_path)
        if os.path.isdir(os.path.join(root_test_path, d))
    ])

    total_passed = total_failed = total_skipped = 0
    failed_tests = []
    service_details = []
    no_tests = []
    start_time = int(time.time() * 1000)

    for idx, service_name in enumerate(service_dirs, start=1):
        service_path = os.path.join(root_test_path, service_name)
        passed, failed, skipped, has_tests = run_dotnet_tests(service_path, service_name, idx, failed_tests)

        service_details.append({
            "service_name": service_name.lower(),
            "order_tested": idx,
            "tests_run": passed + failed + skipped,
            "passed": passed,
            "failed": failed,
            "has_tests": has_tests
        })

        if not has_tests:
            no_tests.append(service_name.lower())

        total_passed += passed
        total_failed += failed
        total_skipped += skipped

    stop_time = int(time.time() * 1000)
    total_tests = total_passed + total_failed + total_skipped

    print("\n===== ✅ Final Test Summary =====")
    print(f"Services Checked: {len(service_dirs)}")
    print(f"Total Tests Passed: {total_passed}")
    print(f"Total Tests Failed: {total_failed}")
    print(f"Total Tests Skipped: {total_skipped}")
    print(f"Total Time: {(stop_time - start_time) // 1000} sec")

    schema = {
        "schema-version": "0.0.1",
        "results": {
            "tool": "dotnet",
            "summary": {
                "services": len(service_dirs),
                "tests": total_tests,
                "passed": total_passed,
                "failed": total_failed,
                "start_time": start_time,
                "stop_time": stop_time
            },
            "service_details": service_details,
            "tests": failed_tests,
            "no_tests": no_tests
        }
    }

    now = datetime.utcnow().strftime("%Y-%m-%dT%H-%M")
    filename = f"dotnetv4-{now}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
    print(f"📁 Wrote schema to local file: {filename}")

    upload_to_s3(filename, S3_BUCKET_NAME, filename)

     # Print JSON to stdout
    print("\n===== 📊 Final JSON Schema =====")
    print(json.dumps(schema, indent=2))

if __name__ == "__main__":
    main()
