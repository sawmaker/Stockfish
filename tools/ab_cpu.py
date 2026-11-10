#!/usr/bin/env python3
"""Interleaved A/B benchmark using per-process CPU time.

Wall-clock NPS on a shared VM is dominated by hypervisor steal (observed
spread >15% between identical runs), so the CPU time actually consumed by the
child process is a much better estimator.  Candidates alternate round-robin and
the minimum over all rounds is reported: the minimum is the sample least
contaminated by steal and migration noise.

    ./tools/ab_cpu.py ./stockfish ./stockfish_patched --reps 12
"""
import os, statistics, sys, argparse


def cpu_time(exe):
    """CPU seconds (user+sys) consumed by one `exe bench` run."""
    pid = os.fork()
    if pid == 0:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        os.execv(exe, [exe, "bench"])
        os._exit(127)
    _, status, ru = os.wait4(pid, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0, f"{exe} failed"
    return ru.ru_utime + ru.ru_stime


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exes", nargs="+")
    ap.add_argument("--reps", type=int, default=12)
    a = ap.parse_args()

    res = {e: [] for e in a.exes}
    for e in a.exes:            # warmup: page cache, THP, branch predictors
        cpu_time(e)
    for _ in range(a.reps):
        for e in a.exes:
            res[e].append(cpu_time(e))

    base_min = min(res[a.exes[0]])
    base_med = statistics.median(res[a.exes[0]])
    for e in a.exes:
        v = res[e]
        print(f"{e:26s} min={min(v):7.3f}s med={statistics.median(v):7.3f}s "
              f"rel_min={base_min / min(v):.4f} rel_med={base_med / statistics.median(v):.4f} "
              f"spread={100 * (max(v) - min(v)) / min(v):.1f}%")


if __name__ == "__main__":
    main()
