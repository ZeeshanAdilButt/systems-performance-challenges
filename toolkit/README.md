# Toolkit

The shared tools every lab uses. A lab answers one question. A tool is something the
next lab, or a real project, will reuse.

| Tool | What it does, in plain words | Main code |
|---|---|---|
| [jiffy-service](jiffy-service) | The fake **server** (4 workers and a line), the **client** that talks to it, and helpers to run one experiment and collect both views | [server](jiffy-service/src/jiffy_service/server.py), [client](jiffy-service/src/jiffy_service/client.py), [experiment](jiffy-service/src/jiffy_service/experiment.py) |
| [jiffy-load](jiffy-load) | The **load generator**: decides when each request is sent, sends it, and times it. Also a **budget** that caps extra calls (hedges, retries) | [schedules](jiffy-load/src/jiffy_load/arrivals.py), [senders](jiffy-load/src/jiffy_load/runner.py), [budget](jiffy-load/src/jiffy_load/budget.py) |
| [jiffy-metrics](jiffy-metrics) | Turns raw timings into **p50/p99** (of a whole run, or of only the most recent calls), **busy %** and **queue length**, prints tables, and sends a **live feed** while a lab runs | [percentiles](jiffy-metrics/src/jiffy_metrics/histogram.py), [recent percentile](jiffy-metrics/src/jiffy_metrics/rolling.py), [busy % and queue](jiffy-metrics/src/jiffy_metrics/use.py), [tables](jiffy-metrics/src/jiffy_metrics/report.py), [live feed](jiffy-metrics/src/jiffy_metrics/live.py) |
| [jiffy-queueing](jiffy-queueing) | The **math** that predicts waiting before you measure, and a perfect **simulator** to compare against | [formulas](jiffy-queueing/src/jiffy_queueing/theory.py), [simulator](jiffy-queueing/src/jiffy_queueing/simulate.py) |
| [jiffy-ui](jiffy-ui) | The **dashboard**: runs a lab and draws its live feed as charts in the browser | [runs a lab](jiffy-ui/src/jiffy_ui/runner.py), [chart points](jiffy-ui/src/jiffy_ui/board.py), [web server](jiffy-ui/src/jiffy_ui/app.py), [page](jiffy-ui/src/jiffy_ui/page.html) |

## How they fit together

```
 labs/01-the-knee   labs/02-averages-lie   labs/03-tail-at-scale   labs/04-adaptive-hedging
         \                    |                      |                        /
          +-------------------+---> jiffy-service <--+------------------------+
                            (server, client, run helpers)
                                 /                \
                       jiffy-load             jiffy-metrics
                   (send and time,          (p99, recent p95,
                    hedge budget)            busy %, queue)

                jiffy-queueing  (math and simulation, used by lab 01)

                jiffy-ui  (the dashboard: starts any lab, listens to jiffy-metrics' live feed)
```

Arrows only point down. `jiffy-metrics`, `jiffy-load` and `jiffy-queueing` use nothing
but Python's standard library. `jiffy-service` uses the other two because it is the lab
bench: a server plus the code that drives it and reads the results. `jiffy-ui` sits
outside the labs: it starts one as a separate process, the same way you would, and only
needs `jiffy-metrics`.

## When code becomes a tool

Code moves out of a lab and into `toolkit/` when both are true:

1. **A second lab needs it.** `calibrate` began inside lab 01. It moved into
   `jiffy-service` when lab 02 needed it too.
2. **It can be tested on its own.** The percentile code promises "always within 1% of
   the true answer", and a test checks that on thousands of random inputs. The busy %
   code is checked against a fake clock. Code that only makes sense inside one experiment
   stays in that lab.

## Each tool stands alone

Every tool here has:

- a `src/` folder and full type hints (checked with `mypy --strict`);
- its own `tests/`, which run without anything else in the repository;
- its own `pyproject.toml` and README, so it can be installed on its own;
- no third-party dependencies.

## Using a tool in another project

From a folder next to this one (changes show up immediately):

```bash
uv add --editable "../systems-performance-challenges/toolkit/jiffy-metrics"
```

From GitHub:

```bash
uv add "jiffy-metrics @ git+https://github.com/ZeeshanAdilButt/systems-performance-challenges#subdirectory=toolkit/jiffy-metrics"
```

## One connection, many requests

The client opens one network connection and sends every request over it. Each request
carries a number, and the answer carries the same number back, so answers can arrive in
any order ([protocol](jiffy-service/src/jiffy_service/protocol.py)). Opening a new
connection per request would cost a handshake every time, and on Windows it runs out of
connection ports within seconds at a few hundred requests per second. Reusing one
connection pays the setup cost once, the same idea as keeping workers around instead of
hiring one per customer.
