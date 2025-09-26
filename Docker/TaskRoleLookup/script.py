import boto3
import json

# === CONFIG ===
TASK_ROLE_NAME = "ecsTaskRole"  # Replace with your ECS Task Role name

def check_iam_permissions(policy_doc):
    statements = policy_doc.get("Statement", [])
    if not isinstance(statements, list):
        statements = [statements]
    for stmt in statements:
        actions = stmt.get("Action", [])
        if not isinstance(actions, list):
            actions = [actions]
        for action in actions:
            if action.lower().startswith("iam:") or action == "*":
                effect = stmt.get("Effect", "Allow")
                if effect.lower() == "allow":
                    return True
    return False

def main():
    # Create IAM client
    iam = boto3.client("iam")

    # 1️⃣ List attached managed policies
    attached_policies = iam.list_attached_role_policies(RoleName=TASK_ROLE_NAME)
    print(f"=== Managed Policies attached to {TASK_ROLE_NAME} ===")
    for p in attached_policies.get("AttachedPolicies", []):
        print(f"- {p['PolicyName']} ({p['PolicyArn']})")

    # 2️⃣ List inline policies
    inline_policies = iam.list_role_policies(RoleName=TASK_ROLE_NAME)
    print(f"\n=== Inline Policies attached to {TASK_ROLE_NAME} ===")
    for p_name in inline_policies.get("PolicyNames", []):
        policy = iam.get_role_policy(RoleName=TASK_ROLE_NAME, PolicyName=p_name)
        print(f"- {p_name}:")
        print(json.dumps(policy['PolicyDocument'], indent=2))

    # 3️⃣ Check if any policy allows IAM actions
    print("\n=== IAM Permissions in Managed Policies ===")
    for p in attached_policies.get("AttachedPolicies", []):
        policy_arn = p['PolicyArn']
        policy_version = iam.get_policy(PolicyArn=policy_arn)['Policy']['DefaultVersionId']
        policy_doc = iam.get_policy_version(PolicyArn=policy_arn, VersionId=policy_version)['PolicyVersion']['Document']
        if check_iam_permissions(policy_doc):
            print(f"✅ {p['PolicyName']} grants IAM permissions")
        else:
            print(f"❌ {p['PolicyName']} does NOT grant IAM permissions")

    print("\n=== IAM Permissions in Inline Policies ===")
    for p_name in inline_policies.get("PolicyNames", []):
        policy_doc = iam.get_role_policy(RoleName=TASK_ROLE_NAME, PolicyName=p_name)['PolicyDocument']
        if check_iam_permissions(policy_doc):
            print(f"✅ {p_name} grants IAM permissions")
        else:
            print(f"❌ {p_name} does NOT grant IAM permissions")

if __name__ == "__main__":
    main()

