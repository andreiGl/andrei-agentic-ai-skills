#!/usr/bin/env python3
"""Checks for the collapsible-section structure counts and the replace gate's decisions.

Touches neither UpNote nor your notes: it calls the counting and planning functions directly.
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

def same(name, got, expected):
    check(name, got == expected, f"got {got}")

SECTION_OPEN = '<div class="shine-collapsible-section">'
SECTION_COLLAPSED = '<div class="shine-collapsible-section shine-section-collapsed">'
PLACEHOLDER = '<div class="shine-section-content shine-placeholder" data-upnote-placeholder-key="content"></div>'

# 1. counts
same("wrapper counted in class list", srv._structure('<div class="shine-collapsible-section shine-x">'), {"collapsible_sections": 1, "collapsed_sections": 0, "section_placeholders": 0})
same("collapsed counted", srv._structure('<div class="x shine-collapsible-section shine-section-collapsed">'), {"collapsible_sections": 1, "collapsed_sections": 1, "section_placeholders": 0})
same("placeholder counted", srv._structure(PLACEHOLDER), {"collapsible_sections": 0, "collapsed_sections": 0, "section_placeholders": 1})
same("plain mention not counted", srv._structure("<p>write class=shine-collapsible-section in a sentence</p>"), {"collapsible_sections": 0, "collapsed_sections": 0, "section_placeholders": 0})

# 2. the 11-09 incident shape: old live vs flattened copy, measured from the real trashed notes
old = {"collapsible_sections": 16, "collapsed_sections": 11, "section_placeholders": 32}
flattened = {"collapsible_sections": 1, "collapsed_sections": 1, "section_placeholders": 2}
same("gate refuses progressive flatten", srv._structure_dropped(old, flattened), {"collapsible_sections": 15, "section_placeholders": 30})
one_gone = {**old, "collapsible_sections": 15, "section_placeholders": 30}
same("gate refuses a single lost wrapper", srv._structure_dropped(old, one_gone), {"collapsible_sections": 1, "section_placeholders": 2})
same("gate passes intact rebuild", srv._structure_dropped(old, old), {})
same("gate ignores collapsed-state change", srv._structure_dropped(old, {**old, "collapsed_sections": 0}), {})
same("gate ignores growth", srv._structure_dropped(old, {**old, "collapsible_sections": 17, "section_placeholders": 34}), {})

# 3. _section_html output counts as 1 section, 2 placeholders
built = srv._section_html("T", "<div>x</div>", False)
same("built section counted", srv._structure(built), {"collapsible_sections": 1, "collapsed_sections": 0, "section_placeholders": 2})
same("built collapsed counted", srv._structure(srv._section_html("T", "<div>x</div>", True))["collapsed_sections"], 1)

# 4. _plan_section adds exactly one section to the sent structure
body = SECTION_OPEN + PLACEHOLDER + "<div>inside</div></div>" + "<h3>Next</h3><div>after</div>"
plan = srv._plan_section(body, "Next")
sent = srv._structure(plan["html"])
current = srv._structure(body)
check("plan adds one section", sent["collapsible_sections"] == current["collapsible_sections"] + 1, f"{current} -> {sent}")
check("plan adds two placeholders", sent["section_placeholders"] == current["section_placeholders"] + 2, f"{current} -> {sent}")

# 5. transforms leave the counts unchanged (the gate measures after them)
marked = SECTION_OPEN + PLACEHOLDER + "<div>inside ==hi== $$f$$</div></div>" + "<h3>Next</h3><div>after</div>"
for name, out in [
    ("_nested_lists_to_html", srv._nested_lists_to_html(marked)),
    ("_tighten_html", srv._tighten_html(marked)),
    ("_drop_tags", srv._drop_tags(marked, [])),
    ("_with_tags", srv._with_tags(marked, ["t"])),
    ("sanitize chain", srv._encode_pre_breaks(srv._sanitize_html(srv._MARKER.sub("", srv._nested_lists_to_html(marked))))),
]:
    same(f"{name} keeps counts", srv._structure(out), srv._structure(marked))

# 6. _fragment_html: block constructs of a spliced markdown fragment (home's port-brief table)
def frag(name, src, expected):
    got = srv._encode_pre_breaks(srv._sanitize_html(srv._fragment_html(src)))
    same(name, got, expected)

frag("flat list items share one ul", "- a\n- b", "<ul><li>a</li><li>b</li></ul>")
frag("ordered list becomes ol", "1. one\n2. two", "<ol><li>one</li><li>two</li></ol>")
frag("fence becomes pre with language", "```python\nx = 1\ny = 2\n```", '<pre data-code-language="python">x = 1&#10;y = 2</pre>')
frag("inline HTML passes through", "Text with <b>bold</b> here", "<div>Text with <b>bold</b> here</div>")
frag("blockquote converts", "> quoted", "<blockquote>quoted</blockquote>")
frag("nested list unchanged", "- one\n- two\n  - nested", "<ul><li>one</li><li>two</li><ul><li>nested</li></ul></ul>")
frag("paragraphs become divs", "para one\n\npara two", "<div>para one</div><div>para two</div>")
_mid = srv._tighten_html(srv._fragment_html("text\n```js\ncode\n```\ntail"))
frag("fence between paragraphs", _mid, "<div>text</div><pre data-code-language=\"js\">code</pre><div>tail</div>")

# 7. size-guard message shape
msg = srv._LARGE_BODY_MESSAGE.format(limit=srv.MCP_TEXT_LIMIT, size=srv.MCP_TEXT_LIMIT + 1)
check("message names the limit", str(srv.MCP_TEXT_LIMIT) in msg and "server_only" in msg)

sys.exit(1 if fails else 0)
