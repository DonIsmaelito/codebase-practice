---
slug: orient
title: The first 10 minutes in an unfamiliar codebase
summary: You never read a codebase front to back — you read it with a question, in a fixed order, and stop as soon as you can answer it.
order: 1
---

# The first 10 minutes in an unfamiliar codebase

Opening a repository with forty files and no idea where anything lives feels like being dropped into a city without a map. Here's the secret experienced engineers don't always say out loud: **they don't read everything either.** They follow a routine that builds a rough map fast, and then they read *only* what their current question needs.

Understanding a codebase isn't something you finish. You understand *enough* to do the next thing, and you add detail on demand.

## The routine

Give yourself about ten minutes. Keep a notes file open while you work — anything you learn goes there, not in your head.

### 1. README and pyproject.toml (1 minute)

You're looking for three things:

- **What does this thing do?** One sentence, in your own words.
- **How is it run?** A CLI command, a web server, a library that other code imports, a batch job?
- **What does it depend on?** Dependencies are architecture clues:
  - `fastapi`, `httpx` → a web service, probably with an API layer
  - `sqlalchemy`, `sqlite3` → a database, so look for models and a session or connection helper
  - `click` / `argparse` → a CLI, so look for command functions
  - `pandas` / `numpy` → data processing, so look for a pipeline

READMEs go stale. Treat them as hints, not truth.

### 2. The directory tree (1–2 minutes)

The tree is the codebase's table of contents. Read the names and guess what each module is responsible for:

```text
harborline/
  __init__.py
  cli.py              # entry point? commands?
  config.py           # settings
  models.py           # the nouns: Sailing, Booking, Vessel...
  pricing.py          # fares, discounts
  booking_service.py  # the verbs: create/cancel a booking
  storage.py          # persistence
  notifications.py    # emails / messages
  utils.py            # grab bag — don't start here
tests/
  conftest.py
  test_booking_service.py
  test_pricing.py
```

You've learned a lot without opening a single file. You can already guess that a "wrong price" bug lives in `pricing.py` or where `booking_service.py` calls into it.

### 3. Entry points (1–2 minutes)

Find where execution *starts*:

- `__main__.py`, `cli.py`, `main.py`, `app.py`
- `[project.scripts]` in `pyproject.toml`
- `app = FastAPI()` plus `@app.get(...)` / `router` decorators
- `if __name__ == "__main__":` blocks

An entry point shows you which operations the system offers to the world. That's the list of flows you might have to trace.

### 4. The core data types (2 minutes)

Open the models: dataclasses, pydantic models, ORM classes, `TypedDict`s. These are the **nouns** of the system. Once you know that a `Booking` has a `sailing_id`, a list of `passengers` and a `status`, every function name starts to make sense — `confirm_booking` probably flips `status`, and `allocate_deck_space` probably reads `vehicles`.

Write the nouns and their key fields into your notes.

### 5. Trace ONE flow end to end (3 minutes)

Pick the single most important operation — usually the one your ticket mentions. Follow it from the entry point down:

```text
cli.book  ->  BookingService.create()  ->  pricing.quote()  ->  storage.save()
                        |
                        +-> notifications.send_confirmation()
```

Don't read every line of every function on the way. Read signatures, read what gets passed to the next call, and skim the body only far enough to see which function it calls next. Use **go to definition** (F12) to jump down the stack instead of hunting through files.

One traced flow teaches you how the layers talk to each other, and most other flows follow the same shape.

### 6. Skim the test names (1 minute)

```bash
pytest --collect-only -q
```

Test names are a spec written by the people who built the system: `test_cancel_refunds_full_fare_within_24h`, `test_vehicle_deck_rejects_overbooking`. They tell you what the system is *supposed* to do, including the edge cases the team cared about.

## What you should have after ten minutes

A note that looks something like this:

```text
WHAT: ferry booking backend (library + CLI)
ENTRY: cli.py (book, cancel, manifest); BookingService is the core
NOUNS: Sailing(id, departs_at, deck_capacity_m), Booking(passengers, vehicles, status)
FLOW:  book -> BookingService.create -> pricing.quote -> storage.save
TESTS: pricing has good coverage; storage has almost none
QUESTIONS: where are holds expired? what rounds fares?
```

That's a working map. It's incomplete, and it's supposed to be.

## Common traps

- **Starting in `utils.py`.** It's the least informative file in any codebase: lots of unrelated helpers and no story.
- **Reading files alphabetically or top to bottom.** You'll run out of energy before you reach anything relevant.
- **Trying to understand everything before touching anything.** Understanding comes faster once you have a question. Let the ticket drive your reading.
- **Trusting comments over code.** Comments describe what someone *meant*; code is what actually happens. When they disagree, the code wins — and the disagreement is often the bug.

## When you have a ticket

Everything above gets faster with a question in hand. Pull the nouns and verbs out of the ticket ("the *refund* is wrong when a *booking* is *cancelled* after *departure*"), search for them, and trace just that flow. You'll often find the right file in under two minutes — without having read most of the codebase at all.
