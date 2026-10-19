# jiffy-ui

A local dashboard for the labs. Pick a lab, press Run, and watch latency (p50 and p99),
server busy %, queue length and the share of slow requests move as the lab measures.
The lab's tables appear at the end. Standard library only: `http.server` and
server-sent events, with the charts drawn by the page itself.

```bash
uv run jiffy-ui                # opens http://127.0.0.1:8765/
uv run jiffy-ui --no-browser   # just print the address
```

## How the numbers get to the page

```
 lab process ----- every finished request (batched, 10x a second) ---+
     |                                                               |
     +-- server process -- busy % and queue, last 100 ms, 10x a second --> jiffy-ui --> page
```

1. The dashboard starts the lab as its own process, exactly as you would in a terminal,
   with `JIFFY_LIVE=127.0.0.1:<port>` set ([runner.py](src/jiffy_ui/runner.py)).
2. The lab and the server it starts both see that variable and send their numbers to
   that port ([jiffy_metrics/live.py](../jiffy-metrics/src/jiffy_metrics/live.py)).
   Without the variable, nothing is sent and the lab runs as usual.
3. Every half second, the dashboard turns what arrived into one point per chart
   ([board.py](src/jiffy_ui/board.py)) and pushes it to the page over one long HTTP
   response ([app.py](src/jiffy_ui/app.py)).
4. When the lab exits, its report (`.cache/ui/<lab>.md`) is sent to the page as well.

A new folder in `labs/` with one script and a README shows up on its own
([labs.py](src/jiffy_ui/labs.py)).
