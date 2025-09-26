import boto3
from datetime import datetime, timedelta
import re

# Configuration
S3_BUCKET_NAME = "weathertop2"
FILE_PATTERN = r"java-(\d{4}-\d{2}-\d{2})T\d{2}-\d{2}\.json"

def main():
    s3 = boto3.client("s3")
    response = s3.list_objects_v2(Bucket=S3_BUCKET_NAME)

    if "Contents" not in response:
        print("No files found in the bucket.")
        return

    today = datetime.utcnow()
    cutoff_date = today - timedelta(days=30)

    for obj in response["Contents"]:
        key = obj["Key"]
        match = re.match(FILE_PATTERN, key)
        if match:
            file_date_str = match.group(1)  # e.g., '2025-09-21'
            file_date = datetime.strptime(file_date_str, "%Y-%m-%d")
            if file_date < cutoff_date:
                # Delete file
                print(f"Deleting old file: {key}")
                s3.delete_object(Bucket=S3_BUCKET_NAME, Key=key)
            else:
                print(f"Keeping file: {key} (recent)")
        else:
            print(f"Skipping file (name doesn't match pattern): {key}")

if __name__ == "__main__":
    main()
