---
name: writing-guidelines
description: Write prose a person will actually read - plain language, no invented terms, register matched to the venue, and none of the sentence shapes that mark text as machine-written. Use whenever drafting or editing prose in any language for any audience — code comments, docstrings, READMEs, docs, commit messages, PR and issue text, design notes, reports, analyses, research summaries, essays, emails, forum and social posts, and chat replies. Load it before drafting, not after - it is cheaper to write this way than to strip the tells out afterwards.
---

# Writing Guidelines

How the result reads. Applies to any prose, in any language, for any reader - whether it
ships alongside code or stands on its own.

For how to carry out the underlying task, see the **behavioral-guidelines** skill.

## 1. Write for a Human Reader

**Code comments, docstrings, commit messages, PR and issue text, plans, reports,
analyses, posts, emails, and chat replies should all read as if one person wrote them
for another to read.**

- Plain language. If a common word says the same thing, use the common word, and use no
  jargon beyond what this particular reader already knows.
- No invented terms. Don't coin a phrase to compress an idea - state the idea. If a
  domain term is genuinely unavoidable, say what it refers to in the same sentence.
  Section headings count: a heading you just made up costs the reader a decoding step
  before they reach the content under it.
- Clarity outranks brevity. Where another rule says be terse, it means cut what the
  reader doesn't need - never make what remains harder to follow. Don't compress until it
  turns cryptic; don't pad to sound thorough.

Usually padding, so reach for the plain word first: leverage, orthogonal, holistic,
non-trivial, deep dive, circle back, double down, lean into, moving forward, navigate (a
problem), unpack (an idea). Ban outright: any noun phrase you just coined.

```
Bad:  // Guards the freshness envelope against stale-read contract violations.
Good: // Rejects the entry if it was read before the last write, returning stale data.
```

Applies to text you write or change - not a license to rewrite text you're only reading
past (see *Surgical changes* in behavioral-guidelines).

Test: would a colleague understand this on first read, without asking what a word means?

## 2. Match the Register

**A forum reply, a board memo, a code comment, and a research note are different kinds of
writing. Text in the wrong register reads as written by someone who wasn't there.**

Before drafting, settle three things: who reads this, where it appears, and what they do
after reading it. A commit message is read by someone bisecting a regression at 2am. A
forum reply is read by people already mid-argument who will scroll past anything that
looks like homework.

Signs you've drifted:
- A reply that reads as an essay *about* the conversation rather than a turn *in* it.
- Headings and a table of contents on something the reader will consume in one scroll.
- A commit message with a thesis, or a chat answer with an abstract.
- Structure that took longer to build than the reader will spend on it.

Length follows the venue, not the effort you put in. Research that took twenty sources
can land as four sentences, and usually should.

## 3. Cut the AI Tells

**A handful of sentence shapes mark text as machine-written. They carry no information,
so they read as padding to a colleague and as filler to you a month later.**

- **Throat-clearing openers.** "Here's the thing," "It turns out," "The truth is,"
  "Let me be clear." Cut them and state the point.
- **Binary contrast.** "It's not X, it's Y," "The problem isn't X. It's Y," "not just X
  but Y." State Y and drop the negation.
  *Exception:* keep the negation where it names a claim you are actually correcting and
  the reader needs to see which claim. "That figure is damage valuation, not a tax"
  answers someone who called it a tax. Cut it where nobody claimed X - there it's
  decoration. Correcting a record, expect to keep a few; describing something, expect to
  keep none.
- **Negative listing.** Saying what a thing isn't before saying what it is. Say what it is.
- **Rhetorical setup.** "What if...?", "Think about it:", "Here's what I mean:". Make the
  point instead of announcing that you're about to.
- **Emphasis crutches.** "Let that sink in," "Make no mistake," "Full stop."
- **Meta-commentary.** "In this section we'll...", "As we'll see...", "Let me walk you
  through," "Now for the interesting part," "Notice what happened here," "And here's
  where it gets interesting." Let the document move.
- **Vague declaratives.** "The implications are significant" names nothing. Name the
  implication, or cut the sentence.
- **Hidden actors.** Passive voice and inanimate subjects both drop the person who acted.
  "The decision was reached" and "the decision emerges" are both "the team decided."

```
Bad:  Here's the thing: it's not a caching problem, it's an invalidation problem.
      The implications are significant.
Good: Invalidation is what breaks here. Two writers can clear the same key in either
      order, and the loser's value survives.
```

Not banned: em dashes, adverbs, three-item lists, and sentences opening with a Wh- word.
Blanket bans on those come from essay style guides, and enforcing them rewrites prose
that was already fine. Cut a word because it carries no information, never because of its
part of speech.

Test: does the sentence survive deleting its first four words? Then those four words were
throat-clearing.

## 4. Other Languages

The word lists above are English. Padding is language-specific, so find the local
equivalents rather than translating this list.

Russian, common ones: «стоит отметить», «важно понимать», «давайте разберёмся»,
«ключевой момент», «здесь кроется», «как мы видим», «не просто X, а Y», «и вот что
интересно».

The structural tells carry across languages unchanged - throat-clearing, rhetorical setup,
meta-commentary, vague declaratives, hidden actors. Check for those in any language; check
the word list only in English.
