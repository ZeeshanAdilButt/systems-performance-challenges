# jiffy-metrics

Latency histograms, plus utilization and saturation of a resource worked out from exact
transitions rather than samples. Standard library only.

## Histogram

Log-spaced buckets with bounded memory. Every percentile is within `precision` (1% by
default) of the true value, however many values you record. The idea behind HdrHistogram,
in about a hundred lines.

```python
from jiffy_metrics import Histogram, ms

h = Histogram()
for latency in latencies:  # seconds
    h.record(latency)
print(ms(h.percentile(99)), h.fraction_above(0.050))
s = h.summary()  # count, mean, p50, p90, p99, p999, max
```

## UseRecorder

Tell it about every transition: work arrived (`enqueued`), a worker took it (`started`),
the work is done (`finished`). It keeps the exact state at every instant. Afterwards you
can look at windows of any width, so one run gives both the one-second view and the
ten-millisecond view.

```python
from jiffy_metrics import UseRecorder

use = UseRecorder(capacity=4)
# ... in the server:  use.enqueued(); use.started(); use.finished(ok=True)
coarse = use.summary(1.0)  # utilization, peak_utilization, saturated_windows, max_queue
fine = use.summary(0.01)  # the same run, ten-millisecond windows
```

*Saturation* means work waiting while every worker is busy. A request that waits a few
microseconds for an idle worker to wake up does not count.

## Report helpers

`table(headers, rows)` gives a Markdown table whose columns also line up in a terminal.
`bars(labels, values)` draws a text bar chart, and `ms()` and `pct()` format numbers.
