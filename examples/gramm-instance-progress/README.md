# GRAMM instance progress on Windows

![The GRAMM panel with six instances, eight instances, and the list scrolled to show instance 8](windows-progress.png)

The screenshots show sample counts in the Windows GUI. In the **Done** column, `6/11` means that the worker has written final wind fields for 6 of its 11 assigned original situations. **Left** shows 5 for that row. Hover over a row to see its situation numbers. The file-size box also counts intermediate sunrise wind fields.

## Reproduce the sunrise scheduling check

Use .NET 10, the GUI source from the pull request and the [stock GRAMM source at 1cfd22d](https://github.com/GralDispersionModel/GRAMM/tree/1cfd22dfa3a26de39ee050af0e92324b9b1b96e7). Run the following in PowerShell from the directory containing this README, with the two paths set to your checkouts.

```powershell
$gui = (Resolve-Path 'C:/src/patched-GUI').Path
$gramm = (Resolve-Path 'C:/src/GRAMM').Path
$engineBin = Join-Path $env:TEMP 'gramm-scheduler-engine'
dotnet build (Join-Path $gramm 'src/GRAMM.csproj') -c Release -o $engineBin
dotnet run --project ./SchedulerChecks.csproj -c Release "-p:GuiSource=$gui" -- (Join-Path $engineBin 'GRAMM.dll')
```

The check calls the stock engine's `Meteopgtall.Integrationtime` method. For each of 7,200 small input plans it enumerates every possible contiguous partition and checks that the GUI attains the lowest maximum nominal integration time. It also checks 11 cases covering original IDs, equal weights, extra sunrise rows and the fallback for unsupported settings. The expected output is `{"status":"pass","engineCheckedPlans":7200,"targetedCases":11}`.

The [four-worker wall-clock test](../gramm-sunrise-timing-4-workers/README.md) includes the actual worker times, the assigned situation ranges, and a comparison of the resulting wind fields.
