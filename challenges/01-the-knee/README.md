# 01: The knee

How busy can a service get before its users notice? Intuition says latency rises in
step with load: twice as busy, a bit slower. Queueing says otherwise. Latency barely
moves for a long time, then turns sharply upward as utilization approaches 100%. That
bend is *the knee*. Where it sits decides how much headroom you have to buy.

## Run it

```bash
uv run knee            # eight load levels, about a minute
uv run knee --quick    # three load levels, about fifteen seconds
```

## What it does

1. Starts `jiffy-service` with **4 workers** in its own process.
2. **Calibrates.** Each request asks for exponentially distributed work with a mean of
   10 ms. The server is asked how long that really takes on this machine (`time.sleep`
   overshoots), and every arrival rate is planned from the measured number. Planning from
   the nominal 10 ms would overload the server at the top of the sweep.
3. **Sweeps** from 10% to 95% busy with open-loop Poisson arrivals. The busiest points run
   longer, because near saturation the queue swings so much that a short run is mostly
   luck.
4. At every point, puts **three answers** side by side:

| Column | Where it comes from |
|---|---|
| busy (server) | the server's own USE recorder: busy worker-seconds over capacity |
| mean: theory | M/M/4 (Erlang C), from the arrival rate and the measured service time |
| sim | the *same* arrival times and the *same* measured service times, replayed through a perfect 4-worker queue (`jiffy_queueing.fcfs`) |
| real | what the client measured over TCP, from when each request was due |

## Results

On a Windows 11 laptop, Python 3.12:

Asked for 10.0 ms of work per request on average; the server took 10.4 ms. Arrival rates below are planned from the measured number.

| aimed | busy (server) | req/s | max queue | mean: theory | sim     | real    | p99: sim | real    |
|-------|---------------|-------|-----------|--------------|---------|---------|----------|---------|
| 10%   | 11.9%         | 43    | 2         | 11.2 ms      | 11.2 ms | 11.6 ms | 43.8 ms  | 44.2 ms |
| 30%   | 30.8%         | 114   | 3         | 11.1 ms      | 11.0 ms | 11.4 ms | 52.9 ms  | 52.9 ms |
| 50%   | 51.6%         | 199   | 7         | 11.6 ms      | 11.5 ms | 11.9 ms | 52.9 ms  | 53.4 ms |
| 70%   | 69.5%         | 266   | 10        | 14.6 ms      | 14.4 ms | 14.8 ms | 56.7 ms  | 57.3 ms |
| 80%   | 78.7%         | 307   | 19        | 17.8 ms      | 16.6 ms | 17.3 ms | 61.4 ms  | 62.6 ms |
| 85%   | 83.8%         | 328   | 28        | 21.8 ms      | 21.3 ms | 22.4 ms | 86.1 ms  | 88.7 ms |
| 90%   | 88.5%         | 340   | 46        | 30.0 ms      | 37.9 ms | 42.1 ms | 128 ms   | 136 ms  |
| 95%   | 96.8%         | 367   | 87        | 112 ms       | 84.7 ms | 96.6 ms | 209 ms   | 224 ms  |

p99 latency, real, by how busy the server was:

```
12% busy | ########## 44.2 ms
31% busy | ############ 52.9 ms
52% busy | ############ 53.4 ms
69% busy | ############# 57.3 ms
79% busy | ############## 62.6 ms
84% busy | #################### 88.7 ms
89% busy | ############################## 136.1 ms
97% busy | ################################################## 223.8 ms
```

From 12% to 97% busy, the server did 8.6x the work, and p99 latency went from 44.2 ms to 224 ms (5.1x).

## Reading the table

- **The shape holds.** At low load latency is just the service time. Exponential work
  has a long tail of its own, so p99 sits around 4–5x the mean even with no queue at all.
  Past ~75% busy, queueing takes over and p99 climbs much faster than load.
- **Simulation and reality agree** to within a millisecond or two at moderate load. That
  says the server behaves like a textbook queue. What's left over is its own overhead:
  a single reader thread, the interpreter lock, the loopback network. The gap widens
  near saturation, where every bit of overhead gets amplified by the queue.
- **Theory and simulation disagree more than you'd expect at 90%+.** That isn't a bug.
  Near the knee, the realized arrivals in an 8-second run can be noticeably calmer or
  burstier than the long-run average. Theory describes the average over infinitely long
  runs. The simulation describes *this* run. The lesson for production: one short load
  test near saturation tells you little. Run it longer, or run it several times.
- **More workers move the knee right.** In the theory table, one worker at 90% busy waits
  10x the service time, while four workers sharing one queue wait 3x. That's why one queue
  feeding several workers beats one queue per worker.

## Things to try

- `--duration 15` for steadier numbers near saturation.
- Change `WORKERS` in `knee/run.py` to 1 or 16 and watch the knee move.
- Swap exponential work for a constant 10 ms (`work = [MEAN_WORK] * len(schedule)`). Less
  variance in service time means less queueing at the same utilization: the M/D/c case.

## Where the code is

| What | Where |
|---|---|
| The sweep, tables and chart | `knee/run.py` |
| Calibration, driving a run | `jiffy_service.experiment` |
| Erlang C, M/M/c | `jiffy_queueing.theory` |
| The perfect-queue replay | `jiffy_queueing.simulate.fcfs` |
| Utilization from exact transitions | `jiffy_metrics.use` |
