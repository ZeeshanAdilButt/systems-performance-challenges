# jiffy-queueing

Predict latency before you measure it: M/M/c formulas, plus an exact simulator that
replays any workload through `c` first-come first-served workers. Standard library only.

```python
from jiffy_queueing import MMc, fcfs, latency_multiplier

q = MMc(arrival_rate=360, service_time=0.0105, servers=4)
q.utilization  # 0.945
q.prob_wait  # Erlang C: chance a request has to queue
q.mean_latency  # wait + service
q.wait_percentile(99)  # closed form for M/M/c
latency_multiplier(0.9)  # 10.0: one worker at 90% busy, latency = 10x service

jobs = fcfs(arrival_times, service_times, servers=4)  # start, end, wait, latency per job
```

`fcfs` takes real numbers as easily as made-up ones. Feed it the arrival times and service
times you measured on a real system, and it shows what a perfect queue would have done
with exactly that workload. The difference between that and what you measured is your
system's own overhead.
