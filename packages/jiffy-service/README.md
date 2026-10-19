# jiffy-service

A small TCP service to experiment on: a fixed pool of workers behind one queue, optional
stop-the-world stalls, and a USE recorder inside, so it can report how busy and how
saturated it was. Also includes the client and the helpers that drive it.

```bash
python -m jiffy_service --workers 4 --stall-every 1.5 --stall-for 0.3
# listening 127.0.0.1 53817
```

```python
import random
from jiffy_load import poisson
from jiffy_service import Client, calibrate, drive_open, spawn

with spawn(workers=4) as address, Client(address) as client:
    service = calibrate(client, mean_work=0.010, workers=4)  # what 10 ms really costs here
    rate = 0.8 * 4 / service  # aim for 80% busy
    schedule = poisson(rate, 5.0, random.Random(1))
    run = drive_open(client, schedule, [0.010] * len(schedule), widths=(1.0, 0.01))
    print(run.latency().summary(), run.use)  # workload view, resource view
```

- **Protocol**: one JSON object per line over one long-lived connection. Requests carry an
  id, so many can be in flight and replies can come back in any order.
- **What the server measures**: `wait` (from when the reader thread took the request off
  the socket to when a worker picked it up) and `service` (from pickup to done). Delays
  before the reader sees a request are invisible to it, just like in most real services.
- **Stalls**: every thread freezes, readers included, like a GC pause or a descheduled VM.
- **Timers**: sleeps that need to be accurate use `time.sleep`, never `Event.wait(timeout)`.
  On Windows the latter is rounded up to the clock tick.
