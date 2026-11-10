# Benchmark helpers

Tools used while evaluating speed patches.  They are not part of the engine.

* `ab_cpu.py` — interleaved A/B of two or more engine binaries, comparing the
  **CPU time** each `stockfish bench` run consumes.  Wall-clock NPS on a shared
  VM drifts by >15% between identical runs, which is larger than any patch we
  can expect to measure; CPU time per bench is far more stable.  Every binary
  must produce `Nodes searched : 3464885`, which the script asserts, so a
  speed result can never come from a changed search.

      ./tools/ab_cpu.py ../sf_base ../sf_patch --reps 12

Note (2026-11): on the 2-vCPU sandbox used for this work even CPU time is too
noisy to resolve a 1% change (measured spread ~10-24%).  Results below ~3%
should be treated as unresolved rather than as a win.

## Measured roofline

`bench` performs 688,876 feature-transformer calls (2,019,652 evaluations, two
perspectives each).  Each call reads ~23.6 threat/pawn-pair rows plus ~6.5 psq
rows of 2 KiB, i.e. ~24 KiB of *randomly addressed* weight-table bytes per
call, from a 129 MiB table (62.9 MiB threat+pp, 66.0 MiB psq).

Measured random-row streaming rate on the sandbox (AVX2, 30 rows per pass,
32 B chunks, tile-major — the exact access pattern of `apply_combined`):

| table working set | rate        | cycles / 32 B chunk |
|-------------------|-------------|---------------------|
| 64 MiB            | 12.9 GB/s   | 6.5                 |
| 128 MiB           | 11.1 GB/s   | 7.5                 |
| 256 MiB           | 10.9 GB/s   | 7.7                 |

Instrumented `rdtsc` breakdown of the reference build (`rdtsc` itself adds
~70 cycles/eval, so absolute numbers are inflated; ratios are what matter):

* `Network::evaluate` = 100%
  * feature transformer (`transform`) = 73%
    * accumulator stack update = 87% of that (**64% of evaluate**)
      * forward-incremental (both perspectives) 1.68 M calls, 1.7 kcyc
      * refresh + backward-incremental 0.30 M calls, 2.0 kcyc
      * hybrid 0.06 M calls, 1.7 kcyc
    * feature transform proper (clip/product/nnz) = 13%
  * first affine layer (`propagate`, 160 nonzero rows/eval) = 27%

Conclusion: the accumulator is memory-bound at this machine's random-row
roofline.  Arithmetic-side rewrites of `apply_combined` therefore cannot pay
off — only reading fewer bytes per feature update can.
