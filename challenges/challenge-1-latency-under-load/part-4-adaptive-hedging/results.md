# Part 4 · Adaptive hedging: results

## A. Four ways to hedge, same 50-call pages, normal calls drifting from 2.00 ms to 14.0 ms

| policy                   | slow pages | p50     | p99     | extra calls | hedges that won | refused |
|--------------------------|------------|---------|---------|-------------|-----------------|---------|
| no hedging               | 40.0%      | 27.1 ms | 215 ms  | 0.0%        | -               | 0       |
| fixed 10 ms              | 0.0%       | 25.1 ms | 60.2 ms | 58.0%       | 2.4%            | 0       |
| adaptive p95             | 0.34%      | 25.3 ms | 72.0 ms | 6.9%        | 15.7%           | 0       |
| adaptive p95 + 5% budget | 5.5%       | 24.8 ms | 213 ms  | 2.7%        | 35.3%           | 524     |

## B. Phase by phase: the timer each policy used, and the extra calls it sent

| phase    | normal call        | fixed timer | adaptive timer | extra: fixed | extra: adaptive | extra: + budget |
|----------|--------------------|-------------|----------------|--------------|-----------------|-----------------|
| quiet    | 2.00 ms            | 10.0 ms     | 18.0 ms        | 21.8%        | 6.3%            | 2.1%            |
| climbing | 2.00 ms to 14.0 ms | 10.0 ms     | 22.9 ms        | 62.1%        | 7.9%            | 2.8%            |
| busy     | 14.0 ms            | 10.0 ms     | 22.2 ms        | 86.3%        | 5.6%            | 3.2%            |

## C. Where the budget said no (adaptive p95 + 5% budget)

| hedges a page asked for | pages | asked | refused | slow pages |
|-------------------------|-------|-------|---------|------------|
| none                    | 131   | 0     | 0       | 0          |
| 1 to 9                  | 131   | 289   | 29      | 5          |
| 10 to 50                | 28    | 632   | 495     | 11         |
