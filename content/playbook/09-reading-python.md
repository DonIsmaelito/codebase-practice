---
slug: reading-python
title: Reading Python fast — beacons and plans
summary: Fast readers don't read faster; they recognize familiar shapes at a glance and spend their attention only on what's unusual.
order: 9
---

# Reading Python fast: beacons and plans

A chess master glancing at a board doesn't see 32 pieces — they see four or five familiar *patterns*. Experienced programmers read code the same way. They recognize common shapes ("plans") in one glance, and notice small signals ("beacons") that tell them what code does before they've read it line by line.

You build this library by exposure, but you can speed it up by learning the most common shapes on purpose.

## Plans you'll see everywhere

**The accumulator loop** — build up a result:

```python
total = Decimal("0")
for line in invoice.lines:
    total += line.amount
```

Check: the starting value, what gets added, and whether anything should be skipped.

**Guard clauses** — reject bad cases early, then do the real work:

```python
def refund(booking):
    if booking is None:
        raise BookingNotFound()
    if booking.status is not Status.CONFIRMED:
        return Decimal("0")
    ...
```

Read the guards as the function's rules. Bugs often hide in a guard's condition (`<` vs `<=`, `and` vs `or`, a missing case).

**Grouping into a dict of lists:**

```python
by_customer = defaultdict(list)
for order in orders:
    by_customer[order.customer_id].append(order)
```

Recognize it instantly and move on — unless the key is suspicious (not unique enough? not normalized?).

**Building a lookup index** — turning repeated scans into dict lookups:

```python
products_by_sku = {p.sku: p for p in products}
```

Ask: are the keys unique? Is the index rebuilt when the data changes?

**Data models** — dataclasses, pydantic models, ORM classes. Read the fields and defaults; skip the boilerplate.

**Decorators wrapping behavior:**

```python
@retry(times=3)
@requires_role("admin")
def delete_account(user_id): ...
```

Each decorator changes how the function behaves when it's *called*. The order matters: the one closest to `def` wraps first.

**Context managers:**

```python
with session_scope() as session:
    ...
```

Something is set up before the block and torn down after it — a transaction, a lock, a temporary override. When debugging, open the context manager and check what happens when the block raises.

**Generator pipelines:**

```python
rows = read_rows(path)
valid = (r for r in rows if r.qty > 0)
batches = batched(valid, 500)
```

Nothing runs until the end of the chain is consumed, and each stage can be iterated only once.

**The retry loop, the registry dict, the state machine** — you'll meet each of these in client codebases, and each becomes a single glance once you've seen it three times.

## Names are beacons

Good names are compressed documentation. Read them deliberately:

| Name shape | Usually means |
|---|---|
| `is_*`, `has_*`, `can_*`, `should_*` | returns a bool |
| `get_*` | cheap lookup, may return `None` |
| `fetch_*`, `load_*` | I/O: network, disk or database |
| `ensure_*`, `get_or_create_*` | idempotent — creates only if missing |
| `validate_*`, `check_*` | raises (or returns errors) on bad input |
| `parse_*`, `from_*` | text or dict → object |
| `to_*`, `as_*`, `serialize_*` | object → text or dict |
| `*_by_*` (`orders_by_id`) | a dict index |
| `_leading_underscore` | internal; callers outside the module shouldn't touch it |
| `UPPER_CASE` | a constant — or a module-level global pretending to be one |

When a name and its behavior disagree (`get_user` that writes to the database, `is_valid` that mutates its input), you've found either a bug or a trap. Note it.

## Skim in layers

Don't read a module top to bottom. Read it in passes, and stop when you have what you need:

1. **Signatures only** — names, parameters, return types. This is the module's API.
2. **Docstrings and return statements** — what each function promises and what it actually hands back.
3. **Bodies of the functions your question touches** — and only those.

Editors help: collapse all functions, or use "go to symbol" to see the outline.

## Where complexity hides

Some constructs look simple but can hide a lot of behavior. Slow down when you see:

- **Properties** — `order.total` looks like an attribute but may run a query or a loop.
- **`__getattr__`, descriptors, metaclasses** — attribute access that runs code.
- **Decorators** — the function you're reading may not be the function that runs.
- **`**kwargs` pass-through** — arguments you can't see flowing to a function you haven't read.
- **Module-level state** — globals, caches and registries mutated from several places.
- **Nested loops and recursion** — where performance problems and edge cases live.
- **Anything that reads the clock, randomness or the environment** — behavior that changes between runs.

## Practice deliberately

When you finish reading a function, try to summarize it in one sentence that names its plan: *"groups orders by customer and sums the paid ones."* If you can't, you haven't recognized its shape yet — reread it until you can. Every time you name a plan, it gets a little faster to recognize the next time you see it.
