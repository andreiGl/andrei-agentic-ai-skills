# Writing Guidelines

How the result reads. Any prose, any language, any reader - whether it ships alongside
code or stands on its own.

## What it does

Invoked whenever there is prose to draft or edit: code comments, docstrings, READMEs,
docs, commit messages, PR and issue text, design notes, reports, analyses, research
summaries, essays, emails, forum and social posts, chat replies.

1. **Write for a human reader** - plain language, no invented terms (headings included), clarity over brevity
2. **Match the register** - who reads it, where it appears, what they do next; length follows the venue, not the effort; text going out under someone else's name takes their voice
3. **Cut the AI tells** - throat-clearing, binary contrast, rhetorical setup, meta-commentary, vague declaratives, hidden actors
4. **Simplified Technical English (ASD-STE100)** - sentence discipline from the aerospace controlled-language standard: one instruction per sentence, 20/25-word caps, active voice, simple tenses, no semicolons, no phrasal verbs or nominalizations, one term per thing. Two modes: STE-flavored for prose, Strict for procedures and error messages
5. **Other languages** - the word lists are English; the structural tells carry across unchanged
6. **Corrections** - first sentence, one clause, no apology

Load it before drafting. Writing this way costs less than stripping the tells out
afterwards.

## Two deliberate softenings

**Binary contrast has an exception.** "Not X, but Y" is padding when nobody claimed X,
and is the actual content when you are correcting someone who did. The rule says so
rather than banning the shape outright, because a blanket ban strips the point out of
any rebuttal.

**Part-of-speech bans stay out.** Adverbs, three-item lists, and Wh- openers are not
tells. Banning them comes from essay style guides and rewrites prose that was already
fine.

Em dashes are the exception to that exception. The skill does replace them with a spaced
hyphen, because the em dash now reads as a machine's default punctuation. That is a
punctuation call, not a part-of-speech ban, and `MAINTENANCE.md` carries a sweep that
enforces it.

## STE provenance

The ASD-STE100 section encodes the structural rules of the standard and paraphrased
dictionary rulings, not the dictionary itself. The official dictionary (~900 approved
words) is free to request but not free to redistribute, so no dictionary data ships in
the repo (`references/ste100-rules.md` carries the ruling tables and their provenance).

- Rules summary adapted from
  [cfcosta/writing-styles](https://github.com/cfcosta/writing-styles/blob/main/asd-ste100/references/writing-rules.md)
  (MIT)
- Verb rulings and the approved-verb list parsed from the official Issue 9 PDF (Andrei's
  own copy - the extraction script and any dictionary data stay local, since ASD's
  license forbids redistribution)
- Mode split (Strict vs STE-flavored) and the structural/lexical rule division from
  [danyuchn/asd-ste100-skill](https://github.com/danyuchn/asd-ste100-skill) (MIT)
- Official standard: [asd-ste100.org](https://www.asd-ste100.org/) - Issue 9, 53 rules in
  9 sections
