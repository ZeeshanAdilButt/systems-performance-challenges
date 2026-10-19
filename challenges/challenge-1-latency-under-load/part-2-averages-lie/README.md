# Lab 02 · Averages lie

**Question:** can your graphs say "everything's fine" while people are waiting?

**Answer:** yes, in two ways this lab shows:

- **A. Bursts hide inside averages.** Two traffic patterns look identical on a one-second
  graph (both "50% busy"), but one makes people wait 3x longer.
- **B. Some measuring tools miss slow requests.** The server freezes 20% of the time. One
  common kind of load tool reports only 2% of requests as slow. The truth is 18%.

Read [Lab 01](../01-the-knee) first if words like *busy %*, *queue* or *p99* are new.

## Run it

```bash
uv run labs/02-averages-lie/averages_lie.py            # about 45 seconds
uv run labs/02-averages-lie/averages_lie.py --quick    # about 20 seconds
```

## Part A · Bursts hide inside averages

### The idea, from zero

Same coffee shop, 4 baristas. Two days with the **same number of customers**:

- **Smooth day:** customers trickle in at random all day.
- **Bursty day:** the same customers, but they arrive in groups. A bus pulls up, 20
  people walk in at once, then it's empty for a while.

Count customers per hour and the two days look the same: "half busy". But on the bursty
day everyone off the bus waits in a long line, and the baristas sit idle between buses.
An average over a long window can't see the line. Only a short window can.

### What the lab does

| Step | What happens | Code |
|---|---|---|
| 1 | Start the server with 4 workers and measure the real work time | [`spawn` + `calibrate`](averages_lie.py#L132) |
| 2 | Pick a rate that makes the server 50% busy on average | [`rate = BUSY × …`](averages_lie.py#L43) |
| 3 | **Smooth:** requests at random times | [`poisson(...)`](averages_lie.py#L46) → [`poisson()`](../../toolkit/jiffy-load/src/jiffy_load/arrivals.py#L13) |
| 4 | **Bursty:** the same number of requests, all squeezed into the first 50 ms of every 200 ms | [`bursty(...)`](averages_lie.py#L49) → [`bursty()`](../../toolkit/jiffy-load/src/jiffy_load/arrivals.py#L34) |
| 5 | Run each one, and ask the server for its numbers through **1-second windows** and through **10 ms windows** | [`widths=(1.0, 0.01)`](averages_lie.py#L60), [`second, tick`](averages_lie.py#L61) |

The server can show any window size from the same run because it writes down every
moment a request queues, starts and finishes, rather than checking once a second
([how](../../toolkit/jiffy-metrics/src/jiffy_metrics/use.py#L133)).

### Results

| workload | busy (1 s avg) | peak (1 s) | peak (10 ms) | 10 ms windows queueing | max queue | p50 | p99 |
|---|---|---|---|---|---|---|---|
| smooth | 48.0% | 56.5% | 100.0% | 18.8% | 7 | 8.65 ms | 48.3 ms |
| bursty | 48.6% | 55.3% | 100.0% | 48.2% | 36 | 29.4 ms | 98.0 ms |

| Column | In plain words | Code |
|---|---|---|
| busy (1 s avg) | how busy the workers were, averaged over each second: the usual dashboard graph | [`second["utilization"]`](averages_lie.py#L66) |
| peak (1 s) | the busiest single second | same, the max window |
| peak (10 ms) | the busiest 10 ms slice | [`tick["peak_utilization"]`](averages_lie.py#L68) |
| 10 ms windows queueing | how many 10 ms slices had requests waiting while every worker was busy | [`tick["saturated_windows"]`](averages_lie.py#L69) → [rule](../../toolkit/jiffy-metrics/src/jiffy_metrics/use.py#L133) |
| max queue | the longest the line got | [`use.py`](../../toolkit/jiffy-metrics/src/jiffy_metrics/use.py#L148) |
| p50 / p99 | typical wait, and the 1-in-100 unluckiest wait, measured by the client | [`lat.percentile(99)`](averages_lie.py#L72) |

### What it means

- On the one-second graph the two days are the same: 48% busy, peak 56%. "Plenty of
  room."
- In 10 ms slices, the bursty day has a line in **half** of them, with up to 36 requests
  waiting at once (against 7).
- People feel it: the typical wait is **3x** longer (29 vs 9 ms), and p99 is 2x worse.
- **Fix:** don't buy more servers (on average you have plenty). Spread the traffic out
  (add random delays to timers and cron jobs, have clients pace themselves), or size for
  the burst instead of the average.

## Part B · Tools that miss slow requests

### The idea, from zero

Now the server **freezes for 300 ms every 1.5 seconds**. Real servers do this: garbage
collection pauses, a slow disk, a virtual machine being paused. While frozen, it answers
nobody.

There are two ways to build a load tool:

- **"Wait for the answer, then send the next one"** (closed loop). Simple and very common.
  But when the server freezes, the tool freezes with it. It stops sending, so it records
  one slow request per freeze instead of the dozens that real users would have sent.
- **"Send on a fixed schedule, no matter what"** (open loop). Real users don't wait for
  each other. Every request that was *due* during the freeze gets counted, and its wait
  is timed from when it was due.

A third view is the server's own timer, the "request duration" graph most services have.
It starts timing only when it reads the request, and it can't read anything while it's
frozen.

### What the lab does

| Step | What happens | Code |
|---|---|---|
| 1 | Start a server that freezes 300 ms every 1.5 s | [`STALL`](averages_lie.py#L36), [`spawn(WORKERS, STALL)`](averages_lie.py#L93) → [freeze code](../../toolkit/jiffy-service/src/jiffy_service/server.py#L175) |
| 2 | **Open loop:** ~100 requests/s on a fixed random schedule | [`drive_open`](averages_lie.py#L97) → [`open_loop()`](../../toolkit/jiffy-load/src/jiffy_load/runner.py#L69) |
| 3 | **Closed loop:** 2 users, each sends, waits for the answer, pauses, sends again. Set to aim at the same ~100/s | [`think = …`](averages_lie.py#L100), [`drive_closed`](averages_lie.py#L102) → [`closed_loop()`](../../toolkit/jiffy-load/src/jiffy_load/runner.py#L111) |
| 4 | Put three views side by side | [the three rows](averages_lie.py#L110) |

### Results

| measured by | requests | mean | p50 | p90 | p99 | max | slow (> 50 ms) |
|---|---|---|---|---|---|---|---|
| server's own timer | 882 | 19.2 ms | 10.1 ms | 48.8 ms | 94.2 ms | 318 ms | 9.4% |
| closed-loop tool (2 users) | 696 | 15.9 ms | 8.39 ms | 27.7 ms | 311 ms | 342 ms | 2.2% |
| open-loop tool | 882 | 40.4 ms | 11.0 ms | 173 ms | 302 ms | 319 ms | **17.7%** |

| Row | Where its numbers come from | Code |
|---|---|---|
| server's own timer | the server's `wait + service` for each request, starting when it read the request | [`server_time()`](../../toolkit/jiffy-service/src/jiffy_service/experiment.py#L48), [clock starts here](../../toolkit/jiffy-service/src/jiffy_service/server.py#L132) |
| closed-loop tool | timed from when each request was actually sent | [`closed_loop()`](../../toolkit/jiffy-load/src/jiffy_load/runner.py#L129) |
| open-loop tool | timed from when each request was **due** | [`latency`](../../toolkit/jiffy-load/src/jiffy_load/runner.py#L46), [`intended`](../../toolkit/jiffy-load/src/jiffy_load/runner.py#L91) |
| slow (> 50 ms) | share of requests that waited over 50 ms | [`fraction_above`](averages_lie.py#L88) |

### What it means

- The server is frozen **20%** of the time. The open-loop tool finds **18%** of requests
  slow. That matches.
- The closed-loop tool finds **2%**. It also sent fewer requests (696 against 882),
  because it stopped sending during every freeze. Its p90 of 28 ms says "healthy".
- The server's own timer finds **9%**. It misses the start of every freeze (it can't read
  requests while frozen), and only sees the backlog afterwards.
- **Lesson for real load tests:** use a tool that sends on a schedule and measures from
  the intended send time (wrk2, k6 with arrival-rate executors, Gatling's open model).
  Remember that a server's own latency graph starts its clock late.

## Try this

- Make bursts shorter and sharper: [`BURST_ON`](averages_lie.py#L35) = 0.1. The
  one-second numbers won't move.
- Short, frequent freezes: [`STALL`](averages_lie.py#L36) = `Stall(every=0.2, length=0.04)`.
- More closed-loop users: [`CLOSED_USERS`](averages_lie.py#L39) = 16. Does it get closer
  to the truth?

## Files

| File | What's in it |
|---|---|
| [averages_lie.py](averages_lie.py) | the whole lab: part A is `microbursts`, part B is `omission` |
| [results.md](results.md) | the last full run |
| [test_averages_lie.py](test_averages_lie.py) | checks that bursts hurt the tail at the same average |
