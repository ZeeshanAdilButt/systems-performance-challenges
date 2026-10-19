# Lab 02 · Averages lie: results

## A. Same average load, 50% of 4 workers, two shapes

| workload                      | busy (1 s avg) | peak (1 s) | peak (10 ms) | 10 ms windows queueing | max queue | p50     | p99     |
|-------------------------------|----------------|------------|--------------|------------------------|-----------|---------|---------|
| smooth (Poisson)              | 48.0%          | 56.5%      | 100.0%       | 18.8%                  | 7         | 8.65 ms | 48.3 ms |
| bursty (50 ms on, 150 ms off) | 48.6%          | 55.3%      | 100.0%       | 48.2%                  | 36        | 29.4 ms | 98.0 ms |

## B. One service, a 300 ms pause every 1.5 s, ~100 req/s, measured three ways

| measured by                             | requests | mean    | p50     | p90     | p99     | p99.9  | max    | > 50 ms |
|-----------------------------------------|----------|---------|---------|---------|---------|--------|--------|---------|
| server's own metric (wait + service)    | 882      | 19.2 ms | 10.1 ms | 48.8 ms | 94.2 ms | 318 ms | 318 ms | 9.4%    |
| closed-loop tool (2 users)              | 696      | 15.9 ms | 8.39 ms | 27.7 ms | 311 ms  | 342 ms | 342 ms | 2.2%    |
| open-loop tool (from when each was due) | 882      | 40.4 ms | 11.0 ms | 173 ms  | 302 ms  | 319 ms | 319 ms | 17.7%   |

The service is frozen 20% of the time. The open-loop tool saw 17.7% of requests take over 50.0 ms; the closed-loop tool saw 2.2%, and the server's own metric 9.4%.
