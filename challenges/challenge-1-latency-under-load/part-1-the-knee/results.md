# Lab 01 · The knee: results

## Theory first: latency as a multiple of service time (M/M/c)

| busy | 1 worker: mean | ~p99   | 4 workers: mean | ~p99   |
|------|----------------|--------|-----------------|--------|
| 50%  | 2.0x           | 8.8x   | 1.1x            | 2.4x   |
| 70%  | 3.3x           | 15.2x  | 1.4x            | 4.1x   |
| 80%  | 5.0x           | 22.9x  | 1.7x            | 6.1x   |
| 90%  | 10.0x          | 46.0x  | 3.0x            | 11.9x  |
| 95%  | 20.0x          | 92.1x  | 5.5x            | 23.5x  |
| 99%  | 100.0x         | 460.5x | 25.4x           | 115.6x |

(~p99 is the 99th-percentile wait plus one mean service time.)

## Calibration: measure, don't guess

Asked for 10.0 ms of work per request on average; the server took 10.3 ms. Arrival rates below are planned from the measured number.

## The sweep: 4 workers, open-loop Poisson load, 4s or more per point

| aimed | busy (server) | req/s | max queue | mean: theory | sim     | real    | p99: sim | real    |
|-------|---------------|-------|-----------|--------------|---------|---------|----------|---------|
| 10%   | 11.9%         | 43    | 1         | 11.2 ms      | 11.2 ms | 11.8 ms | 44.2 ms  | 44.6 ms |
| 30%   | 30.8%         | 114   | 3         | 11.1 ms      | 11.0 ms | 11.5 ms | 52.9 ms  | 53.4 ms |
| 50%   | 51.9%         | 200   | 7         | 11.7 ms      | 11.5 ms | 12.0 ms | 51.8 ms  | 52.4 ms |
| 70%   | 70.2%         | 271   | 11        | 14.6 ms      | 14.3 ms | 15.2 ms | 53.4 ms  | 54.5 ms |
| 80%   | 77.8%         | 307   | 16        | 16.9 ms      | 15.6 ms | 16.7 ms | 57.3 ms  | 58.4 ms |
| 85%   | 83.7%         | 330   | 32        | 21.4 ms      | 20.5 ms | 23.0 ms | 91.4 ms  | 98.0 ms |
| 90%   | 88.7%         | 342   | 50        | 29.9 ms      | 36.9 ms | 44.5 ms | 128 ms   | 144 ms  |
| 95%   | 96.6%         | 367   | 98        | 120 ms       | 90.9 ms | 117 ms  | 219 ms   | 250 ms  |

p99 latency, real, by how busy the server was:

```
12% busy | ######### 44.6 ms
31% busy | ########### 53.4 ms
52% busy | ########## 52.4 ms
70% busy | ########### 54.5 ms
78% busy | ############ 58.4 ms
84% busy | #################### 98.0 ms
89% busy | ############################# 144.5 ms
97% busy | ################################################## 249.7 ms
```

From 12% to 97% busy, the server did 8.5x the work, and p99 latency went from 44.6 ms to 250 ms (5.6x).
