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
check("  a break between two closing block tags goes", srv._tighten_html("<ul><li>a</li></ul>\n</div>") == "<ul><li>a</li></ul></div>")
check("  a break between two opening block tags goes", srv._tighten_html("<div>\n<h3>x</h3>") == "<div><h3>x</h3>")
check("  a break that is an element's whole content stays", srv._tighten_html("<li>\n</li><div>\n</div>") == "<li>\n</li><div>\n</div>")
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

# 11. appending keeps tags last: tag-only blocks come out, replace_note adds them back at the end
RVL, UPL = srv._tag_anchor("RV"), srv._tag_anchor("UpNote")
same_ = lambda name, got, want: check(name, got == want, repr(got))
same_("a block of tag links is taken out", srv._without_tag_blocks(f"<div>x</div><div>{RVL} {UPL}</div>"), "<div>x</div>")
same_("  with the line break before it, so no break is left between closing tags",
      srv._without_tag_blocks(f"<div><ul><li>a</li></ul>\n<div>{RVL}</div></div>"), "<div><ul><li>a</li></ul></div>")
same_("  so is UpNote's own <br> + tag link at the end", srv._without_tag_blocks(f"<div><div>x</div></div><br>{RVL}"),
      "<div><div>x</div></div>")
same_("  and a <br> + tag link just inside the closing div", srv._without_tag_blocks(f"<div><div>x</div><br>{RVL}</div>"),
      "<div><div>x</div></div>")
same_("  a block with a non-breaking space and a <br> around the link", srv._without_tag_blocks(f"<div>&nbsp;{RVL}<br></div>"), "")
same_("  a hashtag inside a sentence stays", srv._without_tag_blocks(f"<div>ask {RVL} first</div>"), f"<div>ask {RVL} first</div>")
same_("  a block with text and a tag stays", srv._without_tag_blocks(f"<div>{RVL} notes</div>"), f"<div>{RVL} notes</div>")
same_("  an ordinary link stays", srv._without_tag_blocks('<div><a href="https://e.org">e</a></div>'), '<div><a href="https://e.org">e</a></div>')
check("after an append, the tags come back after the new content",
      srv._with_tags(srv._appended(f"<div>x</div>\n<div>{RVL}</div>", "- new"), ["RV"]) ==
      f"<div>x</div>\n\n- new\n\n<div>{RVL}</div>")

# 12. removing tags
same_("a removed tag's block goes", srv._drop_tags(f"<div>x</div><div>{RVL}</div>", ["rv"]), "<div>x</div>")
same_("  a block keeps the tags not removed", srv._drop_tags(f"<div>{RVL} {UPL}</div>", ["#RV"]), f"<div>{UPL}</div>")
same_("  UpNote's trailing <br> + link goes", srv._drop_tags(f"<div>x</div><br>{RVL}", ["RV"]), "<div>x</div>")
same_("  a link inside a sentence becomes plain text", srv._drop_tags(f"<div>ask {RVL} first</div>", ["RV"]), "<div>ask RV first</div>")
same_("  other tags' links stay", srv._drop_tags(f"<div>ask {UPL} first</div>", ["RV"]), f"<div>ask {UPL} first</div>")
same_("  nothing to remove, no change", srv._drop_tags(f"<div>{RVL}</div>", []), f"<div>{RVL}</div>")

# 13. dates for the list and search filters
import datetime as _dt
local = lambda *a: _dt.datetime(*a).astimezone().timestamp() * 1000
check("a date is local midnight", srv._date_ms("2026-10-03", "updated_after") == local(2026, 10, 3))
check("  a date and time", srv._date_ms("2026-10-03T14:30", "updated_after") == local(2026, 10, 3, 14, 30))
check("  a zone is honoured", srv._date_ms("2026-10-03T00:00+00:00", "x") == _dt.datetime(2026, 10, 3, tzinfo=_dt.timezone.utc).timestamp() * 1000)
try:
    srv._date_ms("last week", "created_after"); check("  nonsense is refused", False, "no error")
except srv.ToolError as e:
    check("  nonsense is refused", "created_after must be a date" in str(e), str(e))

# 14. review fixes, 2026-10-10
check("a Markdown code fence keeps its line breaks",
      srv._tighten_html("x\n\n```html\n<ul>\n<li>x</li>\n</ul>\n```\n<div>a</div>\n<div>b</div>") ==
      "x\n\n```html\n<ul>\n<li>x</li>\n</ul>\n```\n<div>a</div><div>b</div>")
check("  an unclosed fence runs to the end", srv._tighten_html("~~~\n<div>\n<div>x</div>") == "~~~\n<div>\n<div>x</div>")
check("  <pre> is still protected", srv._tighten_html("<pre><div>\n<div></pre>") == "<pre><div>\n<div></pre>")
same_("a title heading that differs by a non-breaking space is removed",
      srv._strip_title_heading("<h2>AWS S3\xa0with Java</h2><div>x</div>", "AWS S3 with Java"), "<div>x</div>")
same_("a note with no <h2> loses the first line that repeats its title",
      srv._strip_title_heading("<div>x1 = x2</div><div>rest</div>", "x1 = x2"), "<div>rest</div>")
same_("  also inside UpNote's wrapper div",
      srv._strip_title_heading("<div><div>Title</div><div>rest</div></div>", "Title"), "<div><div>rest</div></div>")
same_("  a first line that isn't the title stays",
      srv._strip_title_heading("<div>Other</div><div>rest</div>", "Title"), "<div>Other</div><div>rest</div>")
same_("a removed tag quoted as text stops matching",
      srv._drop_tags('<div>&lt;a data-upnote-tag="#RV"&gt;</div>', ["rv"]), '<div>&lt;a data-upnote-tag=&quot;#RV&quot;&gt;</div>')
same_("  a kept tag's link is left alone", srv._drop_tags(f"<div>{UPL}</div>", ["rv"]), f"<div>{UPL}</div>")
same_("lines a rebuild must keep: all but the title", srv._kept_lines("T\na\n\nb\n#rv #up"), ["a", "b", "#rv #up"])
check("  a row of the note's own tags is a tag line", srv._tag_line("#rv #UP", ["RV", "up"]))
check("  a row of other hashtags isn't", not srv._tag_line("#1 #2 #3", ["rv"]))
same_("  minus named lines, compared loosely", srv._kept_lines("T\nStart  Here\nx\nend", "start here", "END"), ["x"])
check("  spacing and case don't matter", srv._line_key("A\xa0 b ") == srv._line_key("a b"))

# 15. review round 2: sending safely
S = srv._sanitize_html
same_("a script goes", S("<div>a</div><script>alert(1)</script><div>b</div>"), "<div>a</div><div>b</div>")
same_("  so do iframes and objects", S('<iframe src="https://e.org"></iframe><object data="x"></object>x'), "x")
same_("  event handlers go, the tag stays", S('<span onclick="steal()" class="k">x</span>'), '<span class="k">x</span>')
same_("  a style that loads a URL goes", S('<span style="background:url(https://e.org/p?d=1)">x</span>'), "<span>x</span>")
same_("  an ordinary style stays", S('<span style="color: red">x</span>'), '<span style="color: red">x</span>')
same_("  javascript: and data: links lose their target", S('<a href="javascript:alert(1)">x</a><a href="data:text/html,x">y</a>'),
      '<a>x</a><a>y</a>')
same_("  an UpNote link that trashes a note is disarmed",
      S('<a href="upnote://x-callback-url/note/moveToTrash?noteId=1">x</a>'), '<a>x</a>')
same_("  a tag link stays", S(srv._tag_anchor("rv")), srv._tag_anchor("rv"))
same_("  a remote image becomes a link", S('<img src="https://e.org/p.gif?d=secret" alt="pic">'), '<a href="https://e.org/p.gif?d=secret">pic</a>')
same_("  a Markdown image becomes a link", S("![x](https://e.org/p.gif)"), "[x](https://e.org/p.gif)")
check("  a Markdown javascript: link is disarmed", "javascript" not in S("[x](javascript:alert(1))"), S("[x](javascript:alert(1))"))
same_("  a code fence becomes escaped code, so its tags are shown, not run",
      S("```html\n<script>x</script>\n```"), '<pre data-code-language="html">&lt;script&gt;x&lt;/script&gt;</pre>')
same_("  links to other apps and UpNote's open links stay",
      S("[c](tel:+1555) [e](evernote:///v/1) [n](upnote://x-callback-url/openNote?noteId=1)"),
      "[c](tel:+1555) [e](evernote:///v/1) [n](upnote://x-callback-url/openNote?noteId=1)")
same_("  a safe style is kept exactly as written", S('<div style="text-align: right !important;">x</div>'),
      '<div style="text-align: right !important;">x</div>')

# 16. every bypass the round-3 review found: nothing live may remain in what would be sent
from html.parser import HTMLParser
from urllib.parse import unquote as _uq


class _Live(HTMLParser):
    BAD_TAGS = {"script", "iframe", "object", "embed", "base", "meta", "link", "style", "svg", "math", "form", "input",
                "video", "audio", "picture", "source", "img", "image", "details"}

    def __init__(self):
        super().__init__()
        self.bad = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BAD_TAGS:
            self.bad.append(tag)
        for n, v in attrs:
            if n.startswith("on") or n in ("srcset", "ping", "poster", "background", "src", "action", "formaction", "srcdoc"):
                self.bad.append(f"{tag}[{n}]")
            if n == "href" and v and not srv._safe_url(v):
                self.bad.append(f"{tag}[href]")
            if n == "style" and v and re.search(r"url|\(|\\|expression", re.sub(r"rgba?\([\d.,\s%]*\)", "", v), re.I):
                self.bad.append("style")


BYPASSES = [
    '<a title=">" onclick="alert(1)">x</a>', '<details open title="<" ontoggle="alert(1)">', '<details/open/ontoggle=alert(1)>',
    '<a title="x"onclick="alert(1)">x</a>', '<a/href="javascript:alert(1)">x</a>', '- a\n  - <a title=">" onclick=alert(1)//>x</a>',
    '    ```\n    x\n<img src=x onerror=alert(1)>', '```a`\n<b onclick=alert(1)>x</b>', '<div>\n```\n<b onclick=alert(1)>x</b>\n```\n</div>',
    '<div>`<b onclick=alert(1)>x</b>`</div>', '\\`<b onclick=alert(1)>x</b>\\`', '- item\n\n  ```\n  code\n- next <b onclick=alert(1)>x</b>',
    '<ifr<iframe></iframe>ame srcdoc="&lt;script&gt;x&lt;/script&gt;"></iframe>', '<scr<script></script>ipt>alert(1)</script>',
    '<sv<svg></svg>g onload=alert(1)>', '<meta http-equiv=refresh content="0;url=upnote://x-callback-url/note/moveToTrash?noteId=abc">',
    'Notes\n\n<details open ontoggle=alert(1)', '<div style="background:url(https://evil)"', '<image src="http://evil/x.png">',
    '<input type=image src=https://evil>', '<video poster=https://evil>', '<audio autoplay src=https://evil>',
    '<table background=https://evil><tr><td>x</td></tr></table>', '<picture><source srcset=https://evil></picture>',
    '<a href=https://ok ping=https://evil>x</a>', '<div style=background:url(https://evil)>x</div>',
    '<div style="background:&#117;rl(https://evil)">x</div>', '<div style="background:u\\72l(https://evil)">x</div>',
    '<a href="upnote://x-callback-url/openNote/../note/moveToTrash?noteId=abc">x</a>',
    '<a href="upnote://x-callback-url/openNote?noteId=1&x-success=upnote%3A%2F%2Fx">x</a>',
]
MD_BAD = re.compile(r"(?<!\\)!\[|\]\(\s*(?:javascript|vbscript|data)|\]:\s*(?:upnote://x-callback-url/note|javascript)"
                    r"|<(?:upnote|javascript):|\]\(upnote\\?://x-callback-url/note", re.I)
MD_BYPASSES = ['![a [b] c](https://evil/x.png)', '![a\nb](https://evil/x.png)', '![a][r]\n\n[r]: https://evil/x.png',
               '[x][r]\n\n[r]: upnote://x-callback-url/note/moveToTrash?noteId=abc', '<upnote://x-callback-url/note/moveToTrash?noteId=abc>',
               '<javascript:alert(1)>', '[x](javascript\\:alert(1))', '[x](upnote\\://x-callback-url/note/moveToTrash?noteId=1)']
for payload in BYPASSES + MD_BYPASSES:
    url = srv._create_url("T", payload, None, True, "m")
    out = _uq(url.split("&text=", 1)[1].split("&markdown=")[0])
    live = _Live()
    live.feed(out)
    live.close()
    check(f"bypass neutralised: {payload[:40]!r}", not live.bad and not MD_BAD.search(out), f"{live.bad} {out[:100]!r}")
check("  a script inside <pre> still goes, since it would run", "<script" not in S("<pre><script>x</script></pre>"))
same_("<pre> line breaks become &#10;", srv._encode_pre_breaks("<pre>a\n\nb</pre>\n<div>x</div>"), "<pre>a&#10;&#10;b</pre>\n<div>x</div>")
same_("  but not a <pre> quoted in a fence", srv._encode_pre_breaks("```\n<pre>a\n\nb</pre>\n```"), "```\n<pre>a\n\nb</pre>\n```")
check("an indented fence keeps its line breaks",
      srv._tighten_html("- a\n    ```html\n    <div>\n    <p>x</p>\n    </div>\n    ```") == "- a\n    ```html\n    <div>\n    <p>x</p>\n    </div>\n    ```")
check("  so does an indented code block", srv._tighten_html("x\n\n    <ul>\n    <li>a</li>\n    </ul>") == "x\n\n    <ul>\n    <li>a</li>\n    </ul>")
import time as _t
t0 = _t.monotonic(); srv._tighten_html("<div>" + " \n" * 25000 + "x")
check("  a long run of blank lines is quick", _t.monotonic() - t0 < 1.0, f"{_t.monotonic() - t0:.2f}s")
from urllib.parse import unquote
url = srv._create_url("T", 'x<span data-upnote-mcp="old"></span>', None, True, "new123")
check("the create link carries one new marker and drops old ones",
      unquote(url).count("data-upnote-mcp") == 1 and 'data-upnote-mcp="new123"' in unquote(url), unquote(url))
try:
    srv._create_url("T", "x\ud800y", None, True); check("an unsendable character is a clear error", False, "no error")
except srv.ToolError as e:
    check("an unsendable character is a clear error", "can't be sent" in str(e), str(e))
same_("a plain first line that repeats the title goes", srv._strip_title_heading("Plans\nTriage x", "Plans"), "Triage x")
same_("  so does a Markdown heading of it", srv._strip_title_heading("## Plans\n\n- x", "Plans"), "\n- x")
same_("  a different first line stays", srv._strip_title_heading("Other\nx", "Plans"), "Other\nx")
same_("visible lines of mixed HTML and Markdown",
      srv._visible_lines("<div>a <b>b</b></div>\n- [ ] task\n### Head\n```html\n[t](http://u)"), ["a b", "task", "head", "t"])
try:
    srv._clean_tag_names(["ok", "a b"]); check("tag names with spaces are refused", False, "no error")
except srv.ToolError:
    check("tag names with spaces are refused", True)

# 17. review round 3
same_("a <pre> named in inline code doesn't swallow the paragraphs after it",
      srv._encode_pre_breaks("Wrap code in `<pre>` blocks.\n\n- item one\n\nThen `</pre>` closes it."),
      "Wrap code in `<pre>` blocks.\n\n- item one\n\nThen `</pre>` closes it.")
same_("  nor one in an indented code block", srv._encode_pre_breaks("x\n\n    <pre>\n    a\n\n    b"), "x\n\n    <pre>\n    a\n\n    b")
same_("  a real <pre> is still encoded", srv._encode_pre_breaks("<pre>a\n\nb</pre>"), "<pre>a&#10;&#10;b</pre>")
same_("on a rename, a heading with the old title stays", srv._strip_title_heading("## Ideas\n- first", "Ideas", "Projects"), "## Ideas\n- first")
same_("  a repeat of the new title goes", srv._strip_title_heading("## Projects\n- first", "Ideas", "Projects"), "- first")

# 18. review round 4
same_("inline code is escaped <code>, keeping its angle brackets", S("Use `List<String>` and `a<b && c>d` here"),
      "Use <code>List&lt;String&gt;</code> and <code>a&lt;b &amp;&amp; c&gt;d</code> here")
same_("  and its image-like text is escaped code, reading the same", S("`vec![1, 2]`"), "<code>vec&#33;&#91;1, 2&#93;</code>")
same_("  so does harmless indented code", S("x\n\n    Map<String, Integer> m;"), "x\n\n    Map<String, Integer> m;")
check("  code holding an event handler is shown escaped, not live", "<b onclick" not in S("`<b onclick=alert(1)>x</b>`"),
      S("`<b onclick=alert(1)>x</b>`"))
check("  so is code holding an image", "<img" not in S("<div>`<img src=x onerror=1>`</div>"))
same_("the marker pattern leaves a closing div it didn't open",
      srv._MARKER.sub("", '<div><div>Para</div><span data-upnote-mcp="aa"></span></div>'), "<div><div>Para</div></div>")
same_("  and takes a whole marker div", srv._MARKER.sub("", '<div>x</div>\n<div><span data-upnote-mcp="aa"></span></div>'), "<div>x</div>")

# 19. harness re-run, round 4
same_("inline code naming <title> doesn't cut off the rest", S("Set the `<title>` element.\n\n- first point"),
      "Set the <code>&lt;title&gt;</code> element.\n\n- first point")
same_("  inline code naming <script> is shown escaped", S("Use `<script>` tags.\n\n- point"), "Use <code>&lt;script&gt;</code> tags.\n\n- point")
same_("  an unclosed <script> doesn't eat the note", S("a <script>x\n\nb"), "a &lt;script>x\n\nb")
same_("a bare & in a URL stays as written", S("[x](https://a.b/?q=x&startIndex=50) &amp; ok"), "[x](https://a.b/?q=x&startIndex=50) &amp; ok")
same_("a fence holding <pre> stays one code block", srv._fences_to_pre("```html\n<pre>a</pre>\n```\nAfter."),
      '<pre data-code-language="html">&lt;pre&gt;a&lt;/pre&gt;</pre>\nAfter.')
same_("a fence after an indented line keeps its line breaks", srv._tighten_html("```html\n<div>\n    <ul>\n</ul>\n</div>\n```"),
      "```html\n<div>\n    <ul>\n</ul>\n</div>\n```")
same_("a stored <pre> after an indented line is still encoded", srv._encode_pre_breaks("<pre>a\n    b</pre>\n<pre>c\n\nd</pre>"),
      "<pre>a&#10;    b</pre>\n<pre>c&#10;&#10;d</pre>")
check("a < before a dropped tag can't rebuild a live tag", "<img" not in S("note <<x>img src=x onerror=alert(1)>"))
check("a reference target on the next line is checked", "javascript" not in S("[r]:\n  javascript:alert(1)"))
check("markup the parser couldn't read is now plain text", "<![" not in S("<pre><![x</pre>"), S("<pre><![x</pre>"))

# 20. round 5: text that only looks like a tag is shown as written; removals are reported
R = srv._sanitize_report
for src, shown in [("export TOKEN=\\<YOUR_TOKEN\\>", "&lt;YOUR_TOKEN"), ("Bearer <API_KEY>", "&lt;API_KEY>"),
                   ("if (a<b && c>d)", "a&lt;b && c>d"), ("List<String> and HashMap<String, Vec<u8>>", "HashMap&lt;String, Vec&lt;u8>>"),
                   ("press <Tab> or <C-a>", "&lt;Tab> or &lt;C-a>"), ("sort <in.txt >out.txt", "&lt;in.txt >out.txt"),
                   ("<?php echo 1 ?>", "&lt;?php echo 1 ?>")]:
    out, removed = R(src)
    check(f"shown as written, not dropped: {src!r}", shown in out and not removed, f"{out!r} {removed}")
same_("an email in angle brackets becomes a mail link", R("Mail <help.desk@example.com> today")[0],
      "Mail [help.desk@example.com](<mailto:help.desk@example.com>) today")
same_("  so does an autolink of another scheme", R("<ssh://git@github.com/org/repo.git>")[0],
      "[ssh://git@github.com/org/repo.git](<ssh://git@github.com/org/repo.git>)")
same_("  an unsafe one stays text", R("<javascript:alert(1)>")[0], "&lt;javascript:alert(1)&gt;")
same_("  an autolink's underscores aren't read as bold", R("<https://e.com/__init__.py>")[0],
      "[https://e.com/\\_\\_init\\_\\_.py](<https://e.com/__init__.py>)")
check("comparisons aren't reported as removals", not R("x <= y >= z, 1 < 2 > 0, <1st>, a <=> b")[1])
check("a removed event handler is reported", R("<b onclick=x()>b</b>")[1] == ["b onclick"], str(R("<b onclick=x()>b</b>")[1]))
check("a removed image is reported", "image" in R("<img src=x alt=pic>")[1])
check("a disarmed UpNote link is reported", R('<a href="upnote://x-callback-url/note/new?t=1">bad</a>')[1])
same_("a fence inside a blockquote keeps its code as written", R("> ```\n> echo $((1<2)) && ls\n> ```")[0],
      "> ```\n> echo $((1<2)) && ls\n> ```")


# 21. round 6: the round-5 harness findings
same_("a <pre> named in inline code leaves later code alone (A)", S("Use `<pre>` for blocks and `List<String>` for lists."),
      "Use <code>&lt;pre&gt;</code> for blocks and <code>List&lt;String&gt;</code> for lists.")
same_("  so does one in an unclosed span's paragraph", S("a `<pre> b\n\nc `Map<K, V>`"), "a `&lt;pre> b\n\nc <code>Map&lt;K, V&gt;</code>")
check("  a stored <pre> after a code span is still a block", srv._pre_spans("`x` <pre>a `b</pre> `y`") == [(4, 19)],
      str(srv._pre_spans("`x` <pre>a `b</pre> `y`")))
check("  a fence after a <pre> named in code is still converted", "<pre" in S("`<pre>`\n\n```\n<b onclick=x>\n```").split("</code>")[1])
for payload in ['<a href="`" onmouseover="alert(1)" x="`">link</a>',  # D1: code set aside inside a tag
                '<div style="`" title="x" onclick=alert(1) y="`">z</div>',
                '<a title="\n    x" onclick=alert(1) y="">k</a>',
                '`[x](javascript:alert(1))`', '`![i](https://evil/t.png)`',  # D2: Markdown inside <code>
                '[l](java<abbr>script:alert(1))', '!<svg></svg>[i](https://evil/x.png)',  # D3: rebuilt by a dropped tag
                '<!-- -->\n[r]: javascript:alert(1)\n\n[x][r]', '!<https://evil/x.png>',  # and by an autolink set aside
                '<div>Use the `<title>` element.</div>', 'a ``` `<textarea>` b']:  # D4: raw-text elements
    out = S(payload)
    live = _Live()
    live.feed(out)
    live.close()
    check(f"round-5 bypass neutralised: {payload[:40]!r}", not live.bad and not MD_BAD.search(out)
          and not re.search(r"<(?:title|textarea|xmp|noscript|plaintext)\b", out), f"{live.bad} {out[:120]!r}")
same_("inline code that could act is escaped against Markdown too", S("`[x](javascript:alert(1))`"),
      "<code>&#91;x&#93;&#40;javascript:alert&#40;1&#41;&#41;</code>")
import time as _t
for name, big in [("many <pre> blocks", "<pre>x</pre>\n" * 8000), ("many unclosed <script", "<script " * 20000),
                  ("many unclosed <style", "<style " * 20000), ("many unclosed comments", "<!-- " * 20000),
                  ("many backticks with no closer", "".join("`" * n + " a " for n in range(1, 400)))]:
    t0 = _t.monotonic()
    S(big)
    check(f"quick on {name}", _t.monotonic() - t0 < 2, f"{_t.monotonic() - t0:.2f}s")

# 22. round 6: UpNote's own converter (micromark + GFM + front matter, then its link and highlight passes)
for payload in ['<span title="<http://x/onmouseover=alert(1)//>">hover me</span>', '<i title="<a@b.co>">x</i>']:
    out = S(payload)
    live = _Live()
    live.feed(out)
    live.close()
    check(f"an autolink inside an attribute stays text: {payload[:30]!r}", not live.bad, f"{live.bad} {out!r}")
check("a ! before an autolink makes no image", "\\![" in S("!<https://evil/x.png>"), S("!<https://evil/x.png>"))
same_("code after an escaped backtick is still code", S("\\``<img src=x onerror=alert(1)>` shows a tag"),
      "\\`<code>&lt;img src=x onerror=alert&#40;1&#41;&gt;</code> shows a tag")
check("a <pre> opening a line ends a code span's search", "javascript" not in S("a `b\n<pre>\nx\n</pre>\n` c [x](javascript:alert(1))"))
same_("  and leaves that <pre>'s content alone", S("a `b\n<pre>\n![x](javascript:alert(1))\n` c\n</pre>"),
      "a `b\n<pre>\n!&#91;x&#93;(javascript:alert(1))\n` c\n</pre>")
out = S("<pre>\n```\n</pre>\n\n- a\n  <pre>\n[x](javascript:alert(1)) ![t](https://evil.example/t.png)")
check("a <pre> cut off inside a list item doesn't shield its links", "javascript" not in out and "![" not in out, out)
same_("plain-text upnote:// that changes notes can't become a link", S("see upnote://x-callback-url/note/new?title=x"),
      "see upnote:<span></span>//x-callback-url/note/new?title=x")
same_("  one that only opens a note is left", S("see upnote://x-callback-url/openNote?noteId=1"), "see upnote://x-callback-url/openNote?noteId=1")
check("  the x-success check sees a bare & in an attribute",
      "x-success" not in S('<a href="upnote://x-callback-url/openNote?noteId=1&x-success=upnote%3A%2F%2Fx">x</a>'))
same_("a plain URL keeps its &", S("see https://e.com/?x=1&y=2"), "see https://e.com/?x=1&y=2")
same_("  unless HTML would read an entity there", S("a &not=1 b"), "a &amp;not=1 b")
check("a first line of --- isn't read as front matter", "text=%2A%2A%2A" in srv._create_url("T", "---\nfoo\n---\nbar", None, True))
same_("inline code inside an HTML block is text there", S("<div>`List<String>`</div>"), "<div>`List&lt;String>`</div>")
same_("indented code that couldn't be kept raw is sent as an escaped <pre>", S("x\n\n    `<b onclick=x>y</b>`"),
      "x\n\n<pre>`&lt;b onclick=x&gt;y&lt;/b&gt;`</pre>")
same_("  so Rust in an indented block shows as written", S("Text\n\n    let v: Vec<u8> = vec![1];"),
      "Text\n\n<pre>let v: Vec&lt;u8&gt; = vec!&#91;1];</pre>")
for t in ['x ` y\n`<img alt=">` z" src="http://e.example/i.png">', '$$ a\n\n    b $$ <img alt=">\nz" src="http://e.example/i.png">',
          'x\n    <img alt="\nz" src="http://e.example/i.png">', 'x\n    <img alt=">\nz" src="http://e.example/i.png">']:
    out = S(t)
    live = _Live()
    live.feed(out)
    live.close()
    check(f"round 13: no remote image from code that isn't code: {t[:30]!r}", not live.bad and "<img" not in out, out)
same_("a dropped block element keeps its text on its own line", S("<details><summary>sum</summary>body</details>"),
      "<div><div>sum</div>body</div>")
same_("== and $$ in a note's HTML stay as written", srv._literal_marks("<div>a == b</div><div>AS $$ x</div><pre>c == d</pre>"),
      "<div><span>a == b</span></div><div><span>AS &#36;&#36; x</span></div><pre>c == d</pre>")
same_("an unsafe autolink is text that can't become a link", S("<upnote://x-callback-url/note/moveToTrash?noteId=abc>"),
      "&lt;upnote:<span></span>//x-callback-url/note/moveToTrash?noteId=abc&gt;")
same_("an autolink inside an HTML block stays text there", S("<p>see <https://e.com/a_b_c></p>"), "<p>see &lt;https://e.com/a_b_c></p>")
same_("a ! before [ that isn't an image keeps its !", S("<div>`vec![1, 2]`</div>"), "<div>`vec!&#91;1, 2]`</div>")
# round 7 fuzz: UpNote reads these as text and links URLs in text
for payload in ["a\n    upnote://x-callback-url/trashNote?noteId=1", "- a\n    upnote://x-callback-url/note/new?title=a",
                "- a\n  - b\n\n    [r]: upnote://x-callback-url/note/new?title=a\n\n    [x][r]",
                "- a\n  - x upnote://x-callback-url/openNote?noteId=1&x-success=javascript:alert(1)",
                "[t](upnote://x-callback-url/openNote?noteId=1&x-success=https://evil.example/)",  # round 8
                "upnote://x-callback-url/openNote?<upnote://x-callback-url/deleteNote",
                "- upnote://x-callback-url/openNote?>upnote://x-callback-url/note/new\n  1."]:
    out = srv._create_url("T", payload, None, True)
    sent = _uq(out.split("&text=", 1)[1].split("&markdown=")[0])
    check(f"a note-changing upnote:// URL can't become a link: {payload[:30]!r}",
          all(srv._safe_url(srv.html_lib.unescape(u)) for u in re.findall(r"upnote://[^\s<>\"'()&]*(?:&(?!lt;|gt;)[^\s<>\"'()&]*)*", sent)), sent[:150])
same_("an unclosed <pre> mid-line is text", S("- x <pre> y\n- after"), "- x &lt;pre> y\n- after")
check("  a safe link target isn't split", "openNote" in S("[t](upnote://x-callback-url/openNote?noteId=1)") and "<span>" not in S("[t](upnote://x-callback-url/openNote?noteId=1)"))
same_("a name that isn't an entity is text", S("a &notit; b &copy; c"), "a &amp;notit; b &copy; c")
# round 8 review
for code in ["x\n\n    function f(data:any) { return a < b && c; }", "x\n\n    a.href = 'javascript:void(0)'; b < c",
             "> ```\n> img.src = 'data:image/png;base64,AAA'; a<b\n> ```"]:
    same_(f"code with a data:/javascript: word is kept as written: {code[3:30]!r}", S(code), code)
for t in ["see upnote&#58;//x-callback-url/note/new", "&#117;pnote://x-callback-url/note/new", "upnote:&#47;/x-callback-url/note/new"]:
    check(f"an entity-encoded upnote: URL is split too: {t[:22]!r}", re.search(r"<span></span>(?://|&#47;)", S(t)), S(t))
out = _uq(srv._create_url("T", "$$<script>w</script>$$\n\n```\n$$\n![a](https://e.com/a.png)\n$$", None, True).split("&text=", 1)[1].split("&markdown=")[0])
check("a $$ in a code block can't pair with one before it", "$$" not in out.split("<pre", 1)[1], out)
# round 9 review
out = S("upnote&#58;//x\n\n&#91;a&#93;: https://evil.example/x.png\n\n&#33;&#91;a&#93; &#42;&#42;b&#42;&#42; https://a.example/?a=1&b=2")
check("splitting an entity-spelled upnote: URL decodes nothing else", "&#91;a&#93;:" in out and "&#33;&#91;a&#93;" in out
      and "&#42;&#42;b" in out and "?a=1&b=2" in out and "upnote&#58;<span></span>//x" in out, out)
for t in ["[x](upnote://x-callback-url/openNote?noteId=1&title=upnote://a)", "[x](upnote://x-callback-url/openNote?noteId=1&amp;b=2)"]:
    check(f"a safe link destination isn't split: {t[:40]!r}", "<span>" not in S(t), S(t))
same_("HTML a caller writes with <pre> in a sentence is kept", S("Wrap code in <pre>like this</pre>"), "Wrap code in <pre>like this</pre>")
own = "<p>" + "a" * 100 + "</p><pre>x\n\ny</pre><p>end " + "z" * 80 + "</p>"
# round 10
check("a tag before [r]: doesn't make a note-changing URL look like a checked link target",
      "upnote:<span></span>//" in S("<span>[r]: upnote://x-callback-url/note/new?title=a"), S("<span>[r]: upnote://x-callback-url/note/new?title=a"))
out = S("<pre>\n![a](https://e.com/a.png) [x](upnote://x-callback-url/note/new) $$\n</pre>")
check("a <pre> block's content can't form an image, link or formula if exposed", "![" not in out and "](" not in out and "$$" not in out, out)
# round 10 review
for t in ["<div>&#x75pnote://x-callback-url/note/new?text=a</div>", "<div>&#117pnote://x-callback-url/note/new</div>",
          "<div>upnote&#58//x-callback-url/note/new</div>", "<b>x</b>[y]: upnote://x-callback-url/note/new?text=a"]:
    check(f"split, however it is spelled: {t[:30]!r}", "<span></span>" in S(t), S(t))
out = _uq(srv._create_url("T", "Saves $$ fast\n\n```sh\necho $HOME\n```\n\nCosts $$ more", None, True).split("&text=", 1)[1].split("&markdown=")[0])
check("a lone $ in a code block still stops a $$ pair running across it", "echo $HOME" in out, out)
same_("LaTeX in inline code is escaped code that can't pair", S("Write `$$\\frac{a}{b}$$` for display math."), "Write <code>$&#36;&#92;frac{a}{b}$&#36;</code> for display math.")
for t in ["x ` y\n`![` z](http://e.example/i.png)", '$$ x `a$$ <img alt="` " src="http://e.example/i.png">',
          'x ` y\n`<b title="` z" onclick=alert(1)>']:
    out = S(t)
    live = _Live()
    live.feed(out)
    live.close()
    check(f"code Markdown may not read as code can't expose an image or a handler: {t[:30]!r}",
          "![" not in out and not live.bad and "<img" not in out and not re.search(r"<b [^>]*onclick", out), out)
same_("indented code holding $$ is still kept as written", S("x\n\n    a<b\n    <!-- w -->\n    $$y"), "x\n\n    a<b\n    <!-- w -->\n    $$y")
for t in ["see $$ x `$$ ![a]`", "see $$ x\n\n    $$ ![a]"]:
    check(f"code with ![ or $$ isn't kept raw: {t[:20]!r}", "$$ ![a]" not in S(t), S(t))
t0 = _t2_ = __import__("time").monotonic()
S("upnote&#58;//" + "&amp;b" * 50000)
check("quick on a long entity run", __import__("time").monotonic() - t0 < 1, f"{__import__('time').monotonic() - t0:.2f}s")
# round 14 review
for t in ["- a\n\n    [x](upnote&#58;//x-callback-url/note/new?text=pwn)", "- a\n\n    upnote&#58;//x-callback-url/note/new?text=pwn",
          "x $$ y\n\n    $$ [x](upnote&#58;//x-callback-url/note/new?text=pwn)", "x\n\n    a\r[x](upnote&#58;//x-callback-url/note/new)",
          "> ```\n[x](upnote&#58;//x-callback-url/note/new)\n> ```", "upnote\\://x-callback-url/note/new?text=pwn",
          "upnote:\\//x-callback-url/note/new?text=pwn", "- a\n\n    [x](upnote\\://x-callback-url/note/new)"]:
    out = S(t)
    check(f"round 14: no note-changing link from {t[:34]!r}",
          not re.search(r"\]\(upnote(?:&#58;|\\?:)|(?<!<span></span>)(?:upnote(?:&#58;|\\?:)(?!<span>))(?:\\?/|&#47;)", out), out)
same_("a table cell's \\| in inline code shows as |", S("| a |\n|---|\n| `x\\|y` |"), "| a |\n|---|\n| <code>x&#124;y</code> |")
same_("a code span keeps its inner spaces less one each side", S("`  a  `"), "<code> a </code>")
t0 = __import__("time").monotonic()
S("x\n\n    <b>\n\n" * 6000)
check("quick on many indented blocks", __import__("time").monotonic() - t0 < 2, f"{__import__('time').monotonic() - t0:.2f}s")
same_("a URL in inline code can't be linked by GFM", S('a `b <a href="https://x.y/z">w</a> www.q.r` c'),
      'a <code>b &lt;a href="https&#58;//x.y/z"&gt;w&lt;/a&gt; www&#46;q.r</code> c')
# round 15 review: references and backslashes mixed
for t in ["a upnote&#58;\\/\\/x-callback-url/note/new?title=P", "upnote&colon;\\/\\/x-callback-url/note/new", "upnote\\:&#47;/x-callback-url/note/new",
          "u&#112;note\\://x-callback-url/note/new", "upnot&#101;\\:/&#47;x-callback-url/note/new"]:
    check(f"split however it is spelled: {t[:28]!r}", "<span></span>" in S(t), S(t))
t0 = __import__("time").monotonic()
S("\n\t![\n" * 33000)
check("quick on many tab-indented blocks", __import__("time").monotonic() - t0 < 2, f"{__import__('time').monotonic() - t0:.2f}s")
# round 16 review
t0 = __import__("time").monotonic()
srv._MARKER.sub("", "\t\n\n" * 20000)
check("the marker pattern is quick on long whitespace", __import__("time").monotonic() - t0 < 1, f"{__import__('time').monotonic() - t0:.2f}s")
same_("  and still takes a marker with the space before it", srv._MARKER.sub("", 'a\n\n<div> <span data-upnote-mcp="x"></span> </div>'), "a")
check("a long line before a list's blank line still shows the list",
      "<pre>" not in S("- item " + "x" * 5000 + "\n\n    <i onclick=x>code</i>"), S("- item " + "x" * 5000 + "\n\n    <i onclick=x>code</i>")[-60:])
same_("a safe link spelled with references stays whole", S("[a](upnote&#58;\\/\\/x-callback-url/openNote?noteId=1)"),
      "[a](upnote&#58;\\/\\/x-callback-url/openNote?noteId=1)")
# round 17 review
for t in ["<b>x</b>[r]: upnote&#58;//x-callback-url/openNote?noteId=1(&x-success=foo)",
          "<b>x</b>[r]: upnote://x-callback-url/openNote?noteId=1(&x-success=foo)",
          "zz[" + "x" * 36 + "]: upnote&#58;//x-callback-url/openNote?noteId=1(&x-success=foo)"]:
    check(f"a URL after something that only looks like a definition is split: {t[:24]!r}", "<span></span>" in S(t), S(t))
# round 18 review
for t in ["See [inbox](upnote://x-callback-url/view).", "[a](upnote://x-callback-url/openNotebook), [b](upnote://x-callback-url/openFilter)"]:
    check(f"a safe link followed by punctuation stays whole: {t[:24]!r}", "<span>" not in S(t), S(t))
for t in ["[x](upnote://x-callback-url/openNote?a=1 &x-success=1)", "[x](upnote://x-callback-url/openNote?a=1>&x-success=1)",
          "[x](upnote://x-callback-url/openNote>/../../note/new)", "[x](upnote://x-callback-url/openNote?a=1　&x-success=1)"]:
    check(f"a destination with > or a non-ASCII space is checked whole: {t[:30]!r}", "](#)" in S(t), S(t))
# round 19 review
for t in ["[x](upnote://x-callback-url/openNote?noteId=1\\)&x-success=evil)", "[x](<upnote://x-callback-url/openNote?noteId=1\\> &x-success=e>)",
          "[x](upnote://x-callback-url/openNote?noteId=1`&x-success=e`)"]:
    out = S(t)
    check(f"an escaped ) or > or code can't cut a destination short: {t[:40]!r}",
          "](#" in out or not re.search(r"\]\(<?upnote://[^)\s]*x-success", out), out)
same_("  a safe destination with an escaped ) stays whole", S("[x](upnote://x-callback-url/openNote?noteId=a\\)b)"),
      "[x](upnote://x-callback-url/openNote?noteId=a\\)b)")
# round 20 review
for t in ["](upnote://x-callback-url/openNote?noteId=1)&x-success=e", "a](upnote://x-callback-url/openNote?noteId=1)&x-success=e",
          "[a](b)](upnote://x-callback-url/openNote?noteId=1)&x-cancel=e"]:
    check(f"a ]( that isn't a link can't keep an unsafe URL whole: {t[:24]!r}", "<span></span>" in S(t), S(t))
for name, big in [("](a(", "](a(" * 12000), ("](<a\\>", "](<a\\>" * 9000), ("](a\\(", "](a\\(" * 10000), ("](<\\<", "](<\\<" * 10000)]:
    t0 = __import__("time").monotonic()
    S(big)
    check(f"quick on many {name}", __import__("time").monotonic() - t0 < 2, f"{__import__('time').monotonic() - t0:.2f}s")
same_("text between a link and a code block isn't repeated", S("[a](b)\n\n```\ny\n```"), "[a](b)\n\n<pre>y</pre>")
same_("  nor on the same line", S("[a](b) x\n```\ny\n```"), "[a](b) x\n<pre>y</pre>")
out = S('[a][]\n\n[a]: data:text/html,x<wfzla@example.com><iframe src="https://e.com">wgzla</iframe>')
check("a definition holding an autolink is checked, its text kept", "data:" not in out and "wgzla" in out, out)
# round 21 review
for t in ["**[a](upnote://x-callback-url/view)** done", "_[a](upnote://x-callback-url/view)_", "~~[b](upnote://x-callback-url/openNotebook)~~"]:
    check(f"a safe link inside emphasis stays whole: {t[:24]!r}", "<span>" not in S(t), S(t))
for t in ["see upnote://x-callback-url/view\x1c/../note/new?title=x now", "x](upnote://x-callback-url/view\x1f/../note/new?title=x)"]:
    check(f"a control character Python counts as space can't end the URL early: {t[:30]!r}", "<span></span>" in S(t) or "](#" in S(t), repr(S(t)))
for name, big in [("[a](upnote://x-callback-url/view)", "[a](upnote://x-callback-url/view)" * 6000),
                  ("](upnote&#58;//x-callback-url/view)", "](upnote&#58;//x-callback-url/view)" * 5000),
                  ("(upnote://x-callback-url/note/new)", "(upnote://x-callback-url/note/new)" * 6000)]:
    t0 = __import__("time").monotonic()
    S(big)
    check(f"quick on many {name[:20]}", __import__("time").monotonic() - t0 < 2, f"{__import__('time').monotonic() - t0:.2f}s")
# round 22 review
for mid in ["*x*", "~~x~~", "`x`", "<https://a.b>", "&quot;", "&nbsp;", "&#32;", "&lt;"]:
    t = f"see upnote://x-callback-url/editNote{mid}/../view here"
    check(f"a ../ can't fold a cut-short route into a safe one: {mid!r}", "upnote:<span></span>//" in S(t), S(t))
check("  nor in a link destination", "](#" in S("[a](upnote://x-callback-url/editNote*x*/../view)"), S("[a](upnote://x-callback-url/editNote*x*/../view)"))
# round 23 review
for t in ["see upnote://x-callback-url/view?mode=all_notes&x%2Dsuccess=https:%2F%2Fexample.com%2Fa now",
          "[a](upnote://x-callback-url/VIEW?x%2Derror=https://example.com/c)", "[a](upnote://x-callback-url/openNote?noteId=1&x%2dsuccess=y)"]:
    out = S(t)
    check(f"a percent-encoded x- parameter or a case-varied route is refused: {t[:34]!r}", "<span></span>" in out or "](#" in out, out)
check("  a plain openNote link still works", srv._safe_url("upnote://x-callback-url/openNote?noteId=1"))
check("  and a tag link", srv._safe_url("upnote://x-callback-url/tag/view?tag=work"))
import time as _t2
t0 = _t2.monotonic()
S("a".join("`" * n for n in range(1, 600)))
check("quick on backtick runs of every length", _t2.monotonic() - t0 < 2, f"{_t2.monotonic() - t0:.2f}s")

print("FAILURES:", fails)
sys.exit(1 if fails else 0)
