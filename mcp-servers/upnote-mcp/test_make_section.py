#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["mcp==2.2.0"]
# ///
"""Checks for make_section's HTML surgery, run against synthetic note markup.

Touches neither UpNote nor your notes: it calls the planning function directly with
hand-written HTML. Exits non-zero if any check fails.
"""
import importlib.util
import re
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

def refuses(name, source, heading, phrase):
    try:
        srv._plan_section(source, heading)
        check(name, False, "no error raised")
    except srv.ToolError as e:
        check(name, phrase in str(e), str(e)[:100])

SECTION = srv._section_html

TOP = ('<div>intro line</div>'
       '<h3>Details</h3>'
       '<div>first block</div><ul><li>a</li><li>b</li></ul>'
       '<h3>Other</h3><div>after</div>')

# 1. a top-level heading wraps the blocks under it, stopping at the next heading
plan = srv._plan_section(TOP, "Details")
check("wraps blocks under a top-level heading", plan["blocks_moved"] == 2, str(plan["blocks_moved"]))
check("  section title comes from the heading", plan["section_title"] == "Details")
check("  heading was not inside a section", plan["inside_section"] is None, str(plan["inside_section"]))
check("  content moved inside the new section",
      '<div class="shine-section-content-inner"><div>first block</div><ul><li>a</li><li>b</li></ul></div>' in plan["html"])
check("  text outside the range is untouched",
      plan["html"].startswith("<div>intro line</div>") and plan["html"].endswith("<h3>Other</h3><div>after</div>"))
check("  the old heading is gone from the body", plan["html"].count("<h3>Details</h3>") == 1)

# 2. a heading inside an existing section nests inside it
NESTED_SOURCE = '<div>lead</div>' + SECTION("Outer", '<div>outer text</div><h3>Inner</h3><div>inner text</div>', False) + '<div>tail</div>'
plan = srv._plan_section(NESTED_SOURCE, "Inner")
check("nests inside an existing section", plan["inside_section"] == "Outer", str(plan["inside_section"]))
inner_at = plan["html"].index('<h3>Inner</h3>')
outer_content_at = plan["html"].index('shine-section-content-inner')
check("  the new section sits inside the outer section's content", inner_at > outer_content_at)
check("  the outer section still closes after it", plan["html"].endswith("<div>tail</div>"))
check("  two sections now exist", plan["html"].count("shine-collapsible-section") == 2, str(plan["html"].count("shine-collapsible-section")))
check("  nothing outside the outer section moved", plan["html"].startswith("<div>lead</div>"))

# 3. collapsed=True marks the new section closed
plan = srv._plan_section(TOP, "Details", collapsed=True)
check("collapsed=true marks the section closed", plan["html"].count("shine-section-collapsed") == 1)

# 4. a deeper heading does not stop the section, an equal or higher one does
LEVELS = '<h3>Top</h3><div>one</div><h4>Sub</h4><div>two</div><h3>Next</h3><div>three</div>'
plan = srv._plan_section(LEVELS, "Top")
check("a deeper heading stays inside the section", plan["blocks_moved"] == 3, str(plan["blocks_moved"]))
check("  a same-level heading ends it", plan["html"].endswith("<h3>Next</h3><div>three</div>"))

# 5. inline markup in the heading is kept as the section title
LINKED = '<h3>See <b>this</b> part</h3><div>body</div>'
plan = srv._plan_section(LINKED, "See this part")
check("inline markup in the heading survives", "<h3>See <b>this</b> part</h3>" in plan["html"])

# 5b. an end marker ends the range and is removed with it
MARKED = ('<div>before</div><h6>start collapse</h6><blockquote><div>body text</div></blockquote>'
          '<h6>end collapse</h6><div>after</div>')
plan = srv._plan_section(MARKED, "start collapse", until="end collapse", title="Explanation")
check("end marker ends the range", plan["blocks_moved"] == 1, str(plan["blocks_moved"]))
check("  both markers are gone", "start collapse" not in plan["html"] and "end collapse" not in plan["html"])
check("  title overrides the heading text", "<h3>Explanation</h3>" in plan["html"] and plan["section_title"] == "Explanation")
check("  marked content moved inside", '<div class="shine-section-content-inner"><blockquote><div>body text</div></blockquote></div>' in plan["html"])
check("  text outside the markers is untouched",
      plan["html"].startswith("<div>before</div>") and plan["html"].endswith("<div>after</div>"))

# 5c. an end marker inside an existing section nests there
MARKED_NESTED = SECTION("Outer", '<div>lead</div><h6>start collapse</h6><div>middle</div><h6>end collapse</h6><div>tail</div>', False)
plan = srv._plan_section(MARKED_NESTED, "start collapse", until="end collapse", title="Inner")
check("marked range nests inside its section", plan["inside_section"] == "Outer", str(plan["inside_section"]))
check("  two sections result", plan["html"].count("shine-collapsible-section") == 2)
check("  content after the end marker stays in the outer section", plan["html"].rstrip().endswith("</div>") and "<div>tail</div>" in plan["html"])

# 6. refusals
refuses("refuses a heading that isn't there", TOP, "Nope", "No heading in the note reads")
refuses("refuses a heading with nothing under it", '<div>x</div><h3>Empty</h3>', "Empty", "would be empty")
refuses("refuses a heading that is already a section title", SECTION("Outer", "<div>x</div>", False), "Outer", "already a collapsible section's title")
def refuses_kw(name, source, phrase, **kw):
    try:
        srv._plan_section(source, **kw)
        check(name, False, "no error raised")
    except srv.ToolError as e:
        check(name, phrase in str(e), str(e)[:110])

refuses_kw("refuses an end marker that isn't there", MARKED, "end of the range is unclear",
           heading="start collapse", until="no such marker")
refuses_kw("refuses markers with nothing between them", '<h6>start collapse</h6><h6>end collapse</h6><div>x</div>',
           "so the section would be empty", heading="start collapse", until="end collapse")
refuses("refuses an ambiguous heading", '<h3>Dup</h3><div>a</div><h3>Dup</h3><div>b</div>', "Dup", "headings read")

# 7. the result parses back into the same shape
plan = srv._plan_section(NESTED_SOURCE, "Inner")
tree = srv._NoteHtml(plan["html"])
sections = [n for n in srv._walk(tree.root) if "shine-collapsible-section" in n.classes]
check("result parses back with one section inside another",
      len(sections) == 2 and sections[1].parent is not None and
      srv._enclosing_section(plan["html"], sections[1]) == "Outer",
      f"{len(sections)} sections")

# 8. offsets stay right when the HTML holds characters other code treats as line ends
for sep in ("\u2028", "\r", "\x0c"):
    src = f"<h3>Details</h3>\n<div>a{sep}b</div>\n<div>c</div>\n<h3>Next</h3>\n<div>tail</div>"
    plan = srv._plan_section(src, "Details")
    inner = plan["html"].split('shine-section-content-inner">', 1)[1]
    check(f"section takes the right blocks around {sep!r}",
          plan["blocks_moved"] == 2 and inner.startswith(f"\n<div>a{sep}b</div>\n<div>c</div></div>")
          and plan["html"].endswith("\n<h3>Next</h3>\n<div>tail</div>"), repr(plan["html"][-120:]))
    plan = srv._plan_section(f"<div>a{sep}b</div>\n<h3>Details</h3>\n<div>body</div>", "Details")
    check(f"  a heading after {sep!r} is found", plan["blocks_moved"] == 1)

# 9. appending: line breaks between tags go, everything else stays
EXISTING = ('<div><h3>Part</h3>\n<div>text</div>\n<ul><li>item\n</li><li>\n</li></ul>'
            '<pre data-code-language="bash">echo a</b>\n<b>\n</pre>\n<div>end</div></div>')
tight = srv._tighten_html(EXISTING)
check("line breaks between a closing and an opening tag are removed",
      "</h3><div>text</div><ul>" in tight and "</pre><div>end</div>" in tight, tight)
check("  a line break inside an element's text stays", "<li>item\n</li>" in tight)
check("  a line break between an opening and a closing tag stays", "<li>\n</li>" in tight)
check("  a line break between inline tags stays, since it shows as a space",
      srv._tighten_html("<div><b>bold</b>\n<i>italic</i></div>") == "<div><b>bold</b>\n<i>italic</i></div>")
check("  a break between a block and an inline tag stays",
      srv._tighten_html("<div>x</div>\n<b>y</b>") == "<div>x</div>\n<b>y</b>")
check("  a code block is left exactly as it was", '<pre data-code-language="bash">echo a</b>\n<b>\n</pre>' in tight)
joined = srv._appended(EXISTING + "\n", "  ### New\n\n- x  \n")
check("appended Markdown follows the HTML after one blank line", joined == tight + "\n\n### New\n\n- x", repr(joined[-30:]))
check("appending to an empty note leaves only the new text", srv._appended("", "- x").strip() == "- x")

# 10. tags travel as hashtag links in the body
anchor = srv._tag_anchor("RV")
check("a tag link has UpNote's own shape", anchor ==
      '<a data-upnote-tag="#RV" spellcheck="false" data-non-editable="true" href="upnote://x-callback-url/tag/view?tag=RV">#RV</a>', anchor)
check("  a nested tag keeps its slash, odd characters are escaped",
      'tag=work/ping"' in srv._tag_anchor("work/ping") and "#a&amp;b" in srv._tag_anchor("a&b"))
check("missing tags are added at the end", srv._with_tags("- x", ["RV", "UpNote"]) ==
      "- x\n\n<div>" + srv._tag_anchor("RV") + " " + srv._tag_anchor("UpNote") + "</div>")
check("  a tag the body already carries isn't added twice, whatever its case",
      srv._with_tags("<div>" + srv._tag_anchor("RV") + "</div>", ["rv"]) == "<div>" + srv._tag_anchor("RV") + "</div>")
check("  no tags, no change", srv._with_tags("- x", []) == "- x")

print("FAILURES:", fails)
sys.exit(1 if fails else 0)
