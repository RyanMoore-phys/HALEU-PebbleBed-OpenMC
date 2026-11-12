# One graphite block on AWS Batch

Production is one On-Demand Batch job with eight EC2 nodes. Each node runs one MPI rank and 16 OpenMP threads, for 128 vCPUs total. All ranks work on the same transport calculation at each depletion step. The supplied workflows build on GitHub and execute on AWS. Your quota and OIDC changes are already complete. The first build, infrastructure validation, and runtime tests are still to be performed remotely.

## Phase 0 — Choose the deployment region and AZ

Use the region of your approved Standard On-Demand quota. Pick one AZ offering c7i.4xlarge. In EC2 → Instance Types, confirm 16 vCPUs and the memory available. In VPC, check that the project's 10.72.0.0/16 allocation fits your networking plan. Adjust infra/core/main.tf before the first apply if necessary. Keep the private subnet, EFS mount target, interface endpoints and placement group in the same AZ. Verify available vCPU headroom at launch. [AWS MNP compute environment requirements](https://docs.aws.amazon.com/batch/latest/userguide/mnp-ce.html)

## Phase 1 — Set the model inputs

| File | What to do |
|---|---|
| cases/block.json | Review the illustrative block edge and height, compact dimensions, pitch, temperature, packing and outer-to-inner ring map. F is a fuel compact and G is graphite. The center must contain fuel for the source. The included map has 19 physical compacts. |
| cases/block-smoke.json | Use the short one-step history for infrastructure verification. The 1 W/g initial heavy-metal value is an illustrative normalization. |
| cases/block-production.json | Set specific_power_W_gHM to your chosen positive study value. For known block power, divide thermal watts by initial_hm_g from the smoke output for the same geometry. Review step_days, steps, batches and particles before tagging this revision. |
| block_model.py | Edit here only to change the fuel recipe, coating specification or geometry implementation. It keeps the legacy atom fractions and coatings. It models a finite, vacuum-bounded graphite block with cylindrical TRISO compacts and one shared fuel inventory. |
| block_depletion.py | Batch runs this driver. It multiplies kernels per compact by physical compact count for total kernel volume, uses the coupled operator's initial heavy-metal mass, and applies constant thermal power over sequential steps. |
| plot_block_results.py | The launcher runs this once after depletion. It checks the time history and writes block-depletion.png. |

The dimensions and prescribed power are study assumptions. The model omits heat pipes, coolant, thermal feedback and surrounding blocks. Confirm enrichment on your intended mass or atom basis, material temperatures and the suitability of your depletion chain. The old pebble scripts and notebooks are independent of this run. [OpenMC depletion guide](https://docs.openmc.org/en/stable/usersguide/depletion.html)

## Phase 2 — Prepare the image release

Commit the supplied files to your GitHub repository on main. Dockerfile, environment.yml and .dockerignore define the Linux AMD64 image and its MPI-enabled environment. The first v* tag builds it on a GitHub-hosted runner. Wait until Phase 5 creates ECR before pushing that tag. Nuclear data is mounted separately. Production power may be supplied in a later tagged release after smoke results are available.

## Phase 3 — Administrator bootstrap

1. Create or reuse a private, encrypted, versioned S3 state bucket in the selected region. Block public access. Reserve block/core.tfstate and block/campaign.tfstate and their .tflock objects. Actions needs bucket listing, state read/write and lock read/write/delete on these paths. Keep administrator state elsewhere. [OpenTofu S3 backend](https://opentofu.org/docs/language/settings/backends/s3/)
2. As administrator, verify AWSServiceRoleForBatch and the ECS EC2 instance role/profile exist. The instance role trusts ec2.amazonaws.com and needs ECS registration, ECR image pull and log delivery permissions. The job role trusts ecs-tasks.amazonaws.com. Grant it s3:ListBucket for the selected prefixes, s3:GetObject on the data bundle, s3:PutObject and multipart upload permissions on the results prefix, and elasticfilesystem:ClientMount and ClientWrite for the project file system and access point. Fill in the generated resource IDs after Phase 5. The administrator passes the required roles. [Batch instance role](https://docs.aws.amazon.com/batch/latest/userguide/instance_IAM_role.html) · [EFS client IAM](https://docs.aws.amazon.com/efs/latest/ug/iam-access-control-nfs-efs.html)
3. Keep all iam:* actions, including iam:PassRole, out of the project OIDC role. Its workflows use state S3, project infrastructure APIs, ECR publish and Batch submission. The definition builder runs under the administrator identity. Confirm your existing trust covers main for dispatch and refs/tags/v* for publishing. The workflows read deployment identifiers from the checked-in infra/deployment.json and authenticate through OIDC. [GitHub OIDC subjects](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)

## Phase 4 — Configure the repository

Before committing, fill in region, availability_zone, oidc_role_arn and state_bucket in [infra/deployment.json](infra/deployment.json). Use the imported subnet’s actual AZ and the bare name of the existing state bucket. The Batch definitions can stay null through infrastructure setup. In Actions select **Block infrastructure**, choose main, core and plan. Check that the VPC, subnet, route table and explicit association in infra/core/import.tf are imported with no replacements on the first apply, then dispatch core/apply. The workflow runs tofu init, validate, plan and apply on GitHub. Its summary gives the subnet and security group IDs, EFS identifiers, bucket names and ECR URI. Image publication builds the repository URI from the authenticated ECR registry and the core repository name. [Infrastructure workflow](.github/workflows/infra.yml)

## Phase 5 — Verify the persistent VPC and storage

In VPC → Your VPCs, find block-vpc and check DNS support and hostnames. Open block-private and check its AZ, 10.72.1.0/24 range and disabled public IPv4 assignment. Its associated route table should have a VPC-local route and an S3 prefix-list route through the gateway endpoint. Nodes have private addresses. The node security group allows peer traffic for SSH/MPI. The EFS group accepts TCP 2049 from the node group. The endpoint group accepts TCP 443 from that group. In EFS, check the mount target is available in the selected subnet and the access point uses /block and UID/GID 1000. In ECR find block-depletion. In CloudWatch find /aws/batch/block-depletion. [ECR private endpoints](https://docs.aws.amazon.com/AmazonECR/latest/userguide/vpc-endpoints.html)

Push a reviewed v* tag, e.g. v0.1.0. In **Publish or submit block depletion → publish**, copy the resulting repository URI ending in @sha256:… from the summary.

## Phase 6 — Create campaign networking and Batch

1. In **Block infrastructure** run campaign/plan and then campaign/apply. In VPC → Endpoints check all six interface endpoints are Available with private DNS enabled: ecs, ecs-agent, ecs-telemetry, ecr.api, ecr.dkr and logs. The S3 gateway endpoint belongs to core. Nodes use these routes for runtime traffic. [ECS endpoint guide](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/vpc-endpoints.html)
2. As administrator open Batch → Compute environments → Create. Select **managed**, **Amazon EC2**, **On-Demand**, the Batch service-linked role and the existing ECS instance profile. Choose the current ECS-optimized Linux x86_64 AMI supported by Batch with EFS support. Select c7i.4xlarge only, minimum/desired 0 and maximum 128 vCPUs, the core private subnet and block-nodes security group. In additional settings select cluster placement group block-campaign. Use a Batch-compatible allocation strategy such as BEST_FIT_PROGRESSIVE. Wait for ENABLED and VALID. [MNP compute environment requirements](https://docs.aws.amazon.com/batch/latest/userguide/mnp-ce.html)
3. In Batch → Job queues create an enabled EC2 queue named block-queue with priority 1. Associate the new compute environment at order 1. The queue name matches the queue field in infra/deployment.json.
4. Open administrator AWS CloudShell in the same region. Obtain the tagged repository files there. Set the following with values from the account and workflow summaries. DATA_S3_URI and RESULTS_S3_URI have no trailing slash.

~~~sh
export AWS_REGION='YOUR_REGION'
export IMAGE_URI='YOUR_ECR_URI@sha256:YOUR_DIGEST'
export JOB_ROLE_ARN='YOUR_BATCH_JOB_ROLE_ARN'
export EFS_ID='fs-YOUR_ID'
export ACCESS_POINT_ID='fsap-YOUR_ID'
export DATA_VERSION='endfb80-v1'
export DATA_S3_URI='s3://YOUR_DATA_BUCKET/endfb80-v1'
export RESULTS_S3_URI='s3://YOUR_RESULTS_BUCKET/runs'
bash scripts/register-definitions.sh
~~~

Copy the final JSON object into the definitions field of infra/deployment.json and commit the mapping to main before dispatching a job. The script registers seed, geometry, smoke, mpi-smoke and production revisions. Every node requests 16 vCPUs and 28 GiB. Every definition mounts the access point at /mnt/efs with TLS and IAM authorization. The last two definitions launch two and eight nodes respectively. Registration launches no instances. Repeat registration and replace the JSON mapping when the image digest changes. [Batch EFS volumes](https://docs.aws.amazon.com/batch/latest/userguide/efs-volumes.html)

## Phase 7 — Stage nuclear data once

On the machine already holding your evaluated library, assemble a bundle containing lib80x_hdf5/cross_sections.xml, its referenced HDF5 files, and the chosen chain under the name chain.xml. Use relative library paths in the XML that resolve inside the bundle. From the bundle root on macOS, generate the manifest and upload the directory. These commands hash and transfer data.

~~~sh
find lib80x_hdf5 -type f -exec shasum -a 256 {} + > SHA256SUMS
shasum -a 256 chain.xml >> SHA256SUMS
aws s3 sync . s3://YOUR_DATA_BUCKET/endfb80-v1/
~~~

In GitHub Actions → **Publish or submit block depletion → Run workflow**, select main and seed. Follow the Batch job ID to CloudWatch. Wait for SUCCEEDED. The seed job validates SHA256SUMS before publishing the directory on EFS. A new data release gets a fresh version and definition revision.

## Phase 8 — Submit and collect results

Use the same workflow and choose a stage. A tag publishes an image; manual dispatch submits the registered job. After submission the GitHub runner exits. The Batch launcher coordinates MPI over private IPs, waits for peer readiness and runs the driver on EFS. Each attempt writes a new output directory. Successful runs upload to the configured results prefix. For MPI runs the prefix includes gha-<workflow-run-id>-<workflow-attempt>/attempt-1. Single-node runs use the Batch job ID. Failed runs retain CloudWatch logs and files already written to EFS. A fresh submission starts a new history. [Batch MNP lifecycle](https://docs.aws.amazon.com/batch/latest/userguide/job-lifecycle.html)

## Phase 9 — Verify on AWS and scale up

| Dispatch stage | Check before proceeding |
|---|---|
| geometry | Inspect the xy and xz images and geometry-debug coverage in CloudWatch. Confirm one hexagonal block, compact positions, graphite above and below, and absence of reported overlaps or lost particles. |
| smoke | Inspect run.json, depletion_results.h5 and block-depletion.png. Confirm 19 compacts for the supplied map, positive initial heavy-metal mass, the chosen power basis, and one completed interval. |
| mpi-smoke | Confirm two distinct hosts in the MPI map, two ranks and 16 threads per rank in run.json, one shared output and a complete history. Compare with the single-node smoke within Monte Carlo uncertainty. |
| production | Set the production specific power and check source convergence and step-size sensitivity for the intended study. If inputs changed, publish a fresh tag and register its digest. Dispatch production once. Verify eight hosts, eight ranks, 16 threads per rank, requested final time and the S3 upload. |

For a job stuck in RUNNABLE, check the queue status reason, free quota, subnet IPs and same-AZ instance capacity. For STARTING failures, inspect ECR endpoints and S3 routing, EFS mount target/security group and instance logs. For an MPI rendezvous failure inspect the per-node CloudWatch streams. Runtime and cost depend on the case and capacity.

## Phase 10 — Control spend and close the campaign

Set a billing alert at your chosen budget. Track EC2 instance hours, endpoint-AZ hours, EBS, EFS, ECR, S3 and logs. Scaling EC2 down to zero leaves interface endpoints billable. When finished, stop submissions and confirm all jobs are terminal and results are in S3. The administrator disables/removes the queue and then disables/removes the compute environment. Wait for its instances to terminate. In Actions run campaign/close-campaign to remove the six interface endpoints and placement group. Keep core for future campaigns. To reopen, repeat Phase 6 and update the checked-in queue name if it changes. [PrivateLink pricing](https://aws.amazon.com/privatelink/pricing/)

## Phase 11 — Update the diagram

In Project2.drawio draw the VPC and one private AZ subnet around the node ENIs, EFS mount target and six interface endpoints. Connect S3 through the gateway endpoint on the subnet route table. Outside the VPC show GitHub Actions publishing to ECR and submitting to Batch, and the independent administrator registering the digest and job role. Show eight nodes feeding a single results history on EFS and a final upload to S3.
