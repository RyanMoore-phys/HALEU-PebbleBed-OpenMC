"""Read one completed constant-power run."""
import argparse
import json

import matplotlib.pyplot as plt
import numpy as np
import openmc.deplete
from pathlib import Path


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--run-dir", type=Path, required=True)
    directory = cli.parse_args().run_dir
    meta = json.loads((directory / "run.json").read_text())
    results = openmc.deplete.Results(directory / "depletion_results.h5")
    days, k = results.get_keff(time_units="d")
    case = meta["case"]
    if len(days) != case["steps"] + 1 or not np.isclose(days[-1], case["steps"] * case["step_days"]):
        raise ValueError("Depletion history is incomplete")
    burnup = days * meta["block_power_W"] / (1000 * meta["initial_hm_g"])
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
    axes[0].errorbar(burnup, k[:, 0], yerr=k[:, 1], marker="o")
    axes[0].set(xlabel="Burnup (MWd/kg initial HM)", ylabel="Block k-effective")
    for isotope in ("U235", "Xe135"):
        _, atoms = results.get_atoms(str(meta["fuel_id"]), isotope)
        axes[1].plot(days, atoms, marker=".", label=isotope)
    axes[1].set(xlabel="Time at assigned power (days)", ylabel="Atoms", yscale="symlog")
    axes[1].legend()
    fig.savefig(directory / "block-depletion.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
