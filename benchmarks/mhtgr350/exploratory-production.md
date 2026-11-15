# One exploratory depletion campaign with advisory comparison

## Current 32-vCPU configuration

The 128-vCPU quota was applied in us-east-1; the deployment stays in us-east-2,
where the applied quota is 32. The old queued job
`d7a3e36b-e3e5-4283-a6d1-a8f2d7e886f6` was cancelled before it started.
Production revision `block-mhtgr-depletion:9` uses the existing v0.1.11 image,
eight MPI nodes, four vCPUs/four OpenMP threads per node, and 28672 MiB per node.
Nodes are pinned to `r7i.xlarge` (4 vCPUs, 32 GiB) to preserve memory. This is one
multi-node job, not eight independent depletion calculations.

Revision 9 is historical: it still uses 50,000 particles and a 24-hour timeout:

```text
arn:aws:batch:us-east-2:591859078128:job-definition/block-mhtgr-depletion:9
```

**Do not submit revision 9 for the current requested run.** Production is now
configured locally for **25,000 particles per batch and a 48-hour timeout**.
Publish a new image and register it using the instructions below; paste the new
ARN into a new manual dispatch. The old deployment pin has been cleared to avoid
silently submitting revision 9. Commit the registration-script and
configuration changes to preserve this setup for future releases. Registering
from the older v0.1.11 script would recreate the old 16-vCPU-per-node configuration.
The compute environment update is recorded in `infra/compute-32vcpu-update.json`;
it allows both the existing single-node instance type and the new production type,
with a requested maximum of 32 vCPUs. Verify the environment is VALID with max 32
before dispatch. No replacement job was automatically submitted.

The user selected one full exploratory run instead of further controlled data
comparisons. The two cold runs completed but failed agreement screens. Their
results remain evidence of an unresolved discrepancy; changing workflow policy
does not change or validate those results.

## What success means now

The cold, pilot and depletion case JSON files explicitly set
`"benchmark_policy": "advisory"`. Geometry is unchanged. The comparator still
evaluates every requested reference burnup, using the original thresholds.

| Outcome | Workflow result | Report |
|---|---|---|
| Calculation, comparison and upload complete; screen passes | Success | `screening_pass`, `not_validated` |
| Calculation, comparison and upload complete; screen fails | Success | `screening_fail`, `not_validated`, advisory warning |
| Calculation fails or history is incomplete | Failure | No completed result claimed |
| Inputs/results missing, invalid or inconsistent; report fails | Failure | Error remains fatal |
| S3 upload fails | Failure | Output preservation not confirmed |

The JSON also records `calculation_status`, `comparison_status` and
`benchmark_policy`. A green GitHub run is operational completion. Agreement with
a numerical reference is not experimental validation; even a screen pass keeps
`validation_status: not_validated`. Published values, acceptance thresholds and
computed results have not been altered. Setting policy to `strict` restores the
old numerical gate; absent policy also defaults to strict.

## Run only production

1. Commit these changes and publish a new unused `v*` tag using the existing
   release workflow. Wait for image publication to finish. Existing definitions
   still reference old images and retain their old behavior.
2. In administrator CloudShell:

   ```bash
   cd ~/HALEU-PebbleBed-OpenMC
   git fetch origin --tags
   RELEASE_TAG=YOUR_NEW_TAG
   git checkout --detach "$RELEASE_TAG"
   bash scripts/register-release.sh "$RELEASE_TAG" > "$HOME/mhtgr-advisory-definitions.json"
   ```

   After registration succeeds, copy the production ARN:

   ```bash
   jq -r '.["mhtgr-depletion"]' ~/mhtgr-advisory-definitions.json
   ```

3. GitHub Actions → **Publish or submit block depletion** → **Run workflow**.
   Select branch **main**, stage **mhtgr-depletion**, and paste that exact ARN
   into `job_definition_arn`. Dispatch once. Do not choose the old `production`
   stage, which runs the original illustrative model.
4. Do not also start the sequential workflow if your intention is just one run.
   It would repeat geometry/cold/pilot. Under advisory policy that sequence now
   advances after operational success even when the numerical screen fails.
5. At completion, use the output prefix in the submit summary. Download
   `comparison.html` with `benchmark-comparison.png`, or read `comparison.md`.
   Preserve `comparison.json`, `comparison.csv`, `run.json`,
   `depletion_results.h5`, and `pin-inventories.csv` with the image digest.

Production remains manual. Nothing in publication or registration submits it.
No IAM changes, new nuclear-data upload or GitHub repository variables are needed
for this policy change.

## Cost and limitations

The current production definition requests **eight nodes × 4 threads**, one
MPI rank per node. It has a 48-hour attempt timeout, one attempt, and no implemented
restart. The schedule remains 125 depletion intervals, about 251 transport solves,
at 25,000 particles and 250 batches per solve (100 inactive). Comparison runs at the end, not
after every step. A timeout before completion can therefore prevent the final
comparison report; the advisory policy does not prevent computational failures.

Skipping diagnostics avoids their costs but does not establish that production
will finish within its timeout or cost less overall. The single-node cold runtime
cannot reliably predict eight-node hot depletion performance. Reducing total CPUs
from 128 to 32 increases runtime risk; halving particles reduces transport work
but does not guarantee completion within 48 hours or a lower total bill. Statistical
uncertainty may increase. Timesteps, temperatures, data and screening limits remain
unchanged. GitHub monitoring now has twelve five-hour windows (up to 60 hours),
allowing some queue/startup time in addition to the Batch runtime allowance.
Monitor AWS Batch during the run; cancelling GitHub monitoring alone does not
terminate the Batch job. Check for an existing active job before any resubmission.

Treat the outcome as an exploratory ENDF/B-VIII.0 calculation compared with
published numerical benchmarks. Do not label it “validated” simply because GitHub
is green. Source/packing/timestep convergence, the cold discrepancy and the
library differences remain unresolved. Only k is automatically compared with
reference values; exported isotope inventories are not validated by this screen.

These policy edits were reviewed by inspection only. No tests, builds or
simulations were run by the assistant; CI checks still run on publication.
