# Part 3 · Tail at scale: results

## A. Fan-out: each backend call is slow 0.97% of the time (measured)

| fan-out k | slow: theory 1-(1-p)^k | slow: measured | p50     | p90     | p99     |
|-----------|------------------------|----------------|---------|---------|---------|
| 1         | 0.97%                  | 0.69%          | 3.07 ms | 3.39 ms | 4.14 ms |
| 5         | 4.8%                   | 7.7%           | 3.43 ms | 4.18 ms | 51.8 ms |
| 10        | 9.3%                   | 10.6%          | 4.44 ms | 51.3 ms | 52.9 ms |
| 20        | 17.7%                  | 15.3%          | 4.44 ms | 51.3 ms | 52.4 ms |
| 50        | 38.6%                  | 40.1%          | 7.98 ms | 52.9 ms | 57.3 ms |

## B. Hedging: resend any call still unanswered after 10.0 ms

| fan-out k | slow before | slow hedged | p99 before | p99 hedged | extra calls |
|-----------|-------------|-------------|------------|------------|-------------|
| 20        | 15.3%       | 0.33%       | 52.4 ms    | 15.2 ms    | 0.94%       |
| 50        | 40.1%       | 7.4%        | 57.3 ms    | 40.0 ms    | 11.1%       |
