# Systems performance challenges

[![verify](https://github.com/ZeeshanAdilButt/systems-performance-challenges/actions/workflows/verify.yml/badge.svg)](https://github.com/ZeeshanAdilButt/systems-performance-challenges/actions/workflows/verify.yml)

Small, runnable labs on what makes systems fast or slow: latency, utilization,
saturation, queueing, and why the obvious numbers mislead. Each challenge takes one idea
and runs it on your machine against a real server process, over real TCP. It puts the
prediction (queueing theory), a perfect simulation of the same workload, and the
measurement side by side, so you can see where they agree and where they don't.

This is a growing series. New challenges come at performance from different angles
(CPU, memory, disk, network, the runtime, the kernel), go deeper as they go, and build
their own tools when the existing ones can't show what matters.

Everything is plain Python. No database, no Docker, and it runs the same on Windows,
macOS and Linux.

## Challenges

| | Challenge | The question | What it shows |
|---|---|---|---|
| 01 | [The knee](challenges/01-the-knee) | How much busier can this service get before users notice? | p99 roughly quadruples between 70% and 96% busy. Theory, simulation and reality agree on the shape. |
| 02 | [Averages lie](challenges/02-averages-lie) | Can the dashboard say "fine" while users wait? | Same 1-second utilization, 2x the p99 under bursts. A closed-loop load tool reports a fraction of the slow requests an open-loop one sees. |
| 03 | [Tail at scale](challenges/03-tail-at-scale) | What happens when one request calls fifty backends? | A backend slow 1% of the time makes 40% of requests slow. Hedging takes that under 1% for ~2% extra calls. |

Each challenge has its own README with the design, the measured results, and things to
try.

## Run it

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-packages
uv run knee              # about a minute
uv run averages-lie      # about 45 seconds
uv run tail-at-scale     # about a minute and a half
```

Add `--quick` to any of them for a shorter run. Each prints its tables and writes a
Markdown report to `reports/`.

## Learn it

Start with [docs/mental-model.md](docs/mental-model.md). It defines each term
(latency, service time, wait time, utilization, saturation, bottleneck) and points to the
number in the output that shows it. Then run 01, 02 and 03 in that order. Each one
builds on the vocabulary of the one before.

## Packages

The parts worth reusing live in `packages/`. Each is small, typed (`mypy --strict`),
tested on its own, and uses only the standard library. [docs/reuse.md](docs/reuse.md)
explains the layering, and when code moves from a challenge into a package.

| Package | What it is |
|---|---|
| [jiffy-metrics](packages/jiffy-metrics) | A latency histogram with bounded error, and a USE recorder that turns exact transitions into utilization and saturation at any window width. |
| [jiffy-load](packages/jiffy-load) | Open- and closed-loop load generation. Latency is measured from when each request was due, so coordinated omission cannot hide a stall. |
| [jiffy-queueing](packages/jiffy-queueing) | M/M/c formulas (Erlang C, Little's law), and an exact FCFS simulator that replays any workload. |
| [jiffy-service](packages/jiffy-service) | The server under test: a worker pool, one multiplexed connection, injected stalls, and helpers that collect the client's and the server's view of one run. |

## Verify everything

```bash
./verify            # lint, strict types, all tests, every challenge in full
./verify --quick    # the same with short challenge runs (about two minutes)
```

On Windows, `./verify` works from Git Bash, or run `.\verify.ps1` in PowerShell. The
summary lands in `reports/verify.md`. CI runs `./verify --quick` on Ubuntu and Windows on
every push.

## Layout

```
challenges/   one directory per challenge, each its own Python project
packages/     the jiffy-* libraries
docs/         the mental model, and how reuse works
tools/        verify.py, the gates behind ./verify
```

The repository is a uv workspace: `uv sync --all-packages` installs every challenge and
package in editable mode.

## Related

[distributed-systems-challenges](https://github.com/ZeeshanAdilButt/distributed-systems-challenges)
works the same way for correctness under failure: leases, fencing, exactly-once effects,
chaos. This repository is about speed under load.

## License

MIT
