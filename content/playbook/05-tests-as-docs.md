---
slug: tests-as-docs
title: Reading tests as executable documentation
summary: Tests tell you what the system is supposed to do, how to build it, and — by what's missing — where bugs are likely to hide.
order: 5
---

# Reading tests as executable documentation

Documentation drifts out of date. Tests can't — if they did, they'd fail. That makes the test suite the most trustworthy description of a codebase you'll find, and it's usually the most underused.

## Test names are a spec

Start by listing every test without running anything:

```bash
pytest --collect-only -q
```

```text
tests/test_holds.py::test_hold_expires_after_ten_minutes
tests/test_holds.py::test_confirming_expired_hold_raises
tests/test_holds.py::test_hold_releases_seats_on_expiry
tests/test_pricing.py::test_child_fare_is_half_adult
tests/test_pricing.py::test_vehicle_fare_by_length_band[4.9-standard]
tests/test_pricing.py::test_vehicle_fare_by_length_band[5.0-long]
```

In thirty seconds you've learned that seat holds expire after ten minutes, that confirming an expired hold is an error, that child fares are half price, and that 5.0 meters is exactly where the "long vehicle" band begins. That last one is an edge case the team clearly cared about — and a great place to look if a ticket mentions vehicle fares.

## Fixtures show you how the system is wired

`conftest.py` and fixtures answer a question that's hard to answer from the application code alone: **how do I construct this thing?**

```python
# tests/conftest.py
@pytest.fixture
def clock():
    return FakeClock(datetime(2025, 6, 1, 9, 0, tzinfo=UTC))

@pytest.fixture
def service(clock, tmp_path):
    repo = SqliteBookingRepo(tmp_path / "bookings.db")
    return BookingService(repo=repo, clock=clock, notifier=RecordingNotifier())
```

This tells you:

- `BookingService` depends on a repository, a clock and a notifier — those are its seams.
- Time is injected, so the service never calls `datetime.now()` directly (or isn't supposed to).
- There's a fake notifier that records messages, which you can use to check notifications in your own tests.

When you need to reproduce a bug, copying a fixture setup is often the fastest route to a working repro.

## Read each test as Arrange → Act → Assert

```python
def test_confirming_expired_hold_raises(service, clock):
    hold = service.hold_seats("HL-0915", seats=2)        # arrange
    clock.advance(minutes=11)
    with pytest.raises(HoldExpired):                     # act + assert
        service.confirm(hold.id)
```

- **Arrange** shows valid inputs and the setup a real call needs.
- **Act** is the public API you're supposed to use.
- **Assert** is the contract — the behavior that must not change.

If you're about to modify `confirm()`, this test is the fence you mustn't knock down.

## What's *not* tested is where bugs hide

Once you know what's covered, look for the gaps. Common untested territory:

- **Zero and empty:** zero quantity, empty cart, no passengers, an empty file
- **Boundaries:** exactly at a limit, the last item, the first day of the month, midnight
- **Time:** time zones, daylight-saving changes, month-end, leap years
- **Repetition:** calling something twice, retries, duplicate events
- **Concurrency:** two requests at once
- **Bad input:** missing fields, wrong types, stray whitespace, non-ASCII text

A bug report about "sometimes wrong" behavior very often lands in one of these gaps. If `pricing.py` has twelve tests but `storage.py` has none, the storage layer deserves suspicion.

## Write the failing test first

When you pick up a bug, turn the report into a test *before* you fix anything:

```python
def test_cancel_after_departure_gives_no_refund(service, clock):
    booking = service.book("HL-0915", passengers=1)
    clock.set(departure_of("HL-0915") + timedelta(minutes=5))
    refund = service.cancel(booking.id)
    assert refund.amount == Decimal("0.00")
```

This does three jobs at once:

1. **It proves you understood the report** — if you can't write the test, you don't understand the bug yet.
2. **It gives you a fast feedback loop** — `pytest -k cancel_after_departure` runs in a second.
3. **It becomes the regression test** — the bug can't quietly come back.

The same goes for features: write an acceptance test from the ticket's examples first, watch it fail, then make it pass.

## Tests can be wrong too

Tests are strong evidence, not scripture. Watch out for:

- **Tests that assert nothing meaningful:** `assert result` passes for any non-empty result.
- **Expected values copied from the buggy output:** the test "locks in" the bug.
- **Tests that pass alone but fail together** (or the reverse) — shared state between tests.
- **Mocks that don't behave like the real thing** — the test proves the mock works, not the code.

When a test and the ticket disagree, figure out which one reflects the real requirement before you "fix" either.

## The habit

Before diving into application code, spend two minutes in the tests: list them, open `conftest.py`, and read the tests nearest your ticket. You'll know the intended behavior, how to build the system, and where the thin ice is — before you've read a line of the implementation.
