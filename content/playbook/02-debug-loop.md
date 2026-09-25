---
slug: debug-loop
title: The debugging loop
summary: Reproduce, locate, explain, fix, prove — debugging is a loop of cheap experiments, not a flash of insight.
order: 2
---

# The debugging loop

Good debuggers aren't magicians who stare at code until the answer appears. They run a boring, reliable loop:

1. **Reproduce** — make the bug happen on demand.
2. **Locate** — narrow down where the wrong thing happens.
3. **Explain** — say *why* it happens, in one sentence.
4. **Fix** — change the cause, minimally.
5. **Prove** — show it's fixed and stays fixed.

Skipping a step is how people lose an afternoon.

## 1. Reproduce

If you can't make the bug happen, you can't know whether you've fixed it. Turn the report into something you can run in seconds:

- a failing test (best — it becomes your regression test later), or
- a tiny script that calls the code with the reported input.

```python
# repro.py — run with: python repro.py
from ledger.accounts import Account
from ledger.transfers import transfer

a, b = Account("alice", 100), Account("bob", 0)
transfer(a, b, 30)
transfer(a, b, 30)
print(a.balance, b.balance)   # report says: bob ends up with 90
```

Shrink the input until it's minimal. Bug reports often contain ten details and only one of them matters; removing details that *don't* matter is itself a clue.

## 2. Locate

Now find where the behavior goes wrong. Two techniques cover most cases.

**Work backwards from the wrong output.** Where was the wrong value last touched? Who computed it? Where did *its* inputs come from? Keep stepping back until you find the first place where a value is wrong even though everything that went into it was right. That spot is the bug.

**Binary search the code path.** If a pipeline has eight steps and the output is wrong, check the value after step four. Correct there? The bug is in steps 5–8. Wrong? Steps 1–4. Three checks narrow eight steps down to one. You can check with a `print`, a log line, an assertion, or a `breakpoint()`.

```python
rows = load(path)
cleaned = clean(rows)
print("after clean:", len(cleaned), cleaned[:3])   # midpoint probe
totals = aggregate(cleaned)
```

Also ask **"what changed?"** Bugs that "started last week" are usually tied to a specific change. Look at recent commits (`git log -p`), config, or new kinds of input data.

## 3. Explain — write the hypothesis down

Before you edit anything, write a sentence:

> I think the second transfer credits bob twice because `transfer()` appends to a pending list that's shared between calls.

Then derive a prediction from it: *if that's true, a brand-new `Account` pair should also see leftover pending entries.* Test that prediction. A hypothesis you've confirmed with a prediction is worth ten you've merely found plausible.

Writing it down matters. Hypotheses held only in your head quietly change shape as you go, and you end up "confirming" something you never actually stated.

If the prediction fails, good — you've eliminated a wrong idea cheaply. Form the next hypothesis.

## 4. Fix

- **Change one thing at a time.** If you change three things and the bug disappears, you don't know which one mattered — or whether the other two broke something else.
- **Fix the cause, not the place where it surfaced.** The crash site is often just where the bad value finally got used. (See *Fix the cause, not the symptom*.)
- **Keep the diff small.** A bug fix that rewrites the module is really a refactor wearing a disguise, and it's much harder to review.

## 5. Prove

A fix isn't done until you can show it:

1. The reproduction now behaves correctly.
2. A **regression test** exists that failed before your fix and passes after it. If you started with a failing test, you already have one.
3. The **whole test suite** still passes — your fix didn't break a neighbor.

```bash
pytest -x -q          # stop at the first failure
```

## When you're stuck

Being stuck means your mental model disagrees with reality somewhere. Find where:

- **Check your assumptions explicitly.** Print the value you're "sure" about. Print its `type()`. Print its `id()` if you suspect aliasing.
- **Read the error message again, slowly.** Word by word. It's usually more specific than it first seemed.
- **Explain it out loud** — to a rubber duck, a colleague or your mentor. Saying "and then this returns the list… oh. It returns the *same* list" is a classic breakthrough.
- **Take the smallest possible next step.** You don't need the whole answer — you need the next experiment.

## Anti-patterns

- **Shotgun debugging** — changing random things until the symptom goes away.
- **Debugging by staring** — reading code for twenty minutes without running anything. Run an experiment instead.
- **Stopping at "it works now"** — without a regression test, it'll be back.

The loop feels slow at first. It's the fastest way there is, because each step removes possibilities instead of adding confusion.
