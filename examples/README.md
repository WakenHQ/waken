# Examples

- **`quickstart.py`** — the smallest possible program: one target, one line to run it.
- **`scheduler.py`** — `every`/`after` firing on a schedule.
- **`broadcast.py`** — sending one prompt to every registered target concurrently.
- **`webhook.py`** — routing an inbound HTTP POST to a Target.

All of them run the same way:

```bash
waken run examples/quickstart.py
```

None of them need an API key — they use a trivial local `echo`/`shout`/`whisper`
target instead of a real LLM adapter, so you can see the routing work before
wiring up `waken-claude` or another adapter package.
