# GRAMM resume UI review images

These images were rendered from the actual WinForms controls by `tests/GrammResumeGui` at GUI commit `60dafd9981f1f0bc4d000cbec11d963362b2d6da`, the source revision of [GUI PR #98](https://github.com/GralDispersionModel/GUI/pull/98). The UI suite passed 12 tests and 835 assertions.

Counts, progress percentages and CPU labels are controlled test fixtures. The images demonstrate layout and displayed information; they are not captures of a live production calculation or performance measurements. The fixture values differ between scenarios. Window borders reflect the rendering environment.

| Image | What to inspect |
| --- | --- |
| `dashboard_balanced_79.png` | Eight instances share 79 pending situations as seven assignments of 10 and one of 9. Separated ranges stay in one assignment. |
| `dashboard_10_420.png` | A 420-pixel client area shows one column with vertical scrolling. |
| `dashboard_64_900.png` | A 900-pixel client area shows two columns and scrolling for a 64-instance layout fixture. |
| `main_gramm_summary.png` | The existing GRAMM group displays the aggregate total and an Instance progress button. |
| `main_cpu_settings.png` | The CPU button fits below the existing NUMA selector. |
| `cpu_placement_dialog.png` | The CPU policy dialog explains Windows preferences and the optional larger-L3 choice. |

`manifest.json` records image dimensions, hashes and the tested GUI assembly hash. This evidence branch hosts images for the PR description; it is not the code branch proposed for merging.
