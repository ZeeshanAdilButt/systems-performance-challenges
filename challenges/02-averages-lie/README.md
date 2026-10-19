# 02: Averages lie

Two ways the numbers you normally look at say "fine" while users wait.

## Run it

```bash
uv run averages-lie            # about 45 seconds
uv run averages-lie --quick    # about 20 seconds
```

## A. Microbursts

Two workloads drive a 4-worker service at the **same average rate**, 50% busy:

- **smooth**: Poisson arrivals;
- **bursty**: the same number of requests, all sent in the first 50 ms of every 200 ms.

The server's USE recorder watches both runs. Because it records every transition rather
than sampling, the same run can be shown through 1-second windows (what a typical
dashboard shows) and through 10 ms windows.

| workload                      | busy (1 s avg) | peak (1 s) | peak (10 ms) | 10 ms windows queueing | max queue | p50     | p99     |
|-------------------------------|----------------|------------|--------------|------------------------|-----------|---------|---------|
| smooth (Poisson)              | 48.5%          | 56.5%      | 99.9%        | 19.8%                  | 7         | 8.56 ms | 48.8 ms |
| bursty (50 ms on, 150 ms off) | 48.9%          | 55.1%      | 100.0%       | 47.4%                  | 36        | 28.5 ms | 91.4 ms |

Averaged over a second, the two workloads look the same: half busy, plenty of headroom.
At 10 ms resolution both hit 100% busy now and then, but the bursty one has work waiting
for a busy worker in nearly half of all 10 ms windows, with up to 36 requests queued at
once against 7. Users in a burst wait behind dozens of others. That shows up at p50
(3x worse), not just p99.

The fix isn't more capacity. On average there's plenty. Either smooth the arrivals
(jitter on timers and cron jobs, client-side pacing) or size for the burst rate rather
than the average.

## B. Coordinated omission

The service now freezes for **300 ms every 1.5 s**, the way a stop-the-world GC pause or a
descheduled VM would. Between freezes it runs at about 26% busy. The same service is
measured three ways:

| View | How it measures |
|---|---|
| server's own metric | `wait + service`, starting when the reader thread takes the request off the socket. The usual "request duration" histogram. |
| closed-loop tool | 2 users, each sends, waits for the answer, thinks, sends again. Aimed at the same ~100 req/s. |
| open-loop tool | requests go out on a fixed Poisson schedule. Latency counts from when each was **due**. |

| measured by                             | requests | mean    | p50     | p90     | p99     | p99.9  | max    | > 50 ms |
|-----------------------------------------|----------|---------|---------|---------|---------|--------|--------|---------|
| server's own metric (wait + service)    | 882      | 18.6 ms | 9.94 ms | 45.5 ms | 88.7 ms | 317 ms | 317 ms | 9.3%    |
| closed-loop tool (2 users)              | 700      | 15.7 ms | 8.23 ms | 27.1 ms | 311 ms  | 347 ms | 347 ms | 2.1%    |
| open-loop tool (from when each was due) | 882      | 40.7 ms | 10.8 ms | 175 ms  | 302 ms  | 320 ms | 320 ms | 17.9%   |

The service is frozen 20% of the time. The open-loop tool saw 17.9% of requests take over 50.0 ms; the closed-loop tool saw 2.1%, and the server's own metric 9.3%.

- **The closed-loop tool sends fewer requests during a freeze.** Each user is stuck
  waiting, so each freeze gives it one slow sample per user instead of the dozens of
  requests real users would have sent in that window. It also sends fewer requests
  overall. Its p90 looks healthy, and only the far tail hints that anything happened.
- **The server's own metric misses the start of every freeze.** Its reader thread is
  frozen too, so requests pile up in the socket buffer, where the server's clock isn't
  running. It does see the backlog drain once the freeze ends, so it catches some of the
  pain, but not all of it.
- **Only the open-loop view matches what users feel.** The service is frozen a fifth of
  the time, and the open-loop tool finds about a fifth of requests slow. The server's own
  metric finds half that, and the closed-loop tool about a ninth.

The lesson for real load tests: generate load on a schedule and measure from the
intended send time (wrk2, Gatling's open model, k6's arrival-rate executors). When
reading server-side latency histograms, remember they start the clock late.

## Things to try

- Change `BURST_ON` to 0.1 (shorter, sharper bursts) or 0.5. The 1-second numbers don't
  move.
- Make the stall shorter but more frequent: `Stall(every=0.2, length=0.04)`.
- Give the closed-loop tool more users (`CLOSED_USERS = 16`) and compare the slow share.

## Where the code is

| What | Where |
|---|---|
| Both experiments | `averages_lie/run.py` |
| Bursty and Poisson schedules | `jiffy_load.arrivals` |
| Open and closed loop | `jiffy_load.runner` |
| Stalls, and where the server starts its clock | `jiffy_service.server` |
| Windowed utilization and saturation | `jiffy_metrics.use` |
