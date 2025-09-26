import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")

def is_bucket_empty(bucket_name):
    """Check if the bucket has no objects (including versioned ones)."""
    try:
        # Check regular objects
        resp = s3.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
        if "Contents" in resp:
            return False

        # Check versioned objects
        try:
            resp = s3.list_object_versions(Bucket=bucket_name, MaxKeys=1)
            if "Versions" in resp or "DeleteMarkers" in resp:
                return False
        except ClientError as e:
            if e.response["Error"]["Code"] not in ("NoSuchBucket", "InvalidBucketState"):
                raise

        return True
    except ClientError as e:
        print(f"❌ Could not check bucket {bucket_name}: {e}")
        return False

def delete_empty_buckets():
    """Delete all empty S3 buckets in the account."""
    resp = s3.list_buckets()
    for bucket in resp["Buckets"]:
        bucket_name = bucket["Name"]
        print(f"🔍 Checking bucket: {bucket_name}")
        if is_bucket_empty(bucket_name):
            try:
                s3.delete_bucket(Bucket=bucket_name)
                print(f"✅ Deleted empty bucket: {bucket_name}")
            except ClientError as e:
                print(f"❌ Could not delete bucket {bucket_name}: {e}")
        else:
            print(f"⏭️ Bucket not empty, skipped: {bucket_name}")

if __name__ == "__main__":
    delete_empty_buckets()
