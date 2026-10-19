# 03: Tail at scale

A distributed request is only as fast as its slowest part. When a front end calls `k`
backends in parallel and needs every answer, a rare slow backend turns into a common
slow request. This challenge measures that on a real server, then applies the fix from
Dean and Barroso's "The Tail at Scale": **hedged requests**.

## Run it

```bash
uv run tail-at-scale            # about a minute and a half
uv run tail-at-scale --quick    # about 30 seconds
```

## Setup

- A 64-worker `jiffy-service`, so nothing queues. This challenge is about variance, not
  load.
- Each backend call takes **2 ms 99% of the time and 50 ms 1% of the time**: a backend
  that is "slow at p99".
- Front-end requests arrive at 25 per second, open-loop. Each one fans out to `k` backend
  calls and waits for all of them.
- A request or call is **slow** if it takes more than 20 ms.

## A. Fan-out amplifies the tail

If one call is slow with probability `p`, a request with `k` calls is slow with
probability `1 - (1 - p)^k`. In this run, `p` (measured across every backend call) was
0.97%.

| fan-out k | slow: theory 1-(1-p)^k | slow: measured | p50     | p90     | p99     |
|-----------|------------------------|----------------|---------|---------|---------|
| 1         | 0.97%                  | 0.69%          | 2.92 ms | 3.43 ms | 4.90 ms |
| 5         | 4.8%                   | 7.7%           | 3.26 ms | 4.14 ms | 52.4 ms |
| 10        | 9.3%                   | 10.6%          | 3.64 ms | 51.3 ms | 51.8 ms |
| 20        | 17.7%                  | 15.3%          | 4.35 ms | 51.3 ms | 52.3 ms |
| 50        | 38.6%                  | 40.1%          | 7.83 ms | 52.9 ms | 56.1 ms |

At k=1 the p99 is a fast call. By k=10 the p90 is a slow call. By k=50 about 40% of
requests wait for a straggler, even though no single backend got any worse. Each extra
dependency lowers the percentile at which the slow path shows up.

## B. Hedging

If a call hasn't answered within 10 ms (several times its usual 2.5 ms), send the
same call again and take whichever answer arrives first.

| fan-out k | slow before | slow hedged | p99 before | p99 hedged | extra calls |
|-----------|-------------|-------------|------------|------------|-------------|
| 20        | 15.3%       | 0.33%       | 52.3 ms    | 14.6 ms    | 0.81%       |
| 50        | 40.1%       | 0.93%       | 56.1 ms    | 19.5 ms    | 2.3%        |

Slow requests drop from 15% to 0.3% at k=20 and from 40% to under 1% at k=50, for
1–2% more backend calls. Hedging works when slowness is a property of *where and when* a
call runs (a GC pause, a busy disk, a noisy neighbour), not of the call itself. Here the hedge draws fresh work, independent of the original. If
the request itself were expensive, a hedge would just be a second expensive request.

## The hedge that fired late

The first version of this challenge used `concurrent.futures.wait(timeout=0.010)` as the
hedge timer. It cut slow requests at k=20 from 16% to only 8.5%, half of what the model
predicted. Measuring the timer itself found the cause:

```
wait(timeout=10ms): median 21.01 ms
time.sleep(10ms):   median 10.39 ms
```

On Windows, lock and event timeouts are rounded up to the system clock tick, while
`time.sleep` uses a high-resolution timer. The hedges were going out 21 ms after the
original call, too late to beat a 50 ms straggler by much. `wait_until` in `run.py` now
waits in short sleeps. If a timeout matters to the result, measure the timeout.

## Things to try

- Change `HEDGE_AFTER` to 5 ms (more extra calls) or 30 ms (less benefit).
- Raise `SLOW_SHARE` to 0.05. At k=50 nearly every request is slow without hedging.
- Make the slow path depend on the request instead of the draw. Hedging stops helping.

## Where the code is

| What | Where |
|---|---|
| Fan-out, hedging, the tables | `tail_at_scale/run.py` |
| One connection, many calls in flight | `jiffy_service.client` |
| Open-loop front-end load | `jiffy_load.runner.open_loop` |
