# Four-worker sunrise timing and wind-field comparison

## Cases and worker ranges

- **Input.** Public AscendingBridge grid (26 × 23 × 20, 300 m). Each run has 48 original situations at 1.5 m/s and 23°. The first 20 are stability class 6 and the remaining 28 are class 4. The base modelling time is 1,300 s. The `10,1,15,` header selects prescribed directions and disables random sector jitter.
- **Work.** At these settings GRAMM assigns 3,900 model seconds to each class-6 case and 221 to each class-4 case, for 84,188 model seconds across both layouts. Each run writes 48 original wind/scalar pairs and 20 intermediate sunrise pairs.

| Worker | A · equal-count situations | A · model seconds | B · weighted situations | B · model seconds |
|---|---|---:|---|---:|
| 1 | 1–12 | 46,800 | 1–6 | 23,400 |
| 2 | 13–24 | 32,084 | 7–12 | 23,400 |
| 3 | 25–36 | 2,652 | 13–18 | 23,400 |
| 4 | 37–48 | 2,652 | 19–48 | 13,988 |

- **How the comparison works.** A deliberately uses four equal counts. B calls the GUI range planner. The original V2701 GUI used a different inclusive-offset rule; the times here compare the two listed policies. The harness launches the chosen GRAMM executable directly with those range arguments.
- **Host and timing.** Windows 11 x64, AMD Ryzen 9 9950X3D, four concurrent processes with `Max_Proc.txt = 1` each, CPU affinity unrestricted. Workers start in range order at a requested 300 ms interval. Each run gets clean copies of the same seven inputs. Timings include process start, radiation-geometry synchronization, solver work and output writes.
- **Repeat design.** One warm-up per layout, followed by four measured pairs in orders A/B, B/A, B/A and A/B. The launcher has a common 270 s deadline for all four workers, measured from before the first launch, and a bounded cleanup period. Output checks are outside the timed interval.
- **Definitions.** Process lifetime is the operating system’s recorded exit time minus creation time. The per-run *worker gap* is the longest minus shortest lifetime. *Finish spread* measures time from first exit to last exit. *Total time* runs from the first worker’s creation to the last worker’s exit. Each published median is taken over the four measured runs of that policy.

## Measured results

The table reports the **final corrected engine** at [`58fcb6f`](https://github.com/Borealis-Thoon/GRAMM/commit/58fcb6f4f480cf688882e71f453eee93a989b560). Each cell is the median of four runs. The gap is calculated within each run before taking the median.

| Wall-clock metric | Equal-count ranges | Weighted ranges | Change |
|---|---:|---:|---:|
| Longest minus shortest worker lifetime | 43.22 s | 4.98 s | 88.5% lower |
| Standard deviation of four worker lifetimes | 19.11 s | 1.78 s | 90.7% lower |
| First worker exit to last worker exit | 42.50 s | 5.89 s | 86.1% lower |
| First worker start to last worker exit | 55.51 s | 35.30 s | 36.4% lower |

- Both the runtime gap and total time decreased in all four matched pairs. The gaps ranged from **42.51–43.57 s** with equal counts and **4.06–5.36 s** with weighting. Total times ranged from **54.90–56.11 s** and **34.96–35.65 s**. The longest corrected run, including launcher overhead, took **56.13 s**.
- Median worker lifetimes in worker-number order were **55.51, 43.81, 12.45, 12.38 s** for equal counts and **29.41, 31.87, 32.23, 34.39 s** for weighting.
- **Field identity.** At one configured core per instance, all 68 wind files and their decompressed scalar members matched in every cross-layout and same-layout comparison (**1,088** field comparisons). One process running situations 1–48 produced identical values for all 68 fields when compared with all eight measured runs (**544** further comparisons).
- **Limits.** In a separate four-worker test at `Max_Proc=2`, seven of 68 wind files differed between layouts by a maximum of **0.01 m/s**. All decompressed scalar members matched. The correction can also change a cold-start value relative to the original engine: for original situation 1 the maximum wind-component difference was 0.01 m/s, with a one-unit difference in some UST and OBL cells. The exact-match result above applies to the tested one-core setup.
- **Corrected engine data.** [Trial times](fixed/trials.csv) · [Worker lifetimes](fixed/worker_times.csv) · [Input and binary hashes](fixed/manifest.json) · [Per-field comparisons](fixed/field_summary_by_id.csv) · [All pairwise comparisons](fixed/field_comparisons.csv) · [Single-process, standalone-case and two-core controls](fixed/additional-controls.json)
- **Stock engine data.** With stock [`1cfd22d`](https://github.com/GralDispersionModel/GRAMM/commit/1cfd22dfa3a26de39ee050af0e92324b9b1b96e7), the same layouts gave median gaps of 41.30 and 3.42 s, respectively, but the wind-field values differed as described below. [Trial times](stock/trials.csv) · [Worker lifetimes](stock/worker_times.csv) · [Input and binary hashes](stock/manifest.json) · [Per-field comparisons](stock/field_summary_by_id.csv)

- **Validation.** All four processes had to exit successfully. Each wind file had to contain the expected 20-byte header, grid dimensions and length. The harness checked the mapping of intermediate fields to their original situations and the names, uncompressed sizes and CRCs of the three members in each scalar archive.
- **Scope.** The test deliberately places the expensive cases together. Wall-clock results depend on case order, grid, host, solver time steps and retries.

## Why the stock wind fields changed

- In the stock four-worker test, original situations 7 and 19 reached a maximum difference of 1.15 m/s in an individual U, V or W component between layouts. Across the matched pairs, 44 of 48 original IDs and 11 of 20 intermediate IDs had at least one difference.
- In a serial diagnostic, situation 7 ran alone or after situation 6, using the same inputs and identical `albeq.dat`. Wind direction was fixed. With no overlapping processes, 24,170 of 35,880 wind components still differed, by up to 0.80 m/s.
- Resetting the previous situation’s vertical velocity `WN` left just 18 differing components, up to 0.01 m/s. Resetting the solver’s `StripeCounter` alone left the 0.80 m/s difference. Resetting both made this case’s wind components and all three decompressed scalar members identical. [Controlled interventions and source locations](situation-reset-evidence.json)
- After these two resets, the full four-worker comparison still had differences of at most 0.01 m/s between layouts and within repeats. [Reset-only control](reset-only-field-summary.json)
- A separate repeat test found two in-place stripe bodies active concurrently with `Max_Proc.txt = 1`. Restricting the cached sweeps to one lane while keeping their stripe widths removed the last-digit repeat differences in the diagnostic. Enforcing one lane can itself change the last stored digit relative to stock, including on a cold start. [Single-worker stripe test](single-worker-stripe-evidence.json)

## Reproduce the four-worker test on Windows

Use Python 3.11 or later and .NET 10. Set `$gui` to the [tested planner checkout](https://github.com/Borealis-Thoon/GUI/tree/29c534c1b39526aa47b33d1cfeab4a868acbac05) and `$gramm` to the engine checkout for the series you want to reproduce. The source commits and input hashes are listed with the results. Run the following in PowerShell from this directory.

```powershell
$gui = (Resolve-Path 'C:/src/GUI').Path
$gramm = (Resolve-Path 'C:/src/GRAMM').Path
$engineBin = Join-Path $env:TEMP 'gramm-four-worker-engine'
$plannerBin = Join-Path $env:TEMP 'gramm-four-worker-planner'
$output = Join-Path $env:TEMP ('gramm-four-worker-' + [guid]::NewGuid().ToString('N'))

dotnet build (Join-Path $gramm 'src/GRAMM.csproj') -c Release -o $engineBin
dotnet build ./planner/Planner.csproj -c Release "-p:PlannerSource=$gui/src/GRALMainFunctions/GrammInstanceRanges.cs" -o $plannerBin
py -3.12 ./benchmark.py --exe (Join-Path $engineBin 'GRAMM.exe') --fixture (Join-Path $gui 'SampleProjects/AscendingBridge/Computation') --planner (Join-Path $plannerBin 'Planner.dll') --out $output
py -3.12 ./summarize.py $output "$output-timing"
py -3.12 ./compare_wind.py $output "$output-fields"
```

The field comparator decodes all signed 16-bit U/V/W values in units of 0.01 m/s, then compares the scalar ZIP members after decompression. The published per-worker CSVs use times relative to the first launch; the local run also records the raw Windows timestamps.
