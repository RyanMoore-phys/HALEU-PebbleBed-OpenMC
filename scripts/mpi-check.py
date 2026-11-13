"""Exercise the MPI data path between two Batch nodes."""
import socket

from mpi4py import MPI

comm = MPI.COMM_WORLD
rank = comm.Get_rank()
host = socket.gethostname()
print(f"Rank {rank} on {host}: MPI initialized", flush=True)
if comm.Get_size() != 2:
    raise SystemExit("Expected exactly two ranks")
hosts = comm.allgather(host)
if len(set(hosts)) != 2:
    raise SystemExit(f"Expected two distinct hosts, got {hosts}")

peer = 1 - rank
for size in (64, 1024 * 1024):
    outgoing = bytes([rank + 1]) * size
    incoming = bytearray(size)
    print(f"Rank {rank}: exchanging {size} bytes with rank {peer}", flush=True)
    comm.Sendrecv([outgoing, MPI.BYTE], dest=peer,
                  recvbuf=[incoming, MPI.BYTE], source=peer)
    if incoming != bytes([peer + 1]) * size:
        raise SystemExit(f"Payload mismatch on rank {rank}")
comm.Barrier()
if rank == 0:
    print(f"MPI CHECK PASSED: bidirectional exchange on {hosts}", flush=True)
