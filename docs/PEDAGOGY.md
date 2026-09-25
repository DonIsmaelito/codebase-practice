# How Cold Start teaches

You asked for a gym that makes you *fast* in any codebase and turns Python into a
tool you've mastered — not a language you've studied. Those are skills, not facts,
and skills are built differently from knowledge. This document is the reasoning
behind every design choice, and — more usefully — how to practice so it works.

## What expertise actually is

Research on expert programmers (and chess players, radiologists, pilots) keeps
finding the same thing: experts don't think faster, they **recognize more**. They
have a huge library of *chunks* — "that's an accumulator loop," "that's a retry
wrapper," "that default argument is a list" — so they read code in whole phrases
while a novice reads it word by word. They also have *strategies* for where to look
first, and they *externalize* (notes, sketches, tests) instead of juggling
everything in working memory.

So the gym is built to do three things:

1. **Grow your chunk library** across as many realistic contexts as possible.
2. **Train the strategies** (orienting, hypothesizing, tracing, verifying) explicitly.
3. **Make every rep produce a transferable lesson**, not just a solved puzzle.

## The mechanics, and why

**Every codebase is new territory (variability of practice).** The same concept —
shared mutable state, say — shows up as a leaking shopping cart in one client and a
duplicate-job bug in a code judge in another. Seeing one idea in many surface forms is
what lets you recognize it in a form you've never seen. Drilling one context makes you
good at that context; varying the context makes you good at the *idea*.

**You don't know which concept the bug is about (interleaving).** Textbooks tell you
the chapter; real bugs don't. The scheduler mixes concepts and regions so that part of
every incident is *discriminating* which idea applies. That discrimination is the
actual skill, and blocked practice never trains it.

**Concepts come back just as you're about to forget them (spacing).** Each concept
has an interval that grows when you solve it cleanly and resets when you don't. A due
concept returns in a *different* domain. The quick-recall cards on the Desk do the
same for your own journal lessons.

**Recon before the incident (building the map first).** Understanding compounds: the
minutes you spend orienting pay for themselves during the incident, and knowing *that*
is half of getting fast. Early on you get a guided tour (a worked example of how an
expert reads a repo); it fades to an optional hint, then to closed-book scouting where
the code hides while you answer. Answering from memory is retrieval practice — the
single most reliable way to make knowledge durable — and it forces you to read with
intent instead of scrolling.

**Write a hypothesis before digging (prediction).** A guess you commit to turns
reading into testing. When you're wrong, you learn *why* you were wrong, which is worth
more than being right by luck. The debrief shows your hypothesis next to the truth.

**Explain the root cause before the reveal (the generation effect).** Putting the
cause into your own words — even imperfectly — is what converts "I made the tests
pass" into "I'll recognize this next time." The grader pushes for precision, not
polish.

**Your path vs. an expert's path (metacognition).** The debrief replays what you
actually did — files opened, searches, test runs, hints — next to how an expert would
have gone from report to root cause. Watching where *your* time went is the fastest way
to change how you investigate. You also get exactly one habit to try next time. One,
because one gets done.

**"You've met this before" (analogical encoding).** When a concept recurs, the
debrief puts the earlier case next to the new one. Comparing two instances is how the
underlying schema gets extracted; either case alone stays stuck to its details.

**Feature tickets with a real PR review (writing, not just reading).** Reading makes
you fast; writing makes you fluent. The review is where idioms, data-structure
choices, complexity, and conventions get taught — on *your* code, which is the only
code you'll remember.

**Hints are a ladder, the mentor is Socratic.** Productive struggle is where learning
happens; unproductive struggle is where people quit. Hints go nudge → area → exact
spot → mechanism, so you only take as much as you need. The mentor knows the answer
but will make you find it — unless you explicitly ask it to stop.

**Difficulty adapts (desirable difficulty).** Codebase size, how far the symptom is
from the cause, how honest the bug report is (failing test → traceback → customer
complaint → a thread with a confidently wrong theory), and recon mode all scale with
you. The target is "probably, not certainly": if you're breezing through, it gets
harder; if you're drowning, it backs off.

**No points (on purpose).** Extrinsic scores tend to crowd out the intrinsic
motivation that makes practice sustainable, and they reward gaming over learning.
What you see instead is real: the atlas only lights up when you've *demonstrated* a
concept in a codebase, the progress charts are your actual times, and the journal is
what you actually learned.

## How to practice (the protocol)

This is what I'd tell you as your coach:

1. **Show up briefly, often.** Three 30-minute sessions a week beat one 3-hour
   session. Spacing works on *you*, too — the calendar is there to help you notice
   your rhythm, not to guilt you.
2. **Recon with a question, not a scroll.** "Where does a request enter? What are the
   core data types? What happens when X?" Take notes in the Notes tab — it's working
   memory you don't have to hold.
3. **Always write the hypothesis**, even a bad one. Then name what would confirm or
   kill it, and go check *that* first.
4. **Reproduce before you fix.** Run the failing test, or reproduce the report in the
   terminal (`python -i`, a tiny script). A fix you can't demonstrate is a guess.
5. **Stay stuck for a few minutes before taking a hint.** The discomfort is the part
   that's working. If you've made no progress in ~5 minutes, take *one* hint and go
   again. Ask the mentor about concepts freely — that's teaching, not cheating.
6. **Fix the cause, not the symptom.** Then ask: "where else could this same mistake
   live in this codebase?" (The debrief will ask you anyway.)
7. **Take the debrief seriously.** Read the expert path against your timeline. Edit
   the journal lesson until it's something *you* would say. That sentence is what
   comes back in quick-recall.
8. **Do the quick-recall card** when it shows up on the Desk. Ten seconds of retrieval
   beats ten minutes of re-reading.
9. **Stay late for the feature ticket once or twice a week.** Reading is half the job;
   the PR review is where your writing gets better.
10. **Read the Playbook once, early** — then re-read an article when a debrief's
    "next time" habit points at it.

## What gets harder over time

| You'll see | Early | Later |
|---|---|---|
| Codebase size | 4–6 modules, ~400 lines | 20+ modules, 3–4k lines |
| The report | a failing CI test, a traceback | a vague customer complaint; a thread with a wrong theory |
| Symptom → cause | same function | several calls and modules apart |
| Recon | guided tour, open book | closed-book scouting |
| Concepts | core Python semantics, basic stdlib & DS | concurrency, async, systems patterns, ORMs, pandas/numpy, algorithms in context |

The atlas has ten regions and 157 concepts — Python core, the data model, the
standard library, data structures, algorithms, concurrency & async, data &
persistence, systems & scale, engineering practice, and the library ecosystem. You
won't "finish" it; you'll watch it fill in.
