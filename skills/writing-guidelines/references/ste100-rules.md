# ASD-STE100 Issue 9 - Writing Rules Summary

Full 53-rule summary of ASD-STE100 Issue 9 (January 2025), the aerospace controlled-language
standard. Adapted from the MIT-licensed summary in
[cfcosta/writing-styles](https://github.com/cfcosta/writing-styles/blob/main/asd-ste100/references/writing-rules.md),
which is itself a summary of the official spec. The official spec is free to request but not
free to redistribute, so this file carries the rules, not the dictionary.

The skill uses these rules in two modes (see the STE section of SKILL.md): **STE-flavored**
applies the structural rules to prose. **Strict** applies all of them to procedures, tool
descriptions, and error messages. Dictionary-dependent rules are marked [dict] - apply the
principle (plain, common word, same word for the same thing) rather than a word-list check.

## Section 1 - Words

- 1.1 [dict]: Use approved dictionary words, technical nouns, or technical verbs only.
- 1.2 [dict]: Use approved words only as their specified part of speech.
- 1.3 [dict]: Use approved words only with their approved meanings (example: `follow` only
  as "come after, go after").
- 1.4 [dict]: Use only dictionary-approved verb and adjective forms.
- 1.5 [dict]: Technical nouns must fit one of 22 categories (parts, tools, materials, colors,
  damage terms, law, and so on). No comparatives or superlatives of colors.
- 1.6 [dict]: Unapproved words are allowed only as or within technical nouns.
- 1.7: Never use a technical noun as a verb (`contact the database`, not `database the
  records`).
- 1.8 [dict]: Use technical nouns approved in your company or subject field.
- 1.9: Keep new technical nouns to 3 words or fewer, and easy to understand.
- 1.10: No regional, slang, or jargon words as technical nouns.
- 1.11: One technical noun per item - no synonyms for the same item.
- 1.12 [dict]: Technical verbs must fit one of 4 categories (manufacturing processes,
  computer processes, subject-field operations, law and regulations). Prefer dictionary
  verbs first.
- 1.13: Never use a technical verb as a noun (past-participle adjectives are the exception).
- 1.14: American English spelling (Merriam-Webster), except in quoted text.

## Section 2 - Multi-word nouns

- 2.1: Multi-word nouns max 3 words. Use prepositions to shorten longer ones.
- 2.2: For a longer technical noun, write it in full first, then use a shorter form or
  hyphens. Hyphenated words count as one word.

## Section 3 - Verbs

- 3.1 [dict]: Use only dictionary-listed verb forms.
- 3.2: Use only these verb forms: infinitive, imperative, simple present, simple past,
  simple future, past participle as adjective. No present perfect, no past perfect, no
  progressive (-ing) forms.
- 3.3: Use the past participle as an adjective (state of condition, not passive voice):
  `the log is empty`.
- 3.4: No auxiliary verbs that create complex constructions or passive.
- 3.5: -ing forms only as technical nouns or inside technical nouns.
- 3.6: Active voice required. Passive is allowed in descriptive writing only when the actor
  is unknown.
- 3.7: Use a verb for actions, not a noun form (`analyze the log`, not `perform an analysis
  of the log`).

## Section 4 - Sentences

- 4.1: Short, clear sentences. One topic per descriptive sentence. Imperative for
  procedures.
- 4.2: No omitted words, no contractions (`do not`, not `don't`).
- 4.3: Use a vertical list for complex text. Colon lead-in, items at the same level, period
  only after full sentences and after the last item.
- 4.4: Use approved connecting words: and, but, then, thus, as a result.
- 4.5: Use an article or demonstrative adjective before a noun. Exceptions: general
  statements and alphanumeric identifiers.

## Section 5 - Procedural writing

- 5.1: Max 20 words per procedural sentence. This includes warnings and cautions. Notes max
  25.
- 5.2: One instruction per sentence, unless the actions must happen at the same time.
- 5.3: Imperative form. `must` goes before an imperative only for critical safety.
- 5.4: Condition first, then command, separated by a comma.
- 5.5: A note gives information only - no instructions, limits, or safety content. The
  procedure must still work if you remove the note.

## Section 6 - Descriptive writing

- 6.1: Give information gradually, one subject per sentence.
- 6.2: Keep key words and phrases the same throughout the text.
- 6.3: Max 25 words per descriptive sentence.
- 6.4: Start each paragraph with a topic sentence.
- 6.5: One topic per paragraph.
- 6.6: Max 6 sentences per paragraph.

The imperative is not permitted in descriptive writing.

## Section 7 - Safety instructions

- 7.1: Label the risk level. `Warning` = risk of injury or death. `Caution` = risk of
  equipment damage. If both, use `Warning`.
- 7.2: Start with a clear command or condition.
- 7.3: State the possible result if the reader ignores the instruction.

## Section 8 - Punctuation and word count

- 8.1: Standard punctuation except the semicolon. Write two sentences instead. STE bans the
  semicolon as a mark, not only as a clause join.
- 8.2: Hyphens for 5 uses: multi-word adjectives, fractions, letter or number + noun,
  compound verbs, vowel-prefix joins.
- 8.3: Parentheses for 7 uses: references, item IDs, work steps, abbreviations,
  singular/plural, explanations, alternatives.
- 8.4: A colon ends a sentence for word-count purposes. Each list item counts as a new
  sentence (the 20/25-word limits apply per item).
- 8.5: Parenthetical text counts as one word in the sentence, and separately as its own
  sentence.
- 8.6: Count each of these as one word: numbers, numbers with units, abbreviations,
  alphanumeric identifiers, quoted text, titles, labels, placards, proper nouns.
- 8.7: Hyphenated words count as one word.

## Section 9 - Writing practices

- 9.1: If word-for-word replacement fails, use a different sentence construction.
- 9.2: Use approved words correctly, per their approved meaning.
- 9.3: No phrasal verbs (only a few are approved, with restricted meanings).
- 9.4: Consistent terminology and wording throughout. Never alternate between two correct
  variants.

## General recommendations (not rules)

- GR-1: Use `that` after verbs like `make sure`.
- GR-2: Be careful with an ambiguous `with`.
- GR-3: Use approved pronouns only. Avoid ambiguous ones.
- GR-4: Clarify `this` (`this rule`, not `this`).
- GR-5: Beware false friends for non-native readers.
- GR-6: No Latin abbreviations (e.g., i.e., etc.).
- GR-8: Use possessives correctly, or not at all.

## Quick reference

| Limit | Procedures | Descriptive |
|---|---|---|
| Sentence words | 20 (5.1) | 25 (6.3) |
| Note sentences | 25 (5.1) | 25 (6.3) |
| Sentences per paragraph | - | max 6 (6.6) |
| Voice | imperative (5.3) | active, passive only if actor unknown (3.6) |
| Noun clusters | max 3 words (2.1) | max 3 words (2.1) |

## Standard verb pairs

SKILL.md's "one action, one verb" rule with concrete defaults. The dictionary rulings
below come from the parsed Issue 9 dictionary (see Provenance) and correct an earlier
version of this table that was adapted from the
[starise ASD-STE100 gist](https://gist.github.com/starise/470f53dbd16149dcd168fa45bff17d1f):

| Write | Not (dictionary status) |
|---|---|
| make sure that (a state), examine (look for faults), measure (get a value), do a check of (the noun) | check, verify, confirm, ensure - all rejected as verbs |
| operate | run, execute - both rejected |
| show | display, render, present - all rejected as verbs |
| start | initiate, launch - not in the dictionary (legal as technical verbs) |
| use | utilize, leverage, employ |
| need | require, necessitate |
| validate | legal in computer contexts as a technical verb (Rule 1.12). Not a dictionary verb. |
| delete | legal in computer contexts as a technical verb (Rule 1.12). `erase` (data) and `remove` (physical) are the dictionary verbs. |
| drop, destroy | rejected - use `erase`/`remove`/`delete` |

Defaults, not a lockdown: a domain meaning overrides a pair (`measure a value` is its
own operation).

## Approved verbs (Issue 9 quick-reference list)

The 207 approved verbs from the dictionary introduction. A verb not on this list is
either a technical verb (Rule 1.12 - legal in a defined technical field) or unapproved:

ABSORB, ACCEPT, ACTIVATE, ADAPT, ADD, ADJUST, AGREE, ALIGN, APPLY, ARM, ASSEMBLE,
ATTACH, BALANCE, BE, BECOME, BEND, BLEED, BLOW, BOND, BREAK, BREATHE, BURN, BYPASS,
CALCULATE, CALIBRATE, CAN, CANCEL, CANNOT, CATCH, CAUSE, CHANGE, CHARGE, CLEAN, CLOSE,
COLLECT, COME, COME ON, COMPARE, COMPLETE, COMPRESS, CONNECT, CONTACT, CONTAIN,
CONTINUE, CONTROL, CORRECT, COUNT, CUT, DEACTIVATE, DECREASE, DEFLATE, DEFUEL, DEPLOY,
DISARM, DISASSEMBLE, DISCARD, DISCONNECT, DISENGAGE, DIVIDE, DO, DRAIN, DRINK, DRY,
EAT, EJECT, ENERGIZE, ENGAGE, ERASE, EXAMINE, EXPAND, EXTEND, EXTINGUISH, FALL,
FEATHER, FEEL, FILL, FIND, FIRE, FLASH, FLOW, FLUSH, FOLD, FOLLOW, FREEZE, GET, GIVE,
GO, GO OFF, GROUND, HANG, HAVE, HEAR, HELP, HIT, HOLD, IDENTIFY, IGNORE, ILLUMINATE,
INCLUDE, INCREASE, INFLATE, INSTALL, INTERCHANGE, ISOLATE, KEEP, KILL, KNOW, LATCH,
LET, LIFT, LISTEN, LOCK, LOOK, LOOSEN, LOWER, LUBRICATE, MAKE, MAKE SURE, MEASURE,
MELT, MIX, MONITOR, MOOR, MOVE, MULTIPLY, MUST, OBEY, OCCUR, OPEN, OPERATE, OVERRIDE,
PAINT, PARK, POINT, POLISH, PREPARE, PRESSURIZE, PREVENT, PROTRUDE, PULL, PUSH, PUT,
PUT ON, READ, RECEIVE, RECOMMEND, RECORD, RECYCLE, REFER, REFUEL, REJECT, RELEASE,
REMOVE, REPAIR, REPLACE, RETRACT, RUB, SAFETY, SCHEDULE, SEAL, SEE, SELECT, SEND,
SENSE, SET, SHAKE, SHOW, SIMULATE, SMELL, SMOKE, SOAK, SPEAK, SPILL, SPRAY, START,
STAY, STOP, STOW, SUBTRACT, SUPPLY, SWALLOW, TAG, TAP, TELL, THINK, TIGHTEN, TILT,
TORQUE, TOUCH, TOW, TRANSMIT, TRY, TUNE, TURN, TWIST, UNFOLD, UNLOCK, UNWIND, USE,
WAIT, WALK, WANT, WEAR, WEIGH, WILL, WIND, WRITE

## Software rulings

Part-of-speech rulings the dictionary makes on words software writing hits, from the
parsed dictionary and the community-audited summary in
[AminBlg/SimpleEnglish](https://github.com/AminBlg/SimpleEnglish):

- `test`, `check`, `work` - noun only. `Do a test`, `do a check of`. `Check that X`
  becomes `make sure that X`.
- `help` - verb only. The noun is `aid`: `with the aid of`.
- `follow` - "come after" only, never "obey". `Obey the instructions`.
- `above`, `below` - physical positions only. For limits write `more than`, `less than`.
- `failure` - approved only as a technical noun for performance loss. `problem` and
  `error` are the approved general nouns.
- `issue` - not in the dictionary. Use `problem`, or keep `issue` as a technical noun.
- A technical noun is never a verb (`contact the database`, not `database the records`),
  and a technical verb is never a noun.

## Provenance

- Adapted from the MIT-licensed summary at
  [cfcosta/writing-styles](https://github.com/cfcosta/writing-styles/blob/main/asd-ste100/references/writing-rules.md).
- Official standard: [asd-ste100.org](https://www.asd-ste100.org/). Issue 9 retains 53 rules,
  revises 31 of them, and updates 555 dictionary entries
  ([ASD release note](https://www.asd-europe.org/news-media/news-events/news/simplified-technical-english-asd-ste100-issue-9/)).
- The skill also borrows the mode split (Strict vs STE-flavored) and the structural/lexical
  rule division from [danyuchn/asd-ste100-skill](https://github.com/danyuchn/asd-ste100-skill)
  (MIT). That skill additionally ships a stdlib-only linter, `scripts/ste-lint.py`, for a
  mechanical first pass over the structural rules.
- The verb rulings and the approved-verb list were parsed from the official Issue 9 PDF
  (Andrei's own copy - the extraction script and `dict.json` stay local, since ASD's
  license forbids redistribution of dictionary content). The parser lives in
  `~/tmp/simpleenglish/parse_dict.py`. The same rulings were cross-checked against the
  community-audited [AminBlg/SimpleEnglish](https://github.com/AminBlg/SimpleEnglish)
  strict-vocabulary tables (MIT). To re-extract after a dictionary update:
  `pdftotext`-equivalent via pdfminer into a flat dump, then `parse_dict.py` - the
  parser expects the dictionary body pages 148-433 (0-indexed) of the Issue 9 PDF.
