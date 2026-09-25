---
slug: search
title: Search is your superpower
summary: Experts don't remember where things are — they search for them, precisely, and follow the data instead of the file tree.
order: 4
---

# Search is your superpower

Watch an experienced engineer in an unfamiliar codebase and you'll notice they barely scroll. They search, jump, search again. Navigation isn't about memory; it's about knowing **what to search for** and **which kind of jump to make**.

## Your toolkit in this IDE

| Action | Shortcut | Use it when |
|---|---|---|
| Quick open | **Cmd+P** | You can guess part of a file name (`pricing`, `conftest`). |
| Search in files | **Cmd+Shift+F** | You have a string: an error message, a log line, a name. |
| Go to definition | **F12** / Cmd+click | You're looking at a call and want to see what it does. |
| Find references | **Shift+F12** | You're looking at a definition and want to see who uses it. |
| Terminal grep | `grep -rn "text" --include="*.py" .` | You want the same thing from the terminal. |

## Move 1: grep the exact error or log string

If the bug report contains an error message or a log line, search for its **literal, fixed part**:

```text
Report: "ERROR could not allocate deck space for sailing HL-0915 (need 11.5m)"
Search: could not allocate deck space
```

Leave out the parts that change per event (IDs, numbers) — they were filled in by an f-string and won't appear in the source. This single search often lands you on the exact line that produced the symptom. From there you're debugging, not exploring.

## Move 2: search the nouns and verbs of the ticket

"Refund is wrong when a booking is cancelled after departure." Search for `refund`, then `cancel`. If a search returns 80 hits, make it more precise:

- `def refund` or `def cancel` — find the definitions
- `refund(` — find the calls
- `class Refund` — find the type

## Move 3: definition vs references

These two jumps answer different questions:

- **Go to definition (F12)** answers *"what does this do?"* — it moves you *down* the call stack.
- **Find references (Shift+F12)** answers *"who depends on this?"* — it moves you *up*, and shows every call site.

Tracing a flow is mostly F12. Assessing the impact of a change ("if I change `quote()`, what breaks?") is mostly Shift+F12.

## Move 4: separate writes from reads

When a field has the wrong value, you don't care about the forty places that *read* it. You care about the few that *write* it:

```text
.status =          assignments to an attribute
status=            keyword arguments (constructors, replace(), update calls)
["status"] =       dict-style writes
"status":          dict literals / JSON payloads
setattr(           dynamic writes
```

Five targeted searches beat scrolling through forty results.

## Move 5: follow the data, not the files

The file tree tells you how the code is *organized*. The bug lives wherever the *data* goes wrong. Pick the wrong value and ask three questions:

1. **Where is it created?** (search for the constructor or where the field is first set)
2. **Where is it transformed?** (functions that take it and return a modified version)
3. **Where is it consumed?** (where the symptom shows up)

Then check the value at each hop. The bug sits between the last hop where the value was right and the first hop where it was wrong.

## Move 6: search the tests too

Tests are code that *uses* the thing you're investigating, with known inputs and expected outputs. Searching `tests/` for a function name often gives you a ready-made example of how to call it — and a quick way to reproduce the bug.

## Making searches precise

- **Match case** when the name is distinctive: `Booking` the class vs `booking` the variable.
- **Whole word** to avoid `total` matching `subtotal` and `totally`.
- **Regex** when the pattern varies: `def (create|update)_booking`, `status\s*=`.
- **Scope to a folder or file type** when a name is common.

## A worked example

> Ticket: "Customers in Norway see prices in USD."

1. Search `USD` — one hit, in `pricing/currency.py`: `DEFAULT_CURRENCY = "USD"`.
2. Shift+F12 on `DEFAULT_CURRENCY` — used in `resolve_currency(customer)`.
3. F12 into `resolve_currency` — it reads `customer.country` from a config mapping loaded from YAML.
4. Open the YAML: `NO: NOK`. PyYAML reads the unquoted key `NO` as the boolean `False`, so the lookup for `"NO"` misses and falls back to USD.

Four searches, one jump each, and you never opened a file you didn't need.

## The mindset

Every time you catch yourself scrolling or opening files at random, stop and ask: *what exact string or symbol would lead me to the answer?* Then search for it. Search is cheap; attention isn't.
