---
slug: root-cause
title: Fix the cause, not the symptom
summary: The line that crashes is rarely the line that's wrong — keep asking why until you reach the decision that broke the rule.
order: 7
---

# Fix the cause, not the symptom

Every bug has two locations: where it **shows up** and where it **comes from**. Beginners fix the first. Experienced engineers fix the second — and then check whether the same mistake exists anywhere else.

## What symptom patches look like

They're tempting because they make the report go away quickly:

- **Catch and ignore.** Wrapping the crash in `try/except: pass`. The error disappears; the bad data keeps flowing and corrupts something further down.
- **Special-casing the reported input.** `if sku == "HL-0915": ...` Fixes one customer, not the bug.
- **Clamping the output.** `total = max(total, 0)` because totals were sometimes negative. *Why* were they negative?
- **Deduplicating at the end.** `list(set(items))` in the display layer because items "sometimes appear twice."
- **Retrying until it works.** Retries hide races and nondeterminism; they don't remove them.
- **Changing the test to match the output.** The most dangerous one of all.

Each of these leaves the real defect in place, usually quieter and harder to find next time.

## An example

> Ticket: "Sometimes a customer's cart shows items they never added."

The symptom patch: filter the cart in the view so it only shows items the customer clicked. Tests pass, ticket closed.

Now ask *why* instead:

1. **Why does the cart contain foreign items?** Because `Cart.items` already has entries when a new cart is created.
2. **Why is a new cart non-empty?** Because `Cart.__init__(self, items=[])` stores the default list directly.
3. **Why is that a problem?** Default values are evaluated once, when the `def` runs — every cart created without `items` shares the *same* list.

```python
# the cause
class Cart:
    def __init__(self, customer_id, items=[]):
        self.customer_id = customer_id
        self.items = items

# the fix
class Cart:
    def __init__(self, customer_id, items=None):
        self.customer_id = customer_id
        self.items = list(items) if items is not None else []
```

The root-cause fix is *smaller* than the symptom patch, and it fixes every symptom at once — including ones nobody has reported yet.

## Ask "why?" until you hit a decision

Keep asking why until the answer is a **decision** someone made: a data structure choice, a contract between two functions, an assumption about input. That decision is where the fix belongs.

- "The report crashed" → why? → "a `None` price" → why? → "the importer stores `None` for a blank price column" → why? → "it silently coerces blanks instead of rejecting the row." **That** is the decision to change.

A useful test: after your fix, would the *next* bad input of the same kind also be handled correctly? If the answer is "only this exact one," you've patched a symptom.

## Where should the fix live?

Usually in one of two places:

1. **Where the invariant breaks.** The first place a value becomes wrong. If a function is supposed to return a sorted list and doesn't, fix that function — not the three callers that re-sort its output.
2. **At the boundary where bad data enters.** If malformed input is the problem, validate it once, where it enters the system (parser, API handler, importer), rather than defensively everywhere downstream.

Fixing things at the crash site is correct only when the crash site *is* where the invariant breaks.

## Check the other call sites

A bug is evidence of a **pattern** someone was willing to write. If they wrote it once, they may have written it again:

- Found a mutable default? Search the codebase for `=[]`, `={}` and `=set()` in `def` lines.
- Found `x or default` eating a zero? Search for `or DEFAULT` and friends.
- Found a naive/aware datetime comparison? Search for `datetime.now()` and `utcnow()`.
- Found an unparameterized SQL query? Search for `execute(f"`.

You don't have to fix every instance in the same change — but you should know about them, and mention them.

## When a symptom patch is the right call

Sometimes you genuinely need a stopgap: production is on fire, the root cause needs a migration, and a guard buys a day. That's fine if you're **honest** about it:

- Label it: `# Stopgap for INC-2211: root cause is X, fix tracked in TICKET-88`.
- Make it loud: log a warning when the guard triggers, so the problem doesn't become invisible.
- Schedule the real fix.

A labeled stopgap is engineering. An unlabeled one is a trap for the next person — who might be you.

## The checklist

Before you submit a fix, answer these:

- [ ] Can I explain the root cause in one sentence, without using the word "sometimes"?
- [ ] Does my fix change the place where the value first became wrong?
- [ ] Would a *different* input with the same flaw also be handled now?
- [ ] Have I searched for the same pattern elsewhere?
- [ ] Is there a regression test that fails without my change?
