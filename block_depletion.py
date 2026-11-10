"""Run one constant-specific-power depletion history in a new directory."""
import argparse
import json
import math
import os
from pathlib import Path

from mpi4py import MPI
import openmc
import openmc.deplete
import openmc.deplete.pool

from block_model import build_model


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--case", type=Path, required=True)
    cli.add_argument("--run-dir", type=Path, required=True)
    cli.add_argument("--check-geometry", action="store_true")
    args = cli.parse_args()
    case = json.loads(args.case.read_text())
    geometry = json.loads((args.case.parent / case["geometry"]).read_text())
    chain = Path(os.environ["OPENMC_CHAIN_FILE"]).resolve(strict=True)
    xs = Path(os.environ["OPENMC_CROSS_SECTIONS"]).resolve(strict=True)
    openmc.config["cross_sections"] = str(xs)
    specific = case["specific_power_W_gHM"]
    if not args.check_geometry and not (specific and math.isfinite(specific) and specific > 0):
        raise ValueError("Set positive specific_power_W_gHM in the selected case")
    if case["steps"] < 1 or case["step_days"] <= 0 or case["inactive"] >= case["batches"]:
        raise ValueError("Check timestep count, duration and inactive batches")
    comm = MPI.COMM_WORLD
    if comm.rank == 0:
        args.run_dir.mkdir(parents=True, exist_ok=False)
    comm.Barrier()
    os.chdir(args.run_dir)
    model, fuel, counts = build_model(geometry, case)
    if args.check_geometry:
        if comm.size != 1:
            raise ValueError("Use one node and rank for geometry checks")
        for basis in ("xy", "xz"):
            plot = openmc.Plot()
            plot.basis, plot.color_by, plot.filename = basis, "material", basis
            edge = geometry["block_edge_cm"]
            plot.width = (2.2*edge, 2.2*edge if basis == "xy" else 1.1*geometry["block_height_cm"])
            model.plots.append(plot)
        model.export_to_model_xml()
        openmc.plot_geometry()
        model.run(geometry_debug=True)
        return
    openmc.deplete.pool.USE_MULTIPROCESSING = False
    operator = openmc.deplete.CoupledOperator(model, chain_file=str(chain))
    power = specific * operator.heavy_metal
    if comm.rank == 0:
        metadata = dict(counts, case=case, geometry=geometry, fuel_id=fuel.id,
                        fuel_volume_cm3=fuel.volume, initial_hm_g=operator.heavy_metal,
                        block_power_W=power, ranks=comm.size, threads=os.environ.get("OMP_NUM_THREADS"),
                        cross_sections=str(xs), chain=str(chain))
        Path("run.json").write_text(json.dumps(metadata, indent=2))
    openmc.deplete.PredictorIntegrator(operator, [case["step_days"]] * case["steps"],
                                       power=power, timestep_units="d").integrate()


if __name__ == "__main__":
    main()
