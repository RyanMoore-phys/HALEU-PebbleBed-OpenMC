#!/usr/bin/env bash
set -euo pipefail
umask 077
mode=${1:-smoke}
root=/mnt/efs
case "$mode" in
  seed)
    : "${DATA_S3_URI:?}" "${DATA_VERSION:?}"
    [[ $DATA_VERSION =~ ^[A-Za-z0-9._-]+$ && $DATA_VERSION != .* ]]
    mkdir -p "$root/data"
    dest="$root/data/$DATA_VERSION"
    [[ ! -e $dest ]] || { echo "Data version already exists" >&2; exit 1; }
    stage=$(mktemp -d "$root/data/.stage.XXXXXXXX")
    aws s3 sync "$DATA_S3_URI/" "$stage/" --only-show-errors
    (cd "$stage" && sha256sum --check --strict SHA256SUMS && test -s lib80x_hdf5/cross_sections.xml && test -s chain.xml)
    mv -T "$stage" "$dest"
    exit 0 ;;
  geometry|smoke|mpi-check|production) ;;
  *) echo "Unknown mode: $mode" >&2; exit 2 ;;
esac
: "${RESULTS_S3_URI:?}" "${OPENMC_CHAIN_FILE:?}" "${OPENMC_CROSS_SECTIONS:?}"
nodes=${AWS_BATCH_JOB_NUM_NODES:-1}
index=${AWS_BATCH_JOB_NODE_INDEX:-0}
main=${AWS_BATCH_JOB_MAIN_NODE_INDEX:-0}
trap 'echo "Launcher failed on node $index at line $LINENO (exit $?)" >&2' ERR
job=${AWS_BATCH_JOB_ID%%#*}
if [[ $nodes != 1 ]]; then
    job=${SHARED_RUN_ID:?All MPI nodes need the same run ID}
    [[ $job =~ ^[A-Za-z0-9_-]+$ ]] || { echo "Invalid SHARED_RUN_ID" >&2; exit 1; }
    echo "Starting MPI rendezvous on node $index of $nodes"
fi
attempt="$job/attempt-${AWS_BATCH_JOB_ATTEMPT:-1}"
work="$root/runs/$attempt"
run="$work/output"
mkdir -p "$work"
casefile=/app/cases/block-smoke.json
[[ $mode != production ]] || casefile=/app/cases/block-production.json
driver=(/opt/block/bin/python -m mpi4py /app/block_depletion.py --case "$casefile" --run-dir "$run")
launcher=()
if [[ $mode == mpi-check ]]; then
    [[ $nodes == 2 ]] || { echo "mpi-check requires two nodes" >&2; exit 1; }
    driver=(/opt/block/bin/python -u -m mpi4py /app/scripts/mpi-check.py)
    launcher=(timeout --kill-after=10s 120s)
fi
if [[ $mode == geometry ]]; then
    [[ $nodes == 1 ]]
    driver+=(--check-geometry)
fi
if [[ $nodes == 1 ]]; then
    "${driver[@]}"
else
    # Each host keeps its SSH host secret locally; EFS carries the job-scoped MPI identity.
    mesh="$work/mpi"
    mkdir -p "$mesh" /root/.ssh /run/sshd
    chmod 700 /root/.ssh
    if [[ $index == "$main" ]]; then
        ssh-keygen -q -t ed25519 -N '' -f "$mesh/identity"
        touch "$mesh/identity.ready"
    fi
    deadline=$((SECONDS + 1200))
    wait_file() {
        until [[ -e $1 ]]; do
            (( SECONDS < deadline )) || { echo "Timed out waiting for $1" >&2; exit 1; }
            sleep 2
        done
    }
    wait_file "$mesh/identity.ready"
    install -m 600 "$mesh/identity" /root/.ssh/id_ed25519
    install -m 600 "$mesh/identity.pub" /root/.ssh/authorized_keys
    ssh-keygen -q -t ed25519 -N '' -f /run/sshd/job_host_key
    /usr/sbin/sshd -h /run/sshd/job_host_key -o PermitRootLogin=prohibit-password -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o UsePAM=yes
    ipaddr=$(/opt/block/bin/python - <<'PY'
import json
import os
from urllib.request import urlopen

with urlopen(os.environ["ECS_CONTAINER_METADATA_URI_V4"], timeout=10) as response:
    networks = json.load(response)["Networks"]
addresses = [ip for network in networks if network["NetworkMode"] == "awsvpc"
             for ip in network.get("IPv4Addresses", [])]
if len(addresses) != 1:
    raise SystemExit(f"Expected one task ENI IPv4 address, found {addresses}")
print(addresses[0])
PY
)
    read -r kind pub _ < /run/sshd/job_host_key.pub
    echo "$ipaddr $kind $pub" > "$mesh/$index.tmp"
    cat > /root/.ssh/config <<EOF
Host *
    BatchMode yes
    StrictHostKeyChecking yes
    UserKnownHostsFile $mesh/known_hosts
EOF
    mv "$mesh/$index.tmp" "$mesh/$index.host"
    echo "Node $index ready at $ipaddr"
    if [[ $mode == mpi-check ]]; then
        ip -brief -4 address
    fi
    if [[ $index != "$main" ]]; then
        exec sleep infinity
    fi
    trap 'rm -f "$mesh/identity"' EXIT
    for ((i=0; i<nodes; i++)); do wait_file "$mesh/$i.host"; done
    cat "$mesh"/*.host > "$mesh/known_hosts"
    awk '{print $1 " slots=1"}' "$mesh/known_hosts" > "$mesh/hostfile"
    cat "$mesh/hostfile"
    if (( $(sort -u "$mesh/hostfile" | wc -l) != nodes )); then
        echo "Expected $nodes distinct MPI hosts in hostfile" >&2
        exit 1
    fi
    # One rank owns each node. OpenMP binds its 16 threads to hardware threads.
    export OMP_PLACES=threads OMP_PROC_BIND=spread
    # Restrict MPI payload traffic to the task ENIs, excluding ECS local interfaces.
    # This CIDR matches the deployed Batch subnet; override if that subnet changes.
    mpi_tcp_subnet=${MPI_TCP_SUBNET:-10.72.1.0/24}
    echo "MPI transport: ob1 / self,tcp; TCP subnet: $mpi_tcp_subnet"
    "${launcher[@]}" mpirun --allow-run-as-root --prefix /opt/block --hostfile "$mesh/hostfile" -np "$nodes" \
      --mca pml ob1 --mca btl self,tcp --mca btl_tcp_if_include "$mpi_tcp_subnet" \
      --map-by ppr:1:node --bind-to none --display-map --wdir /app \
      -x OMP_NUM_THREADS -x OMP_PLACES -x OMP_PROC_BIND -x OPENBLAS_NUM_THREADS \
      -x OPENMC_CROSS_SECTIONS -x OPENMC_CHAIN_FILE -x MPLBACKEND "${driver[@]}"
fi
if [[ $mode == mpi-check ]]; then
    exit 0
fi
if [[ $mode != geometry ]]; then
    python /app/plot_block_results.py --run-dir "$run"
fi
aws s3 sync "$run/" "$RESULTS_S3_URI/$attempt/" --only-show-errors
