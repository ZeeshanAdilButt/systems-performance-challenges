# jiffy-load

Load generation that measures latency from when each request **should** have been sent.
Standard library only.

## Why "should"

A load tool that waits for each answer before sending the next request (closed loop)
slows down whenever the system slows down. It sends almost nothing during a stall, so it
records the stall once instead of once for every request that would have arrived. This
is *coordinated omission*, and it makes p99 look several times better than it is.

`open_loop` sends on a fixed schedule whether or not earlier requests have come back. It
measures `latency = done - intended`, so even its own lateness counts against the system.

```python
import random
from jiffy_load import open_loop, closed_loop, poisson, bursty

schedule = poisson(rate=200, duration=5, rng=random.Random(1))  # offsets in seconds
samples = open_loop(schedule, lambda i: client.call(i))  # call returns a Future
p99 = sorted(s.latency for s in samples)[int(0.99 * len(samples))]

closed = closed_loop(users=4, duration=5, call=lambda i: client.call(i), think=0.01)
```

- `poisson(rate, duration, rng)`: independent arrivals.
- `bursty(rate, duration, rng, period=0.2, on_fraction=0.25)`: the same average rate,
  packed into bursts.
- `uniform(rate, duration)`: perfectly even spacing.

The target can be anything that returns a `concurrent.futures.Future`: an HTTP client
wrapped in an executor, a gRPC future, or `jiffy_service.Client.work`.
