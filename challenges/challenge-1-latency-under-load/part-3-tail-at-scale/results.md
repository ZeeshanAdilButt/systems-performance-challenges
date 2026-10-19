# Lab 03 · Tail at scale: results

## A. Fan-out: each backend call is slow 0.97% of the time (measured)

| fan-out k | slow: theory 1-(1-p)^k | slow: measured | p50     | p90     | p99     |
|-----------|------------------------|----------------|---------|---------|---------|
| 1         | 0.97%                  | 0.69%          | 3.36 ms | 4.06 ms | 10.4 ms |
| 5         | 4.8%                   | 7.7%           | 3.90 ms | 5.26 ms | 51.8 ms |
| 10        | 9.3%                   | 10.6%          | 4.71 ms | 51.3 ms | 52.4 ms |
| 20        | 17.7%                  | 17.6%          | 6.81 ms | 52.4 ms | 62.6 ms |
| 50        | 38.6%                  | 54.3%          | 22.7 ms | 57.8 ms | 82.7 ms |

## B. Hedging: resend any call still unanswered after 10.0 ms

| fan-out k | slow before | slow hedged | p99 before | p99 hedged | extra calls |
|-----------|-------------|-------------|------------|------------|-------------|
| 20        | 17.6%       | 2.3%        | 62.6 ms    | 24.1 ms    | 2.2%        |
| 50        | 54.3%       | 34.0%       | 82.7 ms    | 77.2 ms    | 40.4%       |
