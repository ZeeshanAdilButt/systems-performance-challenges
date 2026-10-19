# The mental model, and where to see each piece

This repository is a runnable companion to chapter 1 of Brendan Gregg's *Systems
Performance* (2nd edition). The chapter defines the vocabulary every later chapter uses.
Here each term is tied to a number you can produce on your own machine, and to the line of
code that produces it.

## The vocabulary

Every request in the challenges goes through the same path. A client sends it over TCP,
a reader thread puts it on a queue, one of `N` workers takes it and works on it, and the
reply goes back.

```
client ──TCP──> reader ──> [ queue ] ──> worker 1..N ──> reply
          |          |               |                 |
       intended  received         started            done
```

| Term | Definition here | Where it is measured |
|---|---|---|
| **Latency** | `done - intended`: how long the caller waited, counted from when it *wanted* to send | `jiffy_load.Sample.latency` |
| **Response time** | `done - sent`: the same, but only from when the request actually left | `Sample.response_time` |
| **Wait time** | `started - received`: time in the queue, because every worker was busy | `jiffy_service` reply field `wait` |
| **Service time** | `done - started`: time a worker spent on it | reply field `service` |
| **Throughput** | completed requests per second | `jiffy_load.throughput` |
| **Utilization** | share of worker-time spent busy, per window | `jiffy_metrics.UseRecorder` |
| **Saturation** | work waiting *because* every worker is busy (queue length, time spent queueing) | `UseRecorder`: `max_queue`, `saturated_windows` |
| **Errors** | requests that failed | `UseRecorder.errors`, `Sample.error` |
| **Bottleneck** | the resource that limits throughput. Here it is the worker pool, on purpose | `WORKERS` in each challenge |

On the server, latency = wait + service. The client sees more than that: the network, the
reader thread, and any delay before the request was even sent. The gap between the two
views is what challenge 02 is about.

## The three goals, and the trade-off between them

Performance work tries to do three things: lower latency, raise throughput, and pay less
for both. They pull against each other because of queueing. To get more throughput out
of the same hardware you run it busier, and running busier costs latency, slowly at first
and then very fast.

**See it:** `uv run knee`. The first table is pure theory, the sweep is real:

- at 50% busy, 4 workers: mean latency ~1.1x the service time;
- at 90%: ~3x;
- at 95%: ~5.5x, and the p99 is over 20x.

The cheapest capacity is the headroom you don't use. The knee tells you how much
headroom to keep.

## Why it is hard

| Chapter 1 says | This repository shows it in |
|---|---|
| Latency grows non-linearly as utilization approaches 100% | 01, the sweep: p99 roughly quadruples between 70% and 96% busy |
| Averages hide bursts ("microbursts") | 02 part A: two workloads at the same 1-second utilization, one with 2x the p99 |
| Tools have blind spots | 02 part B: a closed-loop load tool reports a fraction of the slow requests an open-loop one sees |
| Tail latency matters more than the mean | 03: one backend slow at p99 makes 40% of fan-out-50 requests slow |
| Complexity hides in layers you did not write | the Windows timer finding below |
| "Good" is relative to a goal | every challenge states its threshold (20 ms, 50 ms) before it measures |

## Observability and experimentation

Gregg splits the tools into two families. This repository uses both, deliberately:

- **Observability** watches a running system without changing it. The `UseRecorder`
  inside the server is observability: it sees every transition and counts them. It is
  cheap enough to leave on in production.
- **Experimentation** changes the system or its load to see what happens. The load
  generators in `jiffy-load`, the injected stalls (`Stall`), and the hedging in 03 are
  experiments. Run them on a lab system, not on production.

A third tool sits between the two: the **model**. `jiffy-queueing` predicts what *should*
happen, so a measurement can be called surprising or unsurprising. Challenge 01 puts
theory, simulation and measurement in one table. Whenever they disagree, one of the three
is wrong, and finding out which one is the work.

## Two perspectives

- **Workload perspective**: what the callers experience. Latency percentiles, throughput,
  error rate. Columns labelled *real*, *p99*, *slow*.
- **Resource perspective**: what the worker pool experiences. Utilization, saturation,
  errors (the USE method). Columns labelled *busy*, *max queue*, *windows queueing*.

Each challenge prints both side by side. Each perspective alone gets something wrong.
In 02 part A, the resource view at one-second resolution says "half busy, fine" for both
workloads, while the workload view shows the bursty one at twice the p99.

## Measure, don't guess

Three times while this repository was being built, a reasonable assumption turned out to
be wrong. A measurement caught each one:

1. **`time.sleep(0.010)` takes about 10.4 ms** on the Windows machine these challenges were
   written on. The service "asked" for 10 ms of work runs longer than that, so planning
   load from the nominal 10 ms would aim at 95% busy and land past 100%. Every challenge
   therefore calibrates first (`jiffy_service.calibrate`) and plans from the measured
   number.
2. **`concurrent.futures.wait(timeout=0.010)` takes about 21 ms on Windows.** Lock and
   event timeouts are rounded up to the system clock tick, unlike `time.sleep`, which
   uses a high-resolution timer. The first version of 03 hedged "after 10 ms" and got
   barely half the benefit it should have, because the hedges actually went out after
   ~21 ms. The fix is a sleep-based wait (`tail_at_scale.run.wait_until`), and the
   server's stall timer uses the same trick.
3. **A request waiting a few microseconds for an idle worker to wake up is not
   saturation.** The first version of the USE recorder counted any non-empty queue. It
   reported 87% of 10 ms windows as "saturated" for a half-idle server. Saturation now
   means work waiting while *every* worker is busy.

None of these would show up in a design review. Each showed up in a table.

## Further reading

- Brendan Gregg, *Systems Performance: Enterprise and the Cloud*, 2nd ed., chapter 1
  (and chapter 2 for the USE method and queueing).
- Jeffrey Dean and Luiz André Barroso, "The Tail at Scale", CACM 2013. Challenge 03.
- Gil Tene, "How NOT to Measure Latency". Coordinated omission, challenge 02.
- Neil Gunther, *Guerrilla Capacity Planning*. Queueing for working engineers.
