# Systems performance challenges

[![verify](https://github.com/ZeeshanAdilButt/systems-performance-challenges/actions/workflows/verify.yml/badge.svg)](https://github.com/ZeeshanAdilButt/systems-performance-challenges/actions/workflows/verify.yml)

Small labs that answer one question each: **why does a system get slow, and how do you
measure it without fooling yourself?** Every lab runs on your laptop in about a minute,
against a real server, and every number it prints links back to the line of code that
made it.

This is a growing series. Later labs will come at performance from other angles (CPU,
memory, disk, network, the runtime) and build their own tools along the way.

## The labs

| Lab | The question | One-line answer |
|---|---|---|
| [01 · The knee](labs/01-the-knee) | How busy can a server get before people notice? | About 75%. After that, waiting time shoots up. |
| [02 · Averages lie](labs/02-averages-lie) | Can the graphs say "fine" while people wait? | Yes. Bursts hide inside averages, and some load tools miss most slow requests. |
| [03 · Tail at scale](labs/03-tail-at-scale) | What if one page needs answers from 50 servers? | A rare slow server makes 40% of pages slow. Sending a backup copy of late calls fixes it. |
| [04 · Adaptive hedging](labs/04-adaptive-hedging) | How late is "late" when normal calls keep getting slower? | Don't pick a number. A fixed timer resent 86% of calls; one set from recent calls resent 7%. |

Each lab is one folder with everything in it:

```
labs/01-the-knee/
  README.md      start here: what it tests, from zero, with links into the code
  knee.py        the whole experiment, top to bottom
  results.md     what it measured last time it ran on this laptop
  test_knee.py   checks that the experiment does what the README says
```

## 101: the words you need

You don't need any background. These are the only ideas the labs use.

- **Server**: a program that waits for requests and answers them. A website, an API, a
  database. Ours is a small fake server that runs on your laptop
  ([code](toolkit/jiffy-service/src/jiffy_service/server.py#L65)).
- **Request**: one question sent to the server ("give me this page"). Ours just says "do
  10 ms of work".
- **Worker**: the part of the server that actually does the work. Our server has 4, so it
  can work on 4 requests at the same time.
- **Queue**: the line requests wait in when every worker is busy, like a supermarket
  checkout.
- **Latency**: how long someone waited for their answer, from the moment they asked to
  the moment the answer arrived. Waiting in the queue plus the work itself. This is the
  number people feel.
- **p50, p99**: sort everyone's latency from fastest to slowest. p50 is the person in the
  middle (the typical wait). p99 is the person 99% of the way down, so only 1 in 100
  waited longer. The unhappy people are in the p99.
- **Busy % (utilization)**: how much of the time the workers were working. 50% means they
  were idle half the time.
- **Throughput**: how many requests the server finished per second.
- **Load generator**: a program that pretends to be lots of users sending requests. Ours
  is in [toolkit/jiffy-load](toolkit/jiffy-load).

A request's life, and where each of those times comes from:

```
 you want an answer          the server reads it        a worker picks it up        answer arrives
        |                           |                           |                           |
        |------- network -----------|-------- queue ------------|-------- work -------------|
        |                           |<-------- wait ----------->|<------- service --------->|
        |<---------------------------------- latency ------------------------------------->|
```

## Run a lab

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/). From this folder:

```bash
uv sync
uv run labs/01-the-knee/knee.py
```

Add `--quick` for a shorter run. The lab prints its tables and saves them to
`results.md` in its folder.

## Watch a lab live

If you'd rather watch charts than read tables, start the dashboard:

```bash
uv run jiffy-ui
```

It opens a page in your browser. Pick a lab, press **Run**, and four charts fill in while
the lab measures:

- **Latency**: p50 (the typical wait) and p99 (only 1 in 100 waited longer), one point
  per half second.
- **Server busy %**: how much of the time the workers were working, measured by the
  server itself ten times a second. A gap in this line means the server was frozen and
  couldn't report (lab 02 freezes it on purpose).
- **Queue**: how many requests were waiting in line.
- **Slow requests**: the share that took longer than the lab's "slow" line.

Numbered dashed lines mark each step of the lab (the same progress lines it prints in a
terminal). Hover over a chart to read the exact numbers. When the lab finishes, its
tables appear under the charts.

How the numbers get from the lab to the page:

1. The dashboard starts the lab exactly as you would in a terminal, plus one setting,
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

Without `JIFFY_LIVE` the feed does nothing, so a lab run from the terminal is unchanged.
A run from the dashboard saves its tables to `.cache/ui/`, never over a lab's
`results.md`. The page draws its own charts, so nothing extra gets installed.

## How a lab works

Every lab does the same four things:

1. **Start the server** in its own process, so it behaves like a separate machine.
2. **Measure first.** Ask the server how long "10 ms of work" really takes on this laptop
   (it's never exactly 10).
3. **Send load** on a fixed schedule, like real users who don't wait for each other.
4. **Collect two views** of the same run, and print them side by side:
   - the users' view: latency for every request;
   - the server's view: how busy it was and how long its queue got.

The interesting lessons are usually in the gap between those two views.

## The toolkit

The labs share a few small tools, kept in [toolkit/](toolkit) so every lab (and any other
project) can reuse them:

| Tool | What it does |
|---|---|
| [jiffy-service](toolkit/jiffy-service) | The fake server, the client that talks to it, and helpers to run one experiment |
| [jiffy-load](toolkit/jiffy-load) | The load generator: sends requests on a schedule and times each one |
| [jiffy-metrics](toolkit/jiffy-metrics) | Turns raw timings into p50/p99, busy % and queue length, and prints tables |
| [jiffy-queueing](toolkit/jiffy-queueing) | The math that predicts latency before you measure it, plus a perfect simulator |
| [jiffy-ui](toolkit/jiffy-ui) | The dashboard: runs a lab and draws its numbers as live charts |

## Check everything

```bash
./verify            # lint, strict types, all tests, every lab
./verify --quick    # the same with short lab runs
```

On Windows, run `./verify` from Git Bash, or `.\verify.ps1` in PowerShell. CI runs
`./verify --quick` on Ubuntu and Windows on every push.

## Related

[distributed-systems-challenges](https://github.com/ZeeshanAdilButt/distributed-systems-challenges)
does the same for correctness: what goes wrong when machines crash, stall and retry.

## License

MIT
