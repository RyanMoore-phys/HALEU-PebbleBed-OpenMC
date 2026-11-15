# Cold benchmark audit and next-run guide

Audit date: 2026-11-15 UTC. Status: **unresolved benchmark mismatch**.
This review used source inspection, the published specification/report and existing
AWS artifacts. No tests, OpenMC calculations, builds or new AWS jobs were run.

## Preserved baseline

Job `e6de7f98-bd2a-4fa9-8d8f-67702572978c` completed 250 batches, wrote its
statepoint and comparison, uploaded outputs, and exited 2 because the screen failed.
Its result is **1.224959932 ± 0.000361644**, versus the published mean 1.236000:
Δk × 100,000 = **−1104.01**, reactivity difference = **−729.17 pcm**.
The statistical screen passed (36.16 versus 50); the bias screen failed (1104.01
versus 500). These are project screening limits, not OECD acceptance criteria.
OpenMC reported 2042.5 seconds elapsed; Batch start-to-stop was about 35 minutes.
This is a cold transport result, not a depletion result.

The adjacent `cold-baseline-e6de7f98.json` records the exact image digest,
job-definition revision, input/data hashes, result and archive file hashes.
All 15 S3 output objects were copied into the ignored local directory
`.local-artifacts/mhtgr-cold-e6de7f98/output/`, including the 164 MB geometry XML
and 5.2 MB statepoint. Job metadata, CloudWatch JSON/text and a local HEAD source
snapshot are also archived. The source snapshot is not an independently verified
image-to-commit mapping; original run XML and image digest are authoritative.

Original S3 prefix:
`s3://openmc-block-results-20261112214420463500000002/runs/e6de7f98-bd2a-4fa9-8d8f-67702572978c/attempt-1/`.
The bucket returned no enabled versioning and no lifecycle configuration. This
archive is preservation, not immutable storage. Back up the local archive before
deleting cloud resources. Raw artifacts are excluded from Git; commit the small
manifest and this review. Existing cloud objects were not modified.

## Confirmed defects and corrections

1. **Missing Cs-134.** Table III-4 specifies `9.75e-08 atom/b-cm` in the fixed
   burned mixture. Both the prior JSON and actual materials XML omitted it.
   Added that entry to `specification.json`. The current cross-section index
   includes `Cs134.h5`. Its effect on k has not been calculated; this finding
   does not establish the cause or direction of the full discrepancy.
2. **Wrong depletion flag.** The actual XML marks `burned` depletable, without
   a volume. OpenMC 0.15.3 automatically enables depletion when adding actinides.
   Explicitly default materials to non-depletable, then enable only central fuel
   pins. A construction-time guard now requires precisely those material IDs.
   This prevents an invalid depletion setup; it does not explain the cold k bias.
3. **Incomplete entropy domain.** The prior box covered only the fresh block,
   excluding fission in the surrounding burned material. It now encloses the
   full supercell, approximately x ±62.354 cm and y ±54 cm, plus numerical
   padding. Bounds are recorded in the geometry audit. This fixes a diagnostic;
   entropy values from the old and new meshes are not directly comparable.

Sources: [specification, Tables III-1–4 and Figures III-1/III-3](https://www.oecd-nea.org/upload/docs/application/pdf/2021-11/mhtgr-350-vol_iii-benchmark_lattice.r0.pdf),
[OpenMC 0.15.3 material implementation](https://github.com/openmc-dev/openmc/blob/v0.15.3/openmc/material.py).

## What was reviewed and what remains uncertain

Manual review found the remaining transcribed material densities consistent with
Tables III-3/III-4. Carbon splitting and thermal-scattering assignment follow the
specified distinction between natural and graphite carbon. Radii, pitch, widths,
packing target, no-poison replacements and temperatures agree with the stated
case. The region partition follows the upper-reflector/lower-burned diagram,
including its diagonal outer interfaces; reflective boundaries and 210 central
fuel positions are consistent with the exercise. This is a source/table review,
not independent certification of the constructed geometry.

The realized packing fraction is 0.3498082575 rather than exactly 0.35, with 1348
kernels per compact. A one-centimetre slice and repeated packing realization can
introduce spatial correlations and wall effects. Seed and slice-height sensitivity
remain open. Initial sources are in fresh fuel only; adequate equilibration into
the burned region has not been demonstrated by the incomplete baseline entropy
diagnostic. A small reported Monte Carlo uncertainty is not proof of convergence.

The comparator selects exercise 1a, zero burnup, and the correct Table 4 mean.
Its Δk and reactivity formulas are distinct and the numerical failure is genuine.
The reference code spread is not an experimental uncertainty.
[Corrected results report, Table 4](https://www.oecd-nea.org/upload/docs/application/pdf/2021-11/nea_nsc_r_2019_6_cancel_and_replace_16_oct_2020_2020-10-16_15-07-51_660.pdf).

For depletion, the intended normalization is 100 W/g of initial central heavy
metal, using central depletable fuel fission-Q normalization. The fixed burned
region must remain outside that inventory. The prior flag violated this intent.
The timestep conversion is 0.1 MWd/kgHM per day; solver, chain and timestep
sensitivity still need their own evaluation after the cold case is understood.

## Could graphite data explain it?

It is a plausible contributor, **not an established explanation**. The library
index selects `c_Graphite.h5`; it also lists `_10p` and `_30p` alternatives, but
the model does not select those. Do not switch tables simply to improve k.
The earlier header inspection found a 296 K lowest graphite table; the case
requests 293.6 K and permits a 3 K endpoint tolerance. Tolerance permits existing
data to be used; it does not generate a new 293.6 K scattering law.

The current library is labeled ENDF/B-VIII.0; the benchmark prefers VII.0.
A temperature-only comparison must hold the evaluation, processing and all other
nuclide data fixed while replacing the relevant graphite thermal table with
properly processed 293.6 K data. A whole-library VII.0 comparison changes more
than graphite and must be reported as such. Neither comparison has been performed.
Keep each library in a separate versioned S3/EFS directory, with a manifest and
matching cross-section index. Do not overwrite `endfb80-v1`/`enfdb80-v1`.

## Exact next steps

1. Review and commit the corrections, audit files and sequential workflow. No
   particle count, temperature tolerance, seeds, data paths or screening limits
   were changed. The edits have not been executed or tested, per your request.
2. Publish a new unused `v*` release using the existing process. The existing CI
   validation job will run when you push; no workflow was dispatched here.
3. In CloudShell, fetch tags, check out the new tag, and run
   `bash scripts/register-release.sh YOUR_NEW_TAG`. Save the new exact geometry,
   cold and pilot ARNs from that one registration. Never reuse an older image's
   definitions for these corrections.
4. For the first controlled follow-up, use **Publish or submit block depletion**,
   stage **mhtgr-cold**, with its new ARN. This isolates the corrected composition
   while keeping the baseline library/settings. It is one node, 16 threads.
   Geometry dimensions and packing are unchanged. Review the new entropy trace
   and verify that outside-entropy-box warnings have disappeared.
5. Compare both the new baseline-relative change and the published-reference
   difference. Do not predict the Cs-134 effect or claim the full gap is fixed
   before observing the result. If the mismatch remains, stop and prepare the
   separately versioned, matched-data comparison described above. Do not increase
   particles or widen limits as a substitute for resolving the mismatch.
6. Before accepting agreement, review inactive-generation behavior and plan an
   independent source/packing/slice sensitivity study. A numerical screen alone
   does not establish convergence or benchmark validation.

## Optional sequential workflow

After release registration, open **MHTGR sequential checks (no production)** in
GitHub Actions, select **main**, and enter the three exact ARNs from the same
release. Alternatively pin them in `infra/deployment.json`; no repo variables are
required. It performs **geometry → cold → pilot**, using the existing submit and
monitor workflow. All three ARN formats are resolved before the first submission.
Only a successful preceding workflow allows the next stage to submit. An AWS
failure, failed numerical screen or monitoring timeout stops progression.

This is an alternative to the standalone cold follow-up, not an instruction to
submit both. While diagnosing this mismatch, the standalone run is preferable:
it avoids repeating the geometry calculation and allows human review before pilot.
Use the sequence when you intend to authorize the pilot automatically if cold
passes. It does not include seed/mpi-check (already completed setup checks), and
it never submits `production` or `mhtgr-depletion`. Production remains a separate
manual dispatch: eight nodes × 16 threads. Pilot retains its existing two nodes.

Sequential success means existing automated checks passed, not scientific
validation. Review plots, convergence and benchmark limitations before production.
Cancelling GitHub monitoring does not terminate a running AWS job; inspect Batch
before any rerun. Avoid concurrent standalone submissions of the same campaign.
Use **Re-run failed jobs** to retry a failed stage; **Re-run all jobs** repeats
earlier successful stages and incurs their compute costs again.

## Summary export and honest reporting

`summary.h5` remains disabled as in the baseline. No evidence in this run establishes
an EFS fault. Restoring and profiling that export is a separate unresolved task;
this audit corrected the misleading source comment that treated EFS as proven.
The saved statepoint and XML are retained. Do not infer a summary-export diagnosis
from the successful transport or the failed numerical comparison.

Suggested result statement: “The initial OpenMC exercise 1a calculation completed
with k = 1.224960 ± 0.000362, 1104 Δk-pcm below the published mean. The project
screen failed. Review identified a missing burned-region isotope, an incorrect
depletion flag and an incomplete entropy diagnostic. Corrections are prepared;
their numerical effects and the contribution of library/temperature differences
have not yet been evaluated. Benchmark validation is not claimed.”
