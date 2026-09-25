---
slug: mental-map
title: Building the map
summary: Understand a system through three lenses — data flow, control flow and state — and keep the map on paper, not in your head.
order: 10
---

# Building the map

When people say they "understand" a codebase, they mean they carry a map of it: what the pieces are, how they connect, and where things change. You don't get that map by reading more. You get it by asking the right three questions and writing the answers down.

## Three lenses

### 1. Data flow — what moves through the system?

Pick the main piece of data (an order, a reading, a document) and follow it:

- **Where does it enter?** An API request, a CSV file, a queue message, a CLI argument.
- **How is it transformed?** Parsed, validated, enriched, priced, aggregated.
- **Where does it end up?** Stored, returned, rendered, sent.

```text
CSV row -> parse_row() -> Reading -> validate() -> Reading(clean)
        -> aggregator.add() -> HourlyStats -> storage.save() -> reports
```

Most bugs are data-flow bugs: a value is wrong at some point along this chain. If you have the chain written down, you know exactly where to put your probes.

### 2. Control flow — who calls whom?

Which code runs, in what order, and who triggers it?

- The entry points (CLI commands, API routes, scheduled jobs, message handlers)
- The main layers each one passes through (handler → service → repository)
- Anything that runs *implicitly*: decorators, callbacks, event listeners, background threads, `__init__`-time work, import-time side effects

Implicit control flow is where people get lost. If a function "somehow" runs, look for a registration: a decorator, a subscriber list, a scheduler entry.

### 3. State — what's remembered, and who changes it?

State is anything that survives between calls:

- database rows and files
- module-level globals, caches and registries
- instance attributes on long-lived objects
- class attributes (shared by every instance!)

For each piece of state, ask: **who writes it, and who reads it?** A value with one writer is easy to reason about. A value with five writers is where lost updates, stale caches and race conditions come from.

## Sketch boxes and arrows

You don't need a drawing tool. A few lines of text are enough:

```text
            +-------------+        +---------------+
 CLI ------>| BookingSvc  |------->|   pricing     |  (pure functions)
 API ------>|  create()   |        +---------------+
            |  cancel()   |------->+---------------+
            +------+------+        |  HoldManager  |  state: holds{} in memory
                   |               +-------+-------+  expires via clock
                   v                       |
            +-------------+                v
            |   Storage   |<----- releases seats on expiry
            |  (sqlite)   |
            +-------------+
```

Drawing it forces you to notice what you *don't* know yet: "wait, who calls `release_seats`?" Those questions are exactly what to investigate next.

## Ownership

In a healthy codebase each piece of data has an **owner** — one module responsible for its rules.

- `pricing` owns how a fare is computed.
- `HoldManager` owns when a hold expires.
- `Storage` owns how things are persisted.

When a bug report comes in, ask *whose rule was broken?* That points you to the owner module. And when you find a rule enforced in two places (fare rounding in both `pricing.py` and `invoice.py`), you've probably found a place where the two copies will drift apart — if they haven't already.

## Keep notes — your working memory is tiny

People can hold only about four chunks of information in mind at once. A codebase has hundreds. Stop trying to remember; write things down as you go. A simple template:

```text
ENTRY POINTS:
NOUNS (key types + fields):
FLOWS (entry -> ... -> end):
STATE (what's stored, who writes it):
OPEN QUESTIONS:
SUSPICIONS:
```

- **Open questions** keep you from forgetting what you meant to check.
- **Suspicions** are where your instincts said "that's odd" — a comment that disagrees with the code, a function with a surprising side effect, a missing test. Revisit them when a bug shows up; the answer is often already on your list.

## The map is never finished

Your first map will be wrong in places, and that's fine. Update it as you learn. After a recon, compare your map with reality: which module did you misjudge? Which flow did you miss? Those corrections are where your intuition for the *next* codebase comes from.

The goal isn't a perfect map. It's a map good enough that when a bug report arrives, you can point to the two or three boxes where it probably lives — and start there.
