# Waken

A lightweight runtime that routes work from a Source, to an interchangeable
AI-agent Target, back through an Output.

```
Source → Runtime → Target → Response → Output
```

**Status:** pre-alpha, under active design/implementation. See
[docs/](docs/) for the full design: [prior art review](docs/prior-art.md),
[architecture decision record](docs/adr/0001-core-architecture.md), [public
API specification](docs/api-spec.md), and [implementation
plan](docs/implementation-plan.md).

```bash
pip install -e ".[dev]"
```

A full quickstart lands with the first usable release (see the
[implementation plan](docs/implementation-plan.md), M10) — there's no runnable
API yet.
