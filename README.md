# Systems performance challenges

[![verify](https://github.com/ZeeshanAdilButt/systems-performance-challenges/actions/workflows/verify.yml/badge.svg)](https://github.com/ZeeshanAdilButt/systems-performance-challenges/actions/workflows/verify.yml)

Deep, runnable challenges on one question: **why do systems get slow, and how do you
measure it without fooling yourself?** Every challenge runs on your laptop against a real
server, explains its idea from zero, and links every number it prints back to the line of
code that made it.

This is a growing series. Later challenges will come at performance from other angles
(CPU, memory, disk, network, the runtime) and build their own tools along the way.

## Challenges

| Challenge | What you learn |
|---|---|
| [Challenge 1 · Latency under load](challenges/challenge-1-latency-under-load) | Why waiting explodes past ~75% busy, how averages and load tools hide slow requests, why one slow server in 100 makes 40% of pages slow, and how hedging fixes it without backfiring. Four parts: the knee, averages lie, tail at scale, adaptive hedging. |

![p99 and average latency against busy %](challenges/challenge-1-latency-under-load/part-1-the-knee/chart.svg)

Start with the [challenge 1 README](challenges/challenge-1-latency-under-load): it has a
101 of every word the parts use (server, request, worker, queue, latency, p50/p99).

## Layout

```
challenges/
  challenge-1-latency-under-load/
    README.md               start here: the 101 and all four parts with their charts
    part-1-the-knee/        README, script, results.md, chart, test
    part-2-averages-lie/
    part-3-tail-at-scale/
    part-4-adaptive-hedging/
toolkit/                    shared tools every challenge reuses
tools/                      verify.py (all checks) and charts.py (draws the charts)
```

## Run it

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/). From this folder:

```bash
uv sync
uv run challenges/challenge-1-latency-under-load/part-1-the-knee/knee.py
```

Add `--quick` for a shorter run. Each part prints its tables and saves them to
`results.md` in its folder.

## Watch it live

If you'd rather watch charts than read tables, start the dashboard:

```bash
uv run jiffy-ui
```

It opens a page in your browser. Pick a part, press **Run**, and four charts fill in while
it measures:

- **Latency**: p50 (the typical wait) and p99 (only 1 in 100 waited longer), one point
  per half second.
- **Server busy %**: how much of the time the workers were working, measured by the
  server itself ten times a second. A gap in this line means the server was frozen and
  couldn't report (part 2 freezes it on purpose).
- **Queue**: how many requests were waiting in line.
- **Slow requests**: the share that took longer than the part's "slow" line.

How the numbers get from a running part to the page:

1. The dashboard starts the part exactly as you would in a terminal, plus one setting,
   `JIFFY_LIVE`: where to send its numbers
   ([runner.py](toolkit/jiffy-ui/src/jiffy_ui/runner.py#L66)).
2. The load generator hands every finished request to the live feed
   ([experiment.py](toolkit/jiffy-service/src/jiffy_service/experiment.py#L64)). The feed
   collects them and sends a batch ten times a second
   ([live.py](toolkit/jiffy-metrics/src/jiffy_metrics/live.py#L69-L89)).
3. The server reports busy % and queue length for the last 100 ms, ten times a second
   ([server.py](toolkit/jiffy-service/src/jiffy_service/server.py#L180-L195)), using the
   same counter the tables use
   ([use.py](toolkit/jiffy-metrics/src/jiffy_metrics/use.py#L117)).
4. Every half second the dashboard turns the batches into p50 and p99 with the same
   percentile code the tables use
   ([board.py](toolkit/jiffy-ui/src/jiffy_ui/board.py#L64-L77)), and pushes them to the
   page over one HTTP response that stays open
   ([app.py](toolkit/jiffy-ui/src/jiffy_ui/app.py#L127)). That's called *server-sent
   events*.

Without `JIFFY_LIVE` the feed does nothing, so a part run from the terminal is unchanged.
A run from the dashboard saves its tables to `.cache/ui/`, never over a part's
`results.md`.

## The toolkit

Every challenge shares a few small tools, kept in [toolkit/](toolkit) so any challenge
(and any other project) can reuse them:

| Tool | What it does |
|---|---|
| [jiffy-service](toolkit/jiffy-service) | The fake server, the client that talks to it, and helpers to run one experiment |
| [jiffy-load](toolkit/jiffy-load) | The load generator: sends requests on a schedule and times each one |
| [jiffy-metrics](toolkit/jiffy-metrics) | Turns raw timings into p50/p99, busy % and queue length, prints tables, draws SVG charts |
| [jiffy-queueing](toolkit/jiffy-queueing) | The math that predicts latency before you measure it, plus a perfect simulator |
| [jiffy-ui](toolkit/jiffy-ui) | The dashboard: runs a part and draws its numbers as live charts |

## Check everything

```bash
./verify            # lint, strict types, all tests, every challenge part
./verify --quick    # the same with short runs
```

On Windows, run `./verify` from Git Bash, or `.\verify.ps1` in PowerShell. CI runs
`./verify --quick` on Ubuntu and Windows on every push.

## Related

[distributed-systems-challenges](https://github.com/ZeeshanAdilButt/distributed-systems-challenges)
does the same for correctness: what goes wrong when machines crash, stall and retry.

## License

MIT
