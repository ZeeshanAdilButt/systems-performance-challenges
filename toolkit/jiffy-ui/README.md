# jiffy-ui

A local dashboard for the challenges. Pick a part of a challenge, press Run, and watch latency (p50 and p99),
server busy %, queue length and the share of slow requests move as the part measures.
The part's tables appear at the end. Standard library only: `http.server` and
server-sent events, with the charts drawn by the page itself.

```bash
uv run jiffy-ui                # opens http://127.0.0.1:8765/
uv run jiffy-ui --no-browser   # just print the address
```

## How the numbers get to the page

```
 part process ----- every finished request (batched, 10x a second) ---+
     |                                                               |
     +-- server process -- busy % and queue, last 100 ms, 10x a second --> jiffy-ui --> page
```

1. The dashboard starts the part as its own process, exactly as you would in a terminal,
   with `JIFFY_LIVE=127.0.0.1:<port>` set ([runner.py](src/jiffy_ui/runner.py)).
2. The part and the server it starts both see that variable and send their numbers to
   that port ([jiffy_metrics/live.py](../jiffy-metrics/src/jiffy_metrics/live.py)).
   Without the variable, nothing is sent and the part runs as usual.
3. Every half second, the dashboard turns what arrived into one point per chart
   ([board.py](src/jiffy_ui/board.py)) and pushes it to the page over one long HTTP
   response ([app.py](src/jiffy_ui/app.py)).
4. When the part exits, its report (`.cache/ui/<part>.md`) is sent to the page as well.

A new `challenges/challenge-*/part-*/` folder with one script and a README shows up on its own
([parts.py](src/jiffy_ui/parts.py)).
