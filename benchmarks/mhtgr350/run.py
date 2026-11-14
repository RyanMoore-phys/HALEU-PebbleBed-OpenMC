"""AWS-only benchmark driver. Run with python -m benchmarks.mhtgr350.run."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from mpi4py import MPI
import openmc
import openmc.deplete
import openmc.deplete.pool
import openmc.lib

from .layout import timesteps, validate_case
from .model import HERE, build


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--case',type=Path,required=True)
    cli.add_argument('--run-dir',type=Path,required=True)
    args = cli.parse_args()
    case = json.loads(args.case.read_text())
    validate_case(case)
    comm = MPI.COMM_WORLD
    xs = Path(os.environ['OPENMC_CROSS_SECTIONS']).resolve(strict=True)
    chain = Path(os.environ['OPENMC_CHAIN_FILE']).resolve(strict=True)
    openmc.config['cross_sections'] = str(xs)
    if comm.rank==0:
        args.run_dir.mkdir(parents=True,exist_ok=False)
    comm.Barrier()
    os.chdir(args.run_dir)
    if comm.rank==0:
        print('Building explicit-TRISO benchmark geometry...',flush=True)
        print(f'Temperature: {case["temperature_K"]} K; interpolation endpoint '
              f'tolerance: {case["temperature_tolerance_K"]} K.',flush=True)
        if case['exercise']=='1a':
            print('Cold-case approximation: the supplied VIII.0 graphite table starts '
                  'at 296 K; the 3 K tolerance permits its use at 293.6 K.',flush=True)
    model,fuels,pins,audit = build(case)
    if comm.rank==0:
        print(f'Geometry built: {len(fuels)} fuel materials; '
              f'{audit["kernels_per_compact"]} kernels per compact; '
              'automatic material-cell offset tables disabled.',flush=True)
    hashes = comm.allgather(audit['packing_sha256'])
    if len(set(hashes)) != 1:
        raise ValueError('MPI ranks built different TRISO packings')
    if comm.rank==0:
        Path('geometry-audit.json').write_text(json.dumps(audit,indent=2))
        Path('pin-map.json').write_text(json.dumps(pins,indent=2))
    spec = json.loads((HERE/'specification.json').read_text())
    meta = dict(benchmark=spec['id'],case=case,ranks=comm.size,
                threads=int(os.environ.get('OMP_NUM_THREADS','16')),pins=pins,
                openmc_version=openmc.__version__,audit=audit,
                specification_sha256=sha256(HERE/'specification.json'),
                reference_sha256=sha256(HERE/'reference.json'),
                cross_sections=str(xs),cross_sections_xml_sha256=sha256(xs),
                chain=str(chain),chain_sha256=sha256(chain),
                normalization='fission-q, central depletable fuel only',
                status='started; no completed benchmark result yet')
    manifest = xs.parent.parent/'SHA256SUMS'
    meta['data_manifest_sha256'] = sha256(manifest) if manifest.is_file() else None
    def save_meta():
        if comm.rank==0:
            Path('run.json').write_text(json.dumps(meta,indent=2))
    save_meta()
    if case['mode']=='geometry':
        if comm.size!=1:
            raise ValueError('Geometry-debug stage requires one rank')
        for name,width,origin,basis in [
            ('supercell-xy',(126,110),(0,0,0),'xy'),
            ('block-xy',(43,38),(0,0,0),'xy'),
            ('slice-xz',(43,case['slice_height_cm']*1.1),(0,0,0),'xz'),
            ('compact-xy',(1.4,1.4),(pins[0]['x'],pins[0]['y'],0),'xy')]:
            plot = openmc.Plot()
            plot.filename,plot.basis,plot.origin,plot.width = name,basis,origin,width
            plot.pixels = (1400,1200)
            plot.color_by = 'material'
            model.plots.append(plot)
        model.export_to_model_xml()
        print('Geometry XML exported; starting OpenMC plotting...',flush=True)
        openmc.plot_geometry()
        print('Plotting completed; starting OpenMC geometry-debug...',flush=True)
        model.run(geometry_debug=True)
        print('OpenMC geometry-debug completed.',flush=True)
        audit['geometry_debug']='completed; inspect log for unchecked cells'
        Path('geometry-audit.json').write_text(json.dumps(audit,indent=2))
    elif case['mode']=='transport':
        model.init_lib(threads=meta['threads'],intracomm=comm)
        try:
            openmc.lib.run()
        finally:
            openmc.lib.finalize()
    elif case['mode']=='depletion':
        openmc.deplete.pool.USE_MULTIPROCESSING = False
        operator = openmc.deplete.CoupledOperator(model,chain_file=str(chain),normalization_mode='fission-q')
        meta['initial_hm_g'] = operator.heavy_metal
        meta['specific_power_W_gHM'] = spec['specific_power_W_gHM']
        meta['slice_power_W'] = spec['specific_power_W_gHM']*operator.heavy_metal
        steps = timesteps(case['report_burnup_MWd_kgHM'],case['max_step_MWd_kgHM'])
        meta['timesteps_MWd_kgHM'] = steps
        save_meta()
        # MWd/kgHM and GWd/tHM are numerically identical. 100 W/gHM -> 0.1 MWd/kgHM/day.
        days = [b*1000/spec['specific_power_W_gHM'] for b in steps]
        openmc.deplete.CECMIntegrator(operator,days,power=meta['slice_power_W'],
                                     timestep_units='d').integrate()
    else:
        raise ValueError('Unknown benchmark mode')
    comm.Barrier()
    meta['status']='calculation_completed; comparison follows'
    save_meta()


if __name__=='__main__':
    main()
