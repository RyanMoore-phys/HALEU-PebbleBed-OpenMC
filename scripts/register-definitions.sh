#!/usr/bin/env bash
# Run in an administrator's AWS CloudShell after the image has been published.
set -euo pipefail
: "${IMAGE_URI:?Use ECR URI with digest}" "${JOB_ROLE_ARN:?}" "${AWS_REGION:?}"
: "${EFS_ID:?}" "${ACCESS_POINT_ID:?}" "${DATA_S3_URI:?}" "${DATA_VERSION:?}" "${RESULTS_S3_URI:?}"
[[ $IMAGE_URI =~ ^[[:digit:]]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/[a-z0-9/._-]+@sha256:[[:xdigit:]]{64}$ ]] || {
    echo "IMAGE_URI must be a full ECR digest URI with a 12-digit account ID" >&2
    exit 1
}
export IMAGE_URI JOB_ROLE_ARN EFS_ID ACCESS_POINT_ID DATA_S3_URI DATA_VERSION RESULTS_S3_URI AWS_REGION
defs='{}'
for stage in seed geometry smoke mpi-check mpi-smoke production mhtgr-geometry mhtgr-cold mhtgr-pilot mhtgr-depletion; do
    nodes=1
    vcpus=16
    instance_type=''
    mode=$stage
    case "$stage" in
        mpi-check) nodes=2 ;;
        mpi-smoke) nodes=2; mode=smoke ;;
        production) nodes=8 ;;
        mhtgr-pilot) nodes=2 ;;
        mhtgr-depletion) nodes=8; vcpus=4; instance_type=r7i.xlarge ;;
    esac
    definition=$(jq -n --arg stage "$stage" --arg mode "$mode" --argjson nodes "$nodes" --arg vcpus "$vcpus" --arg instance_type "$instance_type" '
      def setting($n;$v): {name:$n,value:$v};
      def container: {
        image:env.IMAGE_URI, jobRoleArn:env.JOB_ROLE_ARN, command:[$mode],
        resourceRequirements:[{type:"VCPU",value:$vcpus},{type:"MEMORY",value:"28672"}],
        environment:[
          setting("OMP_NUM_THREADS";$vcpus),setting("DATA_VERSION";env.DATA_VERSION),
          setting("DATA_S3_URI";env.DATA_S3_URI),setting("RESULTS_S3_URI";env.RESULTS_S3_URI),
          setting("OPENMC_CHAIN_FILE";"/mnt/efs/data/"+env.DATA_VERSION+"/chain.xml"),
          setting("OPENMC_CROSS_SECTIONS";"/mnt/efs/data/"+env.DATA_VERSION+"/lib80x_hdf5/cross_sections.xml")],
        volumes:[{name:"shared",efsVolumeConfiguration:{fileSystemId:env.EFS_ID,
          transitEncryption:"ENABLED",authorizationConfig:{accessPointId:env.ACCESS_POINT_ID,iam:"ENABLED"}}}],
        mountPoints:[{sourceVolume:"shared",containerPath:"/mnt/efs",readOnly:false}],
        logConfiguration:{logDriver:"awslogs",options:{"awslogs-group":"/aws/batch/block-depletion",
          "awslogs-region":env.AWS_REGION,"awslogs-stream-prefix":"block"}}
      };
      {jobDefinitionName:("block-"+$stage),retryStrategy:{attempts:1},
       timeout:{attemptDurationSeconds:(if $stage=="mhtgr-depletion" then 172800 elif $stage=="production" then 86400 elif $stage=="mpi-check" then 600 else 7200 end)}}
      + if $nodes==1 then {type:"container",containerProperties:container}
        else {type:"multinode",nodeProperties:{numNodes:$nodes,mainNode:0,
              nodeRangeProperties:[{targetNodes:"0:",container:(container
                + if $instance_type != "" then {instanceType:$instance_type} else {} end)}]}} end')
    arn=$(aws batch register-job-definition --cli-input-json "$definition" --query jobDefinitionArn --output text)
    defs=$(jq -c --arg stage "$stage" --arg arn "$arn" '.[$stage]=$arn' <<<"$defs")
done
echo "$defs"
