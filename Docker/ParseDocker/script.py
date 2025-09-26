import subprocess
import sys
import json

# ================= CONFIG =================
AWS_ACCOUNT_ID = "814548047983"
AWS_REGION = "us-east-1"
ECR_REPO_NAME = "weathertop-rust-ecr-repo"
SCRIPT_PATH_IN_CONTAINER = "/app/run_tests.py"


# ================= HELPER FUNCTIONS =================
def run_cmd(cmd, capture_output=True):
    """Run shell command with UTF-8 decoding."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=True,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        return result.stdout.strip() if capture_output else None
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Command failed: {e}\nOutput: {e.stdout}\nError: {e.stderr}")
        return None


# ================= ECR FUNCTIONS =================
def list_all_image_digests():
    """Return a list of all image digests in the ECR repo."""
    cmd = f"aws ecr describe-images --repository-name {ECR_REPO_NAME} --region {AWS_REGION}"
    output = run_cmd(cmd)
    if not output:
        print("[ERROR] Failed to list images in ECR.")
        sys.exit(1)

    data = json.loads(output)
    digests = [img["imageDigest"] for img in data.get("imageDetails", [])]
    print(f"[ECR] Found {len(digests)} images in repository.")
    return digests


def get_image_uri(digest):
    """Construct full image URI using digest."""
    return f"{AWS_ACCOUNT_ID}.dkr.ecr.{AWS_REGION}.amazonaws.com/{ECR_REPO_NAME}@{digest}"


# ================= DOCKER FUNCTIONS =================
def login_to_ecr():
    """Login to AWS ECR using Docker."""
    print("[ECR] Logging in...")
    pw_cmd = f"aws ecr get-login-password --region {AWS_REGION}"
    password = run_cmd(pw_cmd)
    login_cmd = f"docker login --username AWS --password-stdin {AWS_ACCOUNT_ID}.dkr.ecr.{AWS_REGION}.amazonaws.com"
    proc = subprocess.Popen(
        login_cmd,
        shell=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    out, err = proc.communicate(input=password)
    if proc.returncode != 0:
        print(f"[ERROR] Docker login failed:\n{err}")
        sys.exit(1)
    print("[ECR] Login successful.")


def pull_image(image_uri):
    """Pull a Docker image by digest."""
    print(f"[Docker] Pulling image {image_uri}...")
    run_cmd(f"docker pull {image_uri}")
    print("[Docker] Image pulled successfully.")


def read_script_from_container(image_uri, script_path):
    """Run container to read a script and print it."""
    print(f"[Docker] Reading {script_path} from container {image_uri}...")
    cmd = f"docker run --rm {image_uri} cat {script_path}"
    output = run_cmd(cmd)
    if output:
        print(f"\n=== Contents of {script_path} in {image_uri} ===\n")
        print(output)
        print(f"\n=== End of {script_path} ===\n")
    else:
        print(f"[WARN] Script not found in container {image_uri}")


# ================= MAIN =================
def main():
    print("=== Pulling all Rust images from ECR ===")

    login_to_ecr()
    digests = list_all_image_digests()

    for digest in digests:
        image_uri = get_image_uri(digest)
        print(f"\n[INFO] Processing image: {image_uri}")
        pull_image(image_uri)
        read_script_from_container(image_uri, SCRIPT_PATH_IN_CONTAINER)


if __name__ == "__main__":
    main()




