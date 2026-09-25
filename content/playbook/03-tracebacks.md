---
slug: tracebacks
title: Reading a traceback like a map
summary: Read the last line first, find the last frame in your own code, then work upward to where the bad value was born.
order: 3
---

# Reading a traceback like a map

A traceback isn't an insult — it's a map of exactly how the program got to the crash. Most people read it top to bottom, get lost in library frames, and give up. Read it in this order instead.

## Step 1: the last line first

The bottom line tells you **what** went wrong:

```text
KeyError: 'sku'
```

The exception type is the category of problem; the message is the specific detail. Together they often narrow things down enormously before you've read anything else.

## Step 2: find the last frame in *your* code

Walk upward from the bottom. Skip frames from the standard library and from `site-packages` — those are the tools, and the tools are rarely broken. Stop at the first frame whose path is inside the project. That line is where your code handed something bad to the tool, or where it did the bad thing itself.

## Step 3: ask where the bad value was born

The crash site is where the bad value was *used*, which is often not where it was *created*. Keep walking up the frames and ask at each one: "was the value already wrong here?"

## An annotated example

```text
Traceback (most recent call last):
  File "/app/restock/cli.py", line 41, in main
    report = build_report(load_orders(args.path))
  File "/app/restock/report.py", line 18, in build_report
    totals = summarize(orders)
  File "/app/restock/report.py", line 33, in summarize
    by_sku[order["sku"]] += order["qty"]
KeyError: 'sku'
```

Read it like this:

1. **Bottom line:** `KeyError: 'sku'` — some dict has no `'sku'` key.
2. **Last frame in our code:** `report.py`, line 33, in `summarize`. The dict is `order`.
3. **Where was `order` born?** It came from `orders`, which came from `load_orders(args.path)` in `cli.py`. So the question becomes: *why does `load_orders` produce an order without `'sku'`?* Maybe the CSV header is `SKU`, or `sku ` with a trailing space, or the file starts with a BOM so the first header is actually `'﻿sku'`.

The traceback didn't point at `load_orders` at all — but reading it as a map led straight there.

## Chained exceptions: two phrases, two meanings

Sometimes you'll see two tracebacks glued together. The sentence between them tells you how they're related.

**"During handling of the above exception, another exception occurred:"**

The second error happened *inside an `except` block* while handling the first one. Usually the handler itself is buggy. Both tracebacks matter, but the first one is the original problem.

**"The above exception was the direct cause of the following exception:"**

Someone deliberately wrapped the first error with `raise NewError(...) from err`. The top traceback is the root cause; the bottom one is the translated, domain-level error. Read the top one for the real reason.

```python
try:
    row = self._rows[order_id]
except KeyError as err:
    raise OrderNotFound(order_id) from err   # produces "direct cause"
```

## What common exceptions usually mean

| Exception | Usually means |
|---|---|
| `KeyError: 'x'` | A dict lookup for a key that isn't there — check spelling, casing, stray whitespace, and where the dict was built. |
| `AttributeError: 'NoneType' object has no attribute 'x'` | Something returned `None` that you expected to be an object — a lookup that found nothing, or a function missing a `return`. Find where the `None` came from. |
| `AttributeError: 'X' object has no attribute 'y'` | A typo, the wrong type of object, or an attribute that was never set in `__init__` (for example, a missing `super().__init__()`). |
| `TypeError: unhashable type: 'list'` | A list or dict was used as a dict key or put in a set. |
| `TypeError: f() missing 1 required positional argument` | A signature changed, or a method is being called on the class instead of an instance. |
| `TypeError: '<' not supported between instances of ...` | Sorting or comparing mixed types — often `None` mixed in with values, or objects with no ordering. |
| `ValueError` | Right type, wrong value: `int("12a")`, unpacking the wrong number of items. |
| `IndexError: list index out of range` | Off-by-one or an unexpectedly empty list. |
| `UnboundLocalError` | A variable is assigned somewhere in the function, so it's local everywhere in it — but it was read before the assignment ran. |
| `RecursionError` | A missing or unreachable base case, or a cycle in data you're recursing over. |
| `RuntimeError: dictionary changed size during iteration` | Adding or removing keys while looping over the same dict. |
| `ImportError: cannot import name ... (most likely due to a circular import)` | Two modules import each other at the top level. |

## Reading pytest failures

pytest adds two helpful markers:

```text
    def test_bulk_discount():
        cart = Cart(lines=[Line("A1", qty=10, unit_price=Decimal("2.00"))])
>       assert cart.total() == Decimal("18.00")
E       AssertionError: assert Decimal('20.00') == Decimal('18.00')
E        +  where Decimal('20.00') = <bound method Cart.total ...>()
```

- `>` marks the line that failed.
- `E` lines show the actual values — here the discount wasn't applied at all (20.00 instead of 18.00). That's a *different* bug from "the discount is slightly wrong", and the values tell you which one you have.

Useful flags: `--tb=short` for compact tracebacks, `-l` to show local variables in each frame, and `--pdb` to drop into the debugger right at the failure.

## The habit

Every time you see a traceback: last line, last frame in your code, then work upward to where the value was born. After a few dozen times it becomes automatic — and tracebacks stop being scary and start being the fastest clue you'll ever get.
