# Stockfish build & performance tuning — results

Branch: `arena/de33fb67-stockfish`, based on `43e01e0`.

**Headline result: the engine in this tree was never being built with the
instruction set the host actually has.** All tuning work up to this point was
done on `ARCH=x86-64-avx2`, while the host is an Intel Xeon with AVX-512BW/DQ/VL,
IFMA, VBMI, VBMI2, VPOPCNTDQ and VNNI. Rebuilding for the native target and
adding profile-guided optimization gives a **1.33× speedup**, verified three
independent ways.

## Final numbers

`bench 8 1 14` (5,167,777 nodes), 1 thread, child user CPU, 12 interleaved reps:

| Build                        | mean CPU time | sd     | ratio vs AVX2 |
|------------------------------|---------------|--------|---------------|
| `ARCH=x86-64-avx2` (before)  | 7.7426 s      | 0.0589 | 1.000         |
| `ARCH=native` (avx512icl)    | 6.1135 s      | 0.0855 | **1.2665**    |
| `ARCH=native` + PGO          | 5.8332 s      | 0.0435 | **1.3273**    |

Cross-check with the engine's own reported NPS on the default `bench`
(3,464,885 nodes), which is an independent metric:

| Build                    | Nodes/second |
|--------------------------|--------------|
| `ARCH=x86-64-avx2`       | 651,171      |
| `ARCH=native`            | 842,627      |
| `ARCH=native` + PGO      | 900,203 – 904,905 |

Both metrics agree on magnitude, and the ordering is stable across three
separate interleaved runs of the CPU-time harness.

Correctness is unchanged: every build reports `Nodes searched : 3464885`.

## How to reproduce

```bash
cd src
make -j2 profile-build ARCH=native COMP=gcc     # final: AVX-512 + PGO
make -j2 build       ARCH=native COMP=gcc     # AVX-512 only
make -j2 build ARCH=x86-64-avx2 COMP=gcc      # previous baseline
```

`ARCH=native` resolves to `x86-64-avx512icl` on this host
(`scripts/get_native_properties.sh`). Both builds need
`src/nn-18cd32e11a9c.nnue` present — the net cannot be downloaded from inside
this sandbox.

## Two measurement traps that produced false results

Both of these cost real time and produced numbers that were completely bogus.
Anyone re-running this work should read them first.

1. **`make build` does not invalidate objects when `ARCH` changes.** Switching
   from `ARCH=x86-64-avx2` to `ARCH=native` on a warm tree reported `EXIT 0`
   but left a **binary with zero AVX-512 instructions** in it. A first
   "AVX-512" measurement of +1.4 % was therefore measuring the AVX2 binary
   against itself. Always `make objclean` between architecture changes, and
   verify with `objdump -d --no-show-raw-insn stockfish | grep -c %zmm`.
   (`profile-build` happens to be safe because it runs `objclean` internally.)
2. **A missing net makes a failed build look like a successful one.** If the
   net is absent, the build fails at the `net` target, but a stale `stockfish`
   from an earlier build is still on disk, so `cp stockfish ...` and subsequent
   benchmarking silently use the *old* binary. Check the build exit status and,
   ideally, `cmp` the new binary against the previous one before trusting a
   measurement.

Mitigation used here: every A/B was run with interleaved repetitions and a
child-user-CPU harness (`/home/user/play/reps.py`), never wall-clock NPS from a
single run.

## What did *not* work (all reverted; source is clean)

Before discovering the build-configuration issue, the session exhaustively
attacked the NNUE accumulator, which profiling showed to be the dominant cost
(`Network::evaluate` 22.8 %, `apply_combined<2,1>` 18.8 %, `refresh_cache`
6.2 %). None of it helped, and the reason now looks clear: the AVX2 build was
already at a memory-bandwidth floor, so shaving instructions off its inner
loops changed nothing.

| Experiment | Ratio | Verdict |
|---|---|---|
| Feature prefetch, v2 | 0.997 / 0.977 | wash or loss |
| Hoist all update-row prefetches | 0.978 | loss |
| Hoist psq-only prefetches | 0.994 | wash |
| Fused both-perspective tile loop | 0.948 | loss |
| AVX-512-style multi-chain accumulators | 0.991 | wash |
| fc_0 split into 2 dependency chains | 0.977 | loss |
| fc_0 per-iteration next-column prefetch | 0.968 | loss |
| fc_0 bulk column prefetch (4 lines) | 1.005 | noise; rejected |
| fc_0 head-line prefetch (2 lines) | 0.878 | loss |
| `alignas(64)` on `MovePicker::moves` | 1.00008 | exactly neutral |
| Huge pages via `glibc.malloc.hugetlb=1` | 1.002 | wash |

Supporting micro-benchmarks (`/home/user/micro/`) showed the fc_0 inner loop is
latency-bound in isolation (294 → 119 cycles/column with prefetching) but that
none of that latency is exposed in the real engine — the out-of-order window and
the hardware prefetcher already hide it. **Micro-benchmark wins did not transfer
even once.** Treat them as hypothesis-generating only.

Profiling also showed instruction-level attribution is flat: no single site
accounts for more than ~2 % of samples outside `Network::evaluate`, and
`MovePicker::next_move` (4.9 %) is dominated by a single store-forwarded sort
write at `0x423dfc` (50.6 % of that function's samples) — not worth chasing.

## State of the tree

- Source files: **clean**, identical to `43e01e0`. No experimental patch is
  committed; the entire gain comes from build flags.
- `src/stockfish`: AVX-512 + PGO build (4,542 `%zmm` instructions).
- Reference binaries kept in `/home/user/`: `sf-base-nopgo` (AVX2),
  `sf-avx512-clean`, `sf-avx512-pgo`.

## Recommendation

Adopt `make profile-build ARCH=native` as the local build recipe. This is a
deployment/configuration change, not a source change, so it needs no patch to
upstream — but any future performance work on this machine should be redone on
top of the AVX-512 build, because the bottleneck profile of the AVX2 build was
not representative.
