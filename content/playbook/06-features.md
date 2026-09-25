---
slug: features
title: Adding a feature to someone else's code
summary: Find the nearest existing feature and mirror it — a small, consistent diff beats a clever new design every time.
order: 6
---

# Adding a feature to someone else's code

Writing a feature from scratch is one skill. Adding one to a codebase you didn't design is a different, more common one. The goal isn't the cleverest implementation — it's the one that looks like it was always there.

## 1. Read the ticket like a contract

Before touching code, pull the ticket apart:

- **Inputs:** what data comes in, and in what shape?
- **Outputs:** what comes back — exact names, types and units?
- **Errors:** what should happen on bad input? Which exception, which status code?
- **Examples:** the concrete cases in the ticket are your first acceptance tests.
- **Edge cases:** anything the ticket mentions explicitly, plus the usual suspects (empty, zero, boundary, duplicate, time zone).
- **Out of scope:** what you should *not* build.

Write down anything ambiguous as a question. In a real job you'd ask; here, pick the most reasonable interpretation, write it down, and stay consistent with it.

## 2. Find the nearest existing feature

This is the single most useful move. Almost every feature has a **sibling** already in the codebase:

- Adding a new export format? There's an existing exporter.
- Adding a new discount type? There's an existing discount.
- Adding a new endpoint? There's one right next to it doing something similar.
- Adding a new CLI command? Look at how the others are registered.

Find the sibling (search for its name, then use Find references), trace how it's wired end to end, and **mirror its shape**: the same layers, the same naming, the same error types, the same test layout.

```python
# existing sibling in pricing/rules.py
class SeniorDiscount(Rule):
    code = "SENIOR"

    def applies_to(self, booking: Booking) -> bool:
        return any(p.age >= 65 for p in booking.passengers)

    def amount(self, booking: Booking) -> Decimal:
        return booking.base_fare * Decimal("0.20")
```

A ticket for a "student discount" now looks like a fifteen-minute job: a new `Rule` subclass, registered wherever `SeniorDiscount` is registered, tested the way `SeniorDiscount` is tested.

## 3. Locate the extension points

Well-structured code has designated places where new behavior plugs in:

- **Registries:** a dict of handlers, a list of rules, a decorator that registers plugins
- **Strategy classes:** a base class or `Protocol` with several implementations
- **Dispatch tables:** `match` statements or `if/elif` chains on a type or status
- **Configuration:** tables in YAML/JSON, enum members, constants
- **Routers:** API route registration, CLI command groups

If you find yourself editing ten unrelated files, stop and look again — you've probably missed the extension point.

## 4. Plan the diff before you write it

Write down which files you'll change and why:

```text
pricing/rules.py        + StudentDiscount rule
pricing/__init__.py     register it in DEFAULT_RULES
models.py               + Passenger.student_id (optional)
tests/test_rules.py     + tests mirroring the SeniorDiscount ones
```

Small and local is the goal. A reviewer should be able to understand the change in one sitting. If the plan requires refactoring something first, do the refactor as a separate step with the tests green before adding the feature.

## 5. Spec → acceptance tests → code

1. Turn the ticket's examples into tests. Run them and **watch them fail** for the right reason — "`StudentDiscount` doesn't exist", not an unrelated import error.
2. Write the simplest code that makes them pass.
3. Add tests for the edge cases on your list.
4. Run the **whole** suite.

## 6. Follow local conventions — even ones you'd do differently

Consistency beats personal preference. Match what's already there:

- naming style (`get_x` vs `fetch_x`, `snake_case` module names)
- error handling (does the codebase raise domain exceptions or return `None`?)
- logging style and levels
- type hints (present or absent, `Optional[X]` or `X | None`)
- where tests live and how fixtures are used

If a convention is genuinely harmful, mention it as a follow-up — don't smuggle a style change into a feature.

## 7. The edge-case checklist

Before calling it done, check each of these against your implementation:

- [ ] Empty input (no items, empty string, empty file)
- [ ] Zero and negative values
- [ ] Exactly at each boundary the ticket mentions (≤ vs <)
- [ ] `None` / missing optional fields
- [ ] Duplicates and repeated calls
- [ ] Time: time zones, midnight, month-end, DST — if time is involved at all
- [ ] Money: `Decimal`, rounding rule, currency — if money is involved at all
- [ ] Existing behavior unchanged (the old tests still pass)

## What "done" looks like

- The ticket's examples pass as tests.
- The edge cases are either handled and tested, or explicitly out of scope.
- The diff reads like the surrounding code.
- Someone skimming the codebase next month couldn't tell which feature was added last.
