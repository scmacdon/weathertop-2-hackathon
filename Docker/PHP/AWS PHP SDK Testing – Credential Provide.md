AWS PHP SDK Testing – Credential Provider Issue
Problem Overview

Some PHP service wrapper classes in this repository (for example, IAMService) define their service clients with explicit profile configuration in the constructor:

$this->iamClient = new IamClient([
    'region' => $region,
    'version' => $version,
    'profile' => $profile,
]);


At first glance this looks fine, but it prevents the AWS SDK for PHP from using the default credential provider chain.

The default chain is the mechanism that automatically sources credentials from:

Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, etc.)

AWS config/credentials files (~/.aws/credentials)

EC2/ECS instance metadata

IAM roles for service accounts (IRSA) on EKS

Other sources supported by the SDK

By hardcoding a profile, the tests now depend on the local environment having a [default] profile in ~/.aws/credentials.
In CI/CD or containerized environments (like GitHub Actions, CodeBuild, or ECS), this file doesn’t exist — so tests fail with authentication errors.

Why Tests Fail

Clients require a local profile that may not exist.

No fallback to metadata or environment-based credentials.

Automation breaks in CI pipelines, Docker containers, or ephemeral runners.

Correct Client Declaration

All service clients should be declared without hardcoding profiles or credentials.

❌ Bad pattern:

$this->iamClient = new IamClient([
    'region' => $region,
    'version' => $version,
    'profile' => $profile,
]);


✅ Good pattern (KMS style):

$this->kmsClient = new KmsClient([
    'region' => $region,
    'version' => $version,
]);


This way, the SDK uses the default credential provider chain and will:

Work locally with exported credentials or configured profiles

Work in CI/CD pipelines using AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY

Work on AWS services (ECS, EC2, Lambda, CodeBuild) using IAM roles

Recommendation for Testable Code

Never hardcode profiles or credentials in service constructors.

Always rely on the default provider chain.

Update all service wrappers (e.g., IAMService, GlueService, etc.) to match the KMS example.

This ensures the code:

Works consistently across developer machines, CI/CD pipelines, and containers

Matches AWS best practices

Makes tests portable and reliable

Example – Good Testable Service
use Aws\Kms\KmsClient;

class KMSService
{
    protected KmsClient $kmsClient;

    public function __construct($region = 'us-west-2', $version = 'latest')
    {
        $this->kmsClient = new KmsClient([
            'region' => $region,
            'version' => $version,
        ]);
    }

    public function createKey(string $description): array
    {
        return $this->kmsClient->createKey([
            'Description' => $description,
        ])['KeyMetadata'];
    }
}


This approach works everywhere credentials are supplied correctly because it always relies on the default credential provider chain.

⚠️ Hardcoding a profile or explicit credentials breaks tests (and workloads) in environments like ECS, where credentials come only from the metadata service.

✅ Action Item: Refactor all service classes (IAMService, GlueService, etc.) to follow the KMS-style pattern:

Create clients with only region and version.

Never hardcode profile or credentials.

This guarantees all tests will run successfully from ECS, CI pipelines, and developer environments alike.


Lesson learned:

Any PHP service class used in tests or production on AWS compute environments must not hardcode profiles or credentials.

Always follow the KMS-style pattern, letting the SDK pick up credentials from environment variables, instance metadata, or IAM roles.