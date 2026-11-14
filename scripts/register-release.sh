#!/usr/bin/env bash
# Run from a checked-out release in administrator CloudShell. Never submits jobs.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tag=${1:?Usage: bash scripts/register-release.sh v0.1.4}
[[ $tag == v* ]] || { echo "Expected a version tag" >&2; exit 1; }
cd "$root"
# Use the registration code/config belonging to the requested image release.
[[ $(git rev-parse HEAD) == "$(git rev-parse --verify "refs/tags/$tag^{commit}")" ]] || {
    echo "Check out $tag before registering it." >&2; exit 1;
}
export AWS_REGION
AWS_REGION=$(jq -er .region infra/deployment.json)
export AWS_DEFAULT_REGION="$AWS_REGION"
account=$(jq -er '.oidc_role_arn | split(":")[4]' infra/deployment.json)
repository=$(jq -er .repository infra/registration.json)
digest=$(aws ecr describe-images --registry-id "$account" --repository-name "$repository" \
    --image-ids "imageTag=$tag" --query 'imageDetails[0].imageDigest' --output text)
[[ $digest =~ ^sha256:[[:xdigit:]]{64}$ ]] || {
    echo "No valid published digest for $tag. Check the GitHub publish job." >&2; exit 1;
}
export IMAGE_URI="$account.dkr.ecr.$AWS_REGION.amazonaws.com/$repository@$digest"
export JOB_ROLE_ARN EFS_ID ACCESS_POINT_ID DATA_S3_URI DATA_VERSION RESULTS_S3_URI
JOB_ROLE_ARN=$(jq -er .job_role_arn infra/registration.json)
EFS_ID=$(jq -er .efs_id infra/registration.json)
ACCESS_POINT_ID=$(jq -er .access_point_id infra/registration.json)
DATA_S3_URI=$(jq -er .data_s3_uri infra/registration.json)
DATA_VERSION=$(jq -er .data_version infra/registration.json)
RESULTS_S3_URI=$(jq -er .results_s3_uri infra/registration.json)
echo "Registering $tag: $IMAGE_URI" >&2
bash scripts/register-definitions.sh | jq .
