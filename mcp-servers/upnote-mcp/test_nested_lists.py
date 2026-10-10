#!/usr/bin/env python3
"""Checks for rewriting nested Markdown lists as UpNote's list HTML, on synthetic text.

Touches neither UpNote nor your notes: it calls the conversion functions directly.
Exits non-zero if any check fails.
"""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("upnote_server", Path(__file__).resolve().with_name("server.py"))
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)

fails = 0
def check(name, ok, detail=""):
    global fails
    fails += 0 if ok else 1
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))

def same(name, source, expected):
    got = srv._nested_lists_to_html(source)
    check(name, got == expected, repr(got))

def unchanged(name, source):
    same(name, source, source)

# 1. the shape UpNote's editor uses: a nested list sits beside its parent item
same("two-space nesting", "- a\n  - b\n- c", "<ul><li>a</li><ul><li>b</li></ul><li>c</li></ul>")
same("four-space nesting", "- a\n    - b\n- c", "<ul><li>a</li><ul><li>b</li></ul><li>c</li></ul>")
same("tab nesting", "- a\n\t- b\n- c", "<ul><li>a</li><ul><li>b</li></ul><li>c</li></ul>")
same("three levels, back to the second",
     "- a\n  - b\n    - c\n  - d\n- e",
     "<ul><li>a</li><ul><li>b</li><ul><li>c</li></ul><li>d</li></ul><li>e</li></ul>")
same("nested list in last place", "- a\n- b\n  - c", "<ul><li>a</li><li>b</li><ul><li>c</li></ul></ul>")
same("numbered parent with bullets", "1. a\n   - b\n2. c", "<ol><li>a</li><ul><li>b</li></ul><li>c</li></ol>")
same("a one-space indent is a sibling, not a child", "- a\n - b\n   - c",
     "<ul><li>a</li><li>b</li><ul><li>c</li></ul></ul>")
same("loose list", "- a\n\n  - b\n\n- c", "<ul><li>a</li><ul><li>b</li></ul><li>c</li></ul>")
same("continuation line joins its item", "- a\n  more of a\n  - b", "<ul><li>a more of a</li><ul><li>b</li></ul></ul>")
same("switching marker type starts a new list", "- a\n  - b\n1. c",
     "<ul><li>a</li><ul><li>b</li></ul></ul><ol><li>c</li></ol>")

# 2. checkboxes
same("checkboxes", "- [ ] open\n  - [x] done\n  - [X] also done",
     '<ul><li data-checked="false">open</li><ul><li data-checked="true">done</li><li data-checked="true">also done</li></ul></ul>')

# 3. inline formatting, as UpNote writes it
def item(md):
    return srv._nested_lists_to_html(f"- {md}\n  - x").removeprefix("<ul><li>").removesuffix("</li><ul><li>x</li></ul></ul>")
check("bold, italic, bold-italic", item("**b** *i* ***➡ In Review*** __b2__ _i2_") ==
      "<b>b</b> <i>i</i> <b><i>➡ In Review</i></b> <b>b2</b> <i>i2</i>", item("**b** *i* ***➡ In Review*** __b2__ _i2_"))
check("code keeps its content literal", item("`a **b** <c>`") == "<code>a **b** &lt;c&gt;</code>", item("`a **b** <c>`"))
check("strikethrough and green highlight", item("~~old~~ ==new==") == '<s>old</s> <span class="shine-highlight">new</span>',
      item("~~old~~ ==new=="))
check("link with formatted text", item("[**KEY-1**](https://t/browse/KEY-1) x") ==
      '<a href="https://t/browse/KEY-1"><b>KEY-1</b></a> x', item("[**KEY-1**](https://t/browse/KEY-1) x"))
check("link with brackets in the url", item("[w](https://e.org/a_(b))") == '<a href="https://e.org/a_(b)">w</a>',
      item("[w](https://e.org/a_(b))"))
check("bare url becomes a link, without the full stop", item("see https://e.org/x?a=1&b=2.") ==
      'see <a href="https://e.org/x?a=1&amp;b=2">https://e.org/x?a=1&amp;b=2</a>.', item("see https://e.org/x?a=1&b=2."))
W = "https://en.wikipedia.org/wiki/Python_(programming_language)"
check("bare url keeps a bracket that belongs to it", item(f"see {W} now") == f'see <a href="{W}">{W}</a> now', item(f"see {W} now"))
check("  and still drops the full stop after it", item(f"see {W}.") == f'see <a href="{W}">{W}</a>.', item(f"see {W}."))
check("  a bracket around the whole url stays outside", item("(see https://e.org/x)") ==
      '(see <a href="https://e.org/x">https://e.org/x</a>)', item("(see https://e.org/x)"))
check("  so does a bracket closing outside a bracketed url", item(f"({W})") == f'(<a href="{W}">{W}</a>)', item(f"({W})"))
check("  a scheme with nothing after it stays text", item("https:// alone") == "https:// alone", item("https:// alone"))
check("raw inline HTML is kept", item('<u>Group</u> <span class="shine-highlight-yellow">blocked</span>') ==
      '<u>Group</u> <span class="shine-highlight-yellow">blocked</span>',
      item('<u>Group</u> <span class="shine-highlight-yellow">blocked</span>'))
check("a stray < and & are escaped, an entity is kept", item("a < b & c &amp; d") == "a &lt; b &amp; c &amp; d",
      item("a < b & c &amp; d"))
check("backslash escapes stay literal", item(r"\*not italic\* and snake\_case") == "*not italic* and snake_case",
      item(r"\*not italic\* and snake\_case"))
check("underscores inside words stay", item("snake_case_name") == "snake_case_name", item("snake_case_name"))

# 4. left alone
unchanged("a flat list stays Markdown", "- a\n- b\n\n1. x\n2. y")
unchanged("a list in a fenced code block", "```yaml\n- a\n  - b\n```")
unchanged("a list in an HTML block", "<div>\n- a\n  - b\n</div>")
unchanged("a list in a <pre> that spans a blank line", "<div><pre>x:\n\n- a\n  - b\n</pre></div>")
unchanged("an item holding a code block", "- a\n  ```\n  code\n  ```\n  - b")
unchanged("an item holding a quote", "- a\n  > quoted\n  - b")
unchanged("indented four or more is not a list", "    - a\n      - b")

# 5. surroundings
same("text around the list keeps its place",
     "### Heading\n\nIntro\n\n- a\n  - b\n\nAfter",
     "### Heading\n\nIntro\n\n<ul><li>a</li><ul><li>b</li></ul></ul>\n\nAfter")
same("an unindented line right after an item joins it, as in CommonMark", "- a\n  - b\nlazy",
     "<ul><li>a</li><ul><li>b lazy</li></ul></ul>")
same("two separate lists", "- a\n  - b\n\ntext\n\n- c\n  - d",
     "<ul><li>a</li><ul><li>b</li></ul></ul>\n\ntext\n\n<ul><li>c</li><ul><li>d</li></ul></ul>")
same("a heading right after a list ends it", "- a\n  - b\n### Next",
     "<ul><li>a</li><ul><li>b</li></ul></ul>\n\n### Next")
check("the create link carries the HTML", "%3Cul%3E%3Cli%3Ea%3C%2Fli%3E%3Cul%3E" in srv._create_url("t", "- a\n  - b", None, True))
check("with markdown off the text is sent as given", "-%20a%0A%20%20-%20b" in srv._create_url("t", "- a\n  - b", None, False))

print("FAILURES:", fails)
sys.exit(1 if fails else 0)
