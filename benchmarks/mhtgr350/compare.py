"""Generate traceable k comparisons; never substitute reference data for results."""
import argparse
import csv
import html
import json
import math
import hashlib
from pathlib import Path


def compare_rows(exercise, targets, actual, references, max_bias, max_sigma):
    """Pure comparison logic. No interpolation across missing burnup points."""
    rows = []
    for target in targets:
        matches = [r for r in actual if math.isclose(r['burnup'],target,rel_tol=0,abs_tol=1e-7)]
        reference = next((r for r in references[exercise] if r['burnup']==target),None)
        if len(matches)!=1 or reference is None:
            raise ValueError(f'Missing/duplicate result or reference at burnup {target}')
        result = matches[0]
        k,sigma = result['k'],result['sigma']
        if not (math.isfinite(k) and k>0 and math.isfinite(sigma) and sigma>0):
            raise ValueError('Invalid k estimate or statistical uncertainty')
        delta = 1e5*(k-reference['mean'])
        # Distinguish delta-k pcm from reactivity pcm; do not mix the definitions.
        rho = 1e5*(1/reference['mean']-1/k)
        rows.append(dict(burnup=target,k=k,sigma=sigma,reference_mean=reference['mean'],
                         reference_sd_pcm=reference['sd_pcm'],SERPENT=reference['SERPENT'],
                         McCARD=reference['McCARD'],delta_k_pcm=delta,delta_rho_pcm=rho,
                         sigma_pcm=sigma*1e5,
                         screening_pass=abs(delta)<=max_bias and sigma*1e5<=max_sigma))
    return rows


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--run-dir',type=Path,required=True)
    directory = cli.parse_args().run_dir
    meta = json.loads((directory/'run.json').read_text())
    case = meta['case']
    reference = json.loads((Path(__file__).parent/'reference.json').read_text())
    for filename,key in [('reference.json','reference_sha256'),('specification.json','specification_sha256')]:
        digest=hashlib.sha256((Path(__file__).parent/filename).read_bytes()).hexdigest()
        if meta[key]!=digest:
            raise ValueError(f'{filename} changed since the calculation')
    if meta['status']!='calculation_completed; comparison follows':
        raise ValueError('Calculation has not completed')
    import numpy as np
    import matplotlib.pyplot as plt
    import openmc
    import openmc.deplete
    if case['mode']=='transport':
        with openmc.StatePoint(directory/f'statepoint.{case["batches"]}.h5') as sp:
            actual = [dict(burnup=0,k=sp.keff.nominal_value,sigma=sp.keff.std_dev)]
            entropy = np.asarray(sp.entropy).tolist()
            generation_k = np.asarray(sp.k_generation).tolist()
    else:
        results = openmc.deplete.Results(directory/'depletion_results.h5')
        days,k = results.get_keff(time_units='d')
        burnup = days*meta['specific_power_W_gHM']/1000
        expected = np.concatenate(([0.],np.cumsum(meta['timesteps_MWd_kgHM'])))
        if len(burnup)!=len(expected) or not np.allclose(burnup,expected,rtol=0,atol=1e-7):
            raise ValueError('Incomplete or mismatched depletion history')
        actual = [dict(burnup=float(b),k=float(v[0]),sigma=float(v[1])) for b,v in zip(burnup,k)]
        entropy,generation_k = [],[]
        # Keep inventories separate by pin. No invented published reference values.
        with (directory/'pin-inventories.csv').open('w',newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['pin','nuclide','burnup_MWd_kgHM','atom_b_cm'])
            for pin in meta['pins']:
                for nuclide in ('U235','U238','Pu239','Xe135','Sm149'):
                    _,atoms = results.get_atoms(str(pin['material_id']),nuclide)
                    for b,a in zip(burnup,atoms):
                        writer.writerow([pin['pin'],nuclide,float(b),float(a)/pin['volume_cm3']*1e-24])
    rows = compare_rows(case['exercise'],case['report_burnup_MWd_kgHM'],actual,reference,
                        case['max_abs_delta_k_pcm'],case['max_k_sigma_pcm'])
    passed = all(r['screening_pass'] for r in rows)
    caveats = [
        'Numerical code-to-code comparison, not experimental validation or reactor certification.',
        'Screening limits are project settings, not OECD/NEA acceptance criteria.',
        'Reference SD is between-code spread, not experimental uncertainty.',
        'Nuclear data: '+case['nuclear_data_label'],
        'Preferred reference library is ENDF/B-VII.0; library/chain differences must be investigated.',
        'Axially uniform reflective slice; repeat with changed slice height and packing seed.',
        'Source convergence and timestep sensitivity require separate runs; a green screen does not establish them.',
        'Only multiplication factor is automatically compared. Pin inventories are exported without a reference comparison.'
    ]
    caveats.append(f'Temperature interpolation endpoint tolerance: {case["temperature_tolerance_K"]} K.')
    if case['exercise']=='1a':
        caveats.append('Cold data approximation: the supplied VIII.0 graphite thermal table '
                       'starts at 296 K and is permitted at the requested 293.6 K. '
                       'This is not an exact-temperature reproduction.')
    report = dict(status='screening_pass' if passed else 'screening_fail',
                  validation_status='not_validated',exercise=case['exercise'],rows=rows,
                  limits=dict(max_abs_delta_k_pcm=case['max_abs_delta_k_pcm'],max_k_sigma_pcm=case['max_k_sigma_pcm']),
                  reference=reference['url'],reference_report=reference['report'],caveats=caveats,
                  source_entropy=entropy,k_generation=generation_k)
    (directory/'comparison.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    with (directory/'comparison.csv').open('w',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    fig,axes = plt.subplots(2,1,figsize=(9,7),layout='constrained',sharex=True)
    refs = [r for r in reference[case['exercise']] if r['burnup']<=max(case['report_burnup_MWd_kgHM'])]
    x = np.array([r['burnup'] for r in refs]); y=np.array([r['mean'] for r in refs])
    sd = np.array([r['sd_pcm'] for r in refs])*1e-5
    axes[0].plot(x,y,'o-',label='Published code mean')
    axes[0].fill_between(x,y-sd,y+sd,alpha=.2,label='Published code spread (1 SD)')
    axes[0].errorbar([r['burnup'] for r in actual],[r['k'] for r in actual],
                     yerr=[r['sigma'] for r in actual],fmt='.-',label='OpenMC ±1 statistical SD')
    axes[0].set(ylabel='Supercell multiplication factor',title=f'MHTGR exercise {case["exercise"]}: {report["status"]}')
    axes[0].legend()
    axes[1].errorbar([r['burnup'] for r in rows],[r['delta_k_pcm'] for r in rows],
                     yerr=[r['sigma_pcm'] for r in rows],fmt='o-')
    axes[1].axhline(0,color='black',linewidth=.8)
    for sign in (-1,1): axes[1].axhline(sign*case['max_abs_delta_k_pcm'],color='red',linestyle='--')
    axes[1].set(xlabel='Burnup (MWd/kg initial HM)',ylabel='Δk × 100,000')
    fig.savefig(directory/'benchmark-comparison.png',dpi=150); plt.close(fig)
    if entropy:
        fig,axes=plt.subplots(2,1,figsize=(9,6),layout='constrained')
        axes[0].plot(generation_k); axes[0].set_ylabel('Generation k')
        axes[1].plot(entropy); axes[1].set_ylabel('Source entropy'); axes[1].set_xlabel('Generation index')
        for ax in axes:ax.axvline(case['inactive'],color='red',linestyle='--')
        fig.savefig(directory/'source-convergence.png',dpi=150); plt.close(fig)
    lines = [f'# MHTGR exercise {case["exercise"]}: {report["status"]}',
             '',f'Reference: {reference["url"]}','',
             '| Burnup | OpenMC k | σ(k) | Reference mean | Δk × 100,000 | Screen |',
             '|---:|---:|---:|---:|---:|---|']
    lines += [f'| {r["burnup"]:g} | {r["k"]:.6f} | {r["sigma"]:.6f} | {r["reference_mean"]:.6f} | {r["delta_k_pcm"]:.1f} | {r["screening_pass"]} |' for r in rows]
    lines += ['','## Interpretation','']+['- '+c for c in caveats]
    summary='\n'.join(lines)+'\n'
    (directory/'comparison.md').write_text(summary)
    (directory/'comparison.html').write_text('<!doctype html><meta charset="utf-8"><title>MHTGR comparison</title>'
        '<style>body{font:16px system-ui;max-width:1100px;margin:40px auto}pre{white-space:pre-wrap}img{max-width:100%}</style>'
        '<h1>MHTGR benchmark comparison</h1><img src="benchmark-comparison.png" alt="Benchmark comparison">'
        '<pre>'+html.escape(summary)+'</pre>')
    print(summary,flush=True)
    # Caller uploads even a failed comparison before propagating this status to Batch.
    return 0 if passed else 2


if __name__=='__main__':
    raise SystemExit(main())
