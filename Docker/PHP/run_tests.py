import os
import subprocess
import json
import time
import shutil
import re
from datetime import datetime, timezone
import boto3

# === CONFIG ===
REPO_URL = "https://github.com/awsdocs/aws-doc-sdk-examples.git"
CLONE_DIR = "/app/aws-doc-sdk-examples"
PHP_ROOT = "php/example_code"
S3_BUCKET_NAME = "weathertop2"

# === UTILS ===
def run_command(command, cwd=None):
    env = os.environ.copy()
    in_fargate = "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI" in env or "AWS_CONTAINER_CREDENTIALS_FULL_URI" in env
    if in_fargate:
        for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"]:
            env.pop(key, None)
        env["AWS_REGION"] = env.get("AWS_REGION", "us-east-1")
        print("✅ ECS/Fargate detected. Using task role credentials.")
    else:
        print("ℹ️ Using existing environment credentials if available.")
    env["HOME"] = env.get("HOME", "/root")
    try:
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, cwd=cwd, env=env, check=True, text=True, capture_output=True)
        return result.returncode, result.stdout
    except subprocess.CalledProcessError as e:
        return e.returncode, (e.stdout or "") + "\n" + (e.stderr or "")

def parse_phpunit_output(output):
    passed = failed = skipped = 0
    match_ok = re.search(r"OK\s*\((\d+)\s+tests?", output)
    if match_ok:
        passed = int(match_ok.group(1))
        return passed, 0, 0
    match_summary = re.search(
        r"Tests:\s*(\d+),.*Failures:\s*(\d+),.*Skipped:\s*(\d+)", output, re.DOTALL
    )
    if match_summary:
        total = int(match_summary.group(1))
        failed = int(match_summary.group(2))
        skipped = int(match_summary.group(3))
        passed = total - failed - skipped
        return passed, failed, skipped
    if "FAILURES!" in output:
        failed_count = len(re.findall(r"\d+\) ", output))
        return 0, failed_count, 0
    return 0, 0, 0

def upload_to_s3(local_file, bucket_name, s3_key):
    s3 = boto3.client("s3")
    try:
        s3.upload_file(local_file, bucket_name, s3_key)
        print(f"✅ Uploaded {local_file} to S3 bucket: {bucket_name}/{s3_key}")
    except Exception as e:
        print(f"❌ Failed to upload to S3: {e}")

# === MAIN ===
def main():
    # Remove existing clone
    if os.path.exists(CLONE_DIR):
        print(f"🧹 Removing existing repo directory: {CLONE_DIR}")
        shutil.rmtree(CLONE_DIR)

    # Clone repo
    print(f"📥 Cloning repo: {REPO_URL}")
    returncode, output = run_command(["git", "clone", REPO_URL, CLONE_DIR])
    if returncode != 0:
        print("❌ Failed to clone repo.")
        print(output)
        return

    total_passed = total_failed = total_skipped = 0
    tests_array = []
    service_details = []
    no_tests_list = []

    php_example_root = os.path.join(CLONE_DIR, PHP_ROOT)
    if not os.path.exists(php_example_root):
        print(f"❌ PHP root directory not found: {php_example_root}")
        return

    services = sorted([d for d in os.listdir(php_example_root) if os.path.isdir(os.path.join(php_example_root, d))])

    for idx, service_name in enumerate(services, 1):
        service_root = os.path.join(php_example_root, service_name)
        test_folder = os.path.join(service_root, "tests")
        has_tests = os.path.isdir(test_folder) and any(f.endswith(".php") for f in os.listdir(test_folder))
        tests_run = passed = failed = 0

        if not has_tests:
            print(f"⚠️ No tests found for service: {service_name}")
            no_tests_list.append(service_name)
            service_details.append({
                "service_name": service_name,
                "order_tested": idx,
                "tests_run": 0,
                "passed": 0,
                "failed": 0,
                "has_tests": False
            })
            continue

        # Install dependencies if composer.json exists
        composer_json_path = os.path.join(service_root, "composer.json")
        if os.path.exists(composer_json_path):
            print(f"📦 Installing PHP dependencies in {service_root}...")
            returncode, output = run_command(
                ["composer", "install", "--no-interaction", "--prefer-dist", "--no-progress"],
                cwd=service_root
            )
            if returncode != 0:
                print(f"❌ Composer install failed for {service_name}, skipping tests")
                continue

        # Determine PHPUnit binary
        phpunit_bin_vendor = os.path.join(service_root, "vendor/bin/phpunit")
        phpunit_bin_global = "/usr/local/bin/phpunit"
        phpunit_bin = phpunit_bin_vendor if os.path.isfile(phpunit_bin_vendor) else phpunit_bin_global
        if not os.path.isfile(phpunit_bin):
            print(f"❌ PHPUnit not found for service: {service_name}, skipping")
            continue

        # Generate bootstrap_runtime.php
        bootstrap_file = os.path.join(test_folder, "bootstrap_runtime.php")
        with open(bootstrap_file, "w", encoding="utf-8") as f:
            f.write(f"""<?php
require_once __DIR__ . '/../vendor/autoload.php';
spl_autoload_register(function ($class) {{
    $prefix = '{service_name}\\\\';
    $base_dir = __DIR__ . '/../';
    $len = strlen($prefix);
    if (strncmp($prefix, $class, $len) !== 0) return;
    $relative_class = substr($class, $len);
    $file = $base_dir . str_replace('\\\\', '/', $relative_class) . '.php';
    if (file_exists($file)) require $file;
}});
""")

        # Collect all test files
        test_files = [os.path.join("tests", f) for f in os.listdir(test_folder) if f.endswith(".php") and f != "bootstrap_runtime.php"]

        phpunit_command = [phpunit_bin, "--colors=never", "--bootstrap", bootstrap_file] + test_files
        returncode, output = run_command(phpunit_command, cwd=service_root)
        print(f"PHPUnit output for {service_name}:\n{output}")

        passed, failed, skipped = parse_phpunit_output(output)
        tests_run = passed + failed + skipped

        total_passed += passed
        total_failed += failed
        total_skipped += skipped

        # Track service details
        service_details.append({
            "service_name": service_name,
            "order_tested": idx,
            "tests_run": tests_run,
            "passed": passed,
            "failed": failed,
            "has_tests": True
        })

        # Track individual failed tests
        if failed > 0:
            fail_matches = re.findall(r"\d+\) (.+?)\n(.+?)(?:\n\s*\n|$)", output, re.DOTALL)
            if fail_matches:
                for test_name, log_text in fail_matches:
                    tests_array.append({
                        "service": service_name,
                        "test_name": test_name.strip(),
                        "status": "failed",
                        "message": log_text.strip(),
                        "order_tested": idx
                    })
            else:
                tests_array.append({
                    "service": service_name,
                    "test_name": "FAIL",
                    "status": "failed",
                    "message": output.strip(),
                    "order_tested": idx
                })

    total_tests = total_passed + total_failed + total_skipped
    pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0

    schema = {
        "schema-version": "0.0.1",
        "results": {
            "tool": "phpunit",
            "summary": {
                "services": len(services),
                "tests": total_tests,
                "passed": total_passed,
                "failed": total_failed,
                "skipped": total_skipped,
                "pass_rate": round(pass_rate, 2),
                "start_time": int(time.time() * 1000),
                "stop_time": int(time.time() * 1000)
            },
            "service_details": service_details,
            "tests": tests_array,
            "no_tests": no_tests_list
        }
    }

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M")
    filename = f"php-{now}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
    print(f"📁 Wrote schema to local file: {filename}")

    # Upload to S3
    upload_to_s3(filename, S3_BUCKET_NAME, filename)

    # --- Display JSON in console ---
    print("\n=== FINAL JSON ===")
    print(json.dumps(schema, indent=2))

if __name__ == "__main__":
    main()
