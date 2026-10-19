# How the reuse works

Same rule as in [distributed-systems-challenges](https://github.com/ZeeshanAdilButt/distributed-systems-challenges):
**challenges are disposable demonstrations, packages are the parts worth keeping.** A
challenge answers one question and can be thrown away once you understand the answer. A
package is something the next challenge, or a real project, will import.

## The layering

```
challenges/01-the-knee      challenges/02-averages-lie      challenges/03-tail-at-scale
          \                           |                              /
           +---------------> jiffy-service <------------------------+
                             (server, client, drive_open, calibrate)
                              /                    \
                     jiffy-load                  jiffy-metrics
              (schedules, open/closed loop)  (histogram, USE recorder, tables)

            jiffy-queueing (theory and simulation; used directly by 01)
```

Dependencies only point down. `jiffy-metrics`, `jiffy-load` and `jiffy-queueing` depend on
nothing but the standard library. `jiffy-service` depends on those two because it *is*
the lab bench: a server plus the code that drives it and reads both perspectives.

## When code becomes a package

Code moves from a challenge into `packages/` when both are true:

1. **A second challenge needs it.** `calibrate` began inside challenge 01. It moved into
   `jiffy-service` when 02 needed it too.
2. **It has a contract you can test without the challenge.** The histogram's contract is
   "every percentile within 1% of the truth", and a Hypothesis property checks it on
   random data. The USE recorder's contract is checked against a fake clock. A function
   that only makes sense inside one experiment stays in that experiment.

Some code was copied, not shared, on purpose. `tools/verify.py` started as a copy of the one in
distributed-systems-challenges with the Postgres parts removed. Two repositories that
each own their copy can evolve without coordinating. If a third repository needs the
same gate runner, that is the signal to make it a package.

## Each package stands alone

Every package in `packages/` has:

- a `src/` layout and a `py.typed` marker, and passes `mypy --strict`;
- its own `tests/`, which run without anything else in the repository;
- its own `pyproject.toml` and README, so it can be published or vendored on its own;
- no third-party runtime dependencies.

## Using a package from another project

From a sibling checkout (editable, so changes show up immediately):

```bash
uv add --editable "../systems-performance-challenges/packages/jiffy-metrics"
```

From GitHub, pinned to a commit or tag:

```bash
uv add "jiffy-metrics @ git+https://github.com/ZeeshanAdilButt/systems-performance-challenges#subdirectory=packages/jiffy-metrics"
```

Or with pip:

```bash
pip install "git+https://github.com/ZeeshanAdilButt/systems-performance-challenges#subdirectory=packages/jiffy-metrics"
```

## The other kind of reuse: connections

The client keeps one TCP connection open and multiplexes every request over it.
Requests carry an id, and replies come back in any order (`jiffy_service.protocol`).
The other way, a connection per request, costs a handshake per call. On Windows it also
runs out of ephemeral ports within seconds at a few hundred requests per second, because
every closed socket sits in `TIME_WAIT` for minutes. Pooling or multiplexing connections
does the same job as the worker pool: it pays a setup cost once and amortizes it over
many requests.
