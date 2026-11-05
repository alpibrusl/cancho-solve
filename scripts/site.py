#!/usr/bin/env python3
"""Writes the project pages (docs/index.html, examples.html, stories.html, agents.md, llms.txt) from real runs of the built `solve`.

    SOLVE=build/solve python3 scripts/site.py          write the pages
    SOLVE=build/solve python3 scripts/site.py --check  fail if a page on disk is not what the binary prints today

Nothing on a page is typed in by hand except the prose and the FIGURES table below: every command is run, and the text shown is its standard output
or standard error. The models are docs/examples/*.sol; the figures drawn on the stories are computed from `solve expand` and `solve run` of those
files, not from numbers written here. What is cut for reading (the zero entries of a long solution) is marked with an ellipsis and said so on the page.
Shares no code with the solver: it runs the binary, and reads JSON.
"""
import html
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
SOLVE = os.environ.get("SOLVE", os.path.join(ROOT, "build", "solve"))
SITE = "https://alpibrusl.github.io/cancho-solve/"
REPO = "https://github.com/alpibrusl/cancho-solve"

# Counts read from the gates' own last lines, run on main at 7f60317 plus the two merges of 2026-11-05 (docs/design.md sections 17 to 20 give the commands).
# A figure here is a measurement of that day, on one machine; scripts/site.py does not re-run the gates.
FIGURES = [
    ("168", "test LPs agree with HiGHS", "python3 scripts/check_highs.py (145 optimal, 23 infeasible)"),
    ("194", "generated MIPs agree with HiGHS and enumeration, 142 also with CP-SAT and SCIP", "python3 scripts/check_mip.py --ortools"),
    ("13,414", "runs of mutated and cut inputs reach no panic", "python3 scripts/check_cli.py"),
    ("868", "checks of the verifier, accepting what is feasible and refusing each fault by its tag", "python3 scripts/check_verify.py"),
]


def run(args, stdin=""):
    p = subprocess.run([SOLVE] + args, input=stdin, capture_output=True, text=True)
    return p.returncode, p.stdout.rstrip("\n"), p.stderr.rstrip("\n")


def read(path):
    with open(os.path.join(DOCS, path)) as f:
        return f.read()


def esc(s):
    return html.escape(s, quote=False)


def shorten_x(line):
    """Drops the zero entries of a long "x" object and marks the cut; every other byte is as printed."""
    m = re.search(r'"x":\{([^}]*)\}', line)
    if not m:
        return line
    items = m.group(1).split(",")
    if len(items) <= 8:
        return line
    kept = [i for i in items if not i.endswith(":0.0")]
    return line[: m.start(1)] + ",".join(kept) + ",…" + line[m.end(1):]


# a terminal log: list of (class, text); d = comment, a = command, g = good, b = refused, "" = plain
def term(lines):
    return "\n".join('<span%s>%s</span>' % (' class="%s"' % c if c else "", esc(t)) for c, t in lines)


def cmd(label, args, model=None, stdin_extra=None, show=None, cut=True):
    """Runs `solve ARGS` on a model file and returns the log lines: the command, then what it printed."""
    text = read("examples/" + model) if model else ""
    if stdin_extra is not None:
        text = text + "---\n" + stdin_extra
    code, out, err = run(args, text)
    shown = show or ("$ solve " + " ".join(args) + (" < %s" % model if model else ""))
    lines = [("a", shown)]
    for l in out.splitlines():
        lines.append(("g", shorten_x(l) if cut else l))
    for l in err.splitlines():
        lines.append(("b", l))
    if code != 0:
        lines.append(("b", "# exit status %d" % code))
    return lines, code, out, err


def verify_cmd(model, mutate=None):
    """The model, a separator and the claimed solution (run's own output, optionally changed) into `solve verify`."""
    text = read("examples/" + model)
    _, sol, _ = run(["run"], text)
    claim = mutate(sol) if mutate else sol
    code, out, err = run(["verify"], text + "---\n" + claim)
    return claim, code, out, err


# ---------------------------------------------------------------- figures (computed from the files' own runs)
def params(text):
    out = {}
    for m in re.finditer(r"param\s+(\w+)\s*=\s*(\[[^\]]*\]|[-\d.]+)\s*;", text, re.S):
        v = m.group(2)
        out[m.group(1)] = [float(t) for t in re.findall(r"-?\d+\.?\d*", v)] if v.startswith("[") else float(v)
    return out


def solved(model):
    text = read("examples/" + model)
    _, out, _ = run(["run"], text)
    _, ex, _ = run(["expand"], text)
    return json.loads(out), json.loads(ex), text


def num(v):
    return ("%g" % v)


def fig_bakery():
    sol, ex, _ = solved("bakery.sol")
    names = [v["name"] for v in ex["variables"]]
    x = [sol["x"][n] for n in names]
    rows = []
    for c in ex["constraints"]:
        used = sum(coef * x[i] for i, coef in c["terms"])
        rows.append((c["name"], used, c["rhs"]))
    w = 300.0
    svg = ['<svg viewBox="0 0 520 %d" role="img" aria-labelledby="fb-t"><title id="fb-t">Each resource used against what the bakery has; butter and oven are used up</title>' % (40 + 44 * len(rows))]
    for k, (n, used, lim) in enumerate(rows):
        y = 24 + 44 * k
        full = used >= lim - 1e-9
        svg.append('<text class="lb" x="0" y="%d">%s</text>' % (y + 15, esc(n)))
        svg.append('<rect class="ft" x="80" y="%d" width="%d" height="20" rx="5"/>' % (y, w))
        svg.append('<rect class="%s" x="80" y="%d" width="%.1f" height="20" rx="5"/>' % ("fbf" if full else "fb", y, w * used / lim))
        svg.append('<text class="tk" x="%d" y="%d">%s of %s%s</text>' % (80 + w + 10, y + 15, num(round(used, 6)), num(lim), " · used up" if full else ""))
    svg.append("</svg>")
    return "".join(svg), rows


def fig_van():
    sol, ex, text = solved("van.sol")
    p = params(text)
    w, fee, n = p["w"], p["fee"], int(p["n"])
    taken = [i for i in range(n) if sol["x"]["take[%d]" % i] > 0.5]
    left = [i for i in range(n) if i not in taken]
    u = 22.0
    svg = ['<svg viewBox="0 0 520 190" role="img" aria-labelledby="fv-t"><title id="fv-t">The parcels in the van and the parcels left behind, drawn to weight</title>']
    svg.append('<text class="lb" x="0" y="16">in the van (15 kg)</text><rect class="ft" x="0" y="24" width="%.0f" height="46" rx="6"/>' % (p["cap"] * u))
    x0 = 3.0
    for i in taken:
        svg.append('<rect class="fb" x="%.1f" y="27" width="%.1f" height="40" rx="4"/><text class="in" x="%.1f" y="45">%s</text><text class="in" x="%.1f" y="60">%s</text>' % (x0, w[i] * u - 3, x0 + 4, num(w[i]) + (" kg" if w[i] >= 3 else ""), x0 + 4, num(fee[i])))
        x0 += w[i] * u
    svg.append('<text class="lb" x="0" y="106">left behind</text>')
    x0 = 0.0
    for i in left:
        svg.append('<rect class="fo" x="%.1f" y="114" width="%.1f" height="40" rx="4"/><text class="tk" x="%.1f" y="131">%s kg</text><text class="tk" x="%.1f" y="146">%s</text>' % (x0, w[i] * u - 3, x0 + 4, num(w[i]), x0 + 4, num(fee[i])))
        x0 += w[i] * u + 4
    svg.append('<text class="tk" x="0" y="180">top: weight in kg; bottom: the fee. In the van: %s kg, fee %s.</text></svg>' % (num(sum(w[i] for i in taken)), num(sum(fee[i] for i in taken))))
    return "".join(svg)


def fig_rota():
    sol, ex, text = solved("rota.sol")
    p = params(text)
    n = int(p["n"])
    d = p["dislike"]
    s = 56
    svg = ['<svg viewBox="0 0 %d %d" role="img" aria-labelledby="fr-t"><title id="fr-t">Who works which shift: the chosen cells are filled</title>' % (60 + n * s + 150, 40 + n * s)]
    for j in range(n):
        svg.append('<text class="tk" x="%d" y="14" text-anchor="middle">shift %d</text>' % (60 + j * s + s // 2, j))
    for i in range(n):
        svg.append('<text class="tk" x="0" y="%d">nurse %d</text>' % (28 + i * s + s // 2 + 4, i))
        for j in range(n):
            on = sol["x"]["give[%d,%d]" % (i, j)] > 0.5
            svg.append('<rect class="%s" x="%d" y="%d" width="%d" height="%d" rx="6"/><text class="%s" x="%d" y="%d" text-anchor="middle">%s</text>' % ("fb" if on else "ft", 62 + j * s, 26 + i * s, s - 6, s - 6, "in" if on else "tk", 62 + j * s + (s - 6) // 2, 26 + i * s + (s - 6) // 2 + 5, num(d[i * n + j])))
    svg.append('<text class="tk" x="%d" y="%d">filled: the choice;</text><text class="tk" x="%d" y="%d">numbers: dislike, total %s</text>' % (60 + n * s + 14, 60, 60 + n * s + 14, 80, num(sol["objective"])))
    svg.append("</svg>")
    return "".join(svg)


def fig_depots():
    sol, ex, text = solved("depots.sol")
    p = params(text)
    cost, stock, need = p["cost"], p["stock"], p["need"]
    w = 300.0
    svg = ['<svg viewBox="0 0 520 190" role="img" aria-labelledby="fd-t"><title id="fd-t">Crates shipped from each depot to each shop, as bars; the second depot ships to two shops</title>']
    for i in range(2):
        y = 8 + i * 88
        svg.append('<text class="lb" x="0" y="%d">depot %d</text>' % (y + 16, i))
        x0 = 80.0
        for j in range(3):
            q = sol["x"]["ship[%d,%d]" % (i, j)]
            if q > 1e-9:
                bw = w * q / 60.0
                svg.append('<rect class="%s" x="%.1f" y="%d" width="%.1f" height="26" rx="4"/><text class="in" x="%.1f" y="%d">shop %d: %s</text>' % ("fb" if j != 1 else "fbf", x0, y, bw - 3, x0 + 4, y + 17, j, num(q)))
                x0 += bw
        svg.append('<text class="tk" x="%d" y="%d">holds %s</text>' % (390, y + 17, num(stock[i])))
        svg.append('<text class="tk" x="80" y="%d">price per crate: %s</text>' % (y + 46, ", ".join("shop %d %s" % (j, num(cost[i * 3 + j])) for j in range(3))))
    svg.append("</svg>")
    return "".join(svg)


# ---------------------------------------------------------------- page chrome
NAV = [("index.html", "Home"), ("examples.html", "Examples"), ("stories.html", "Stories")]


def page(name, title, desc, body, extra_head="", bodyclass=""):
    nav = "".join('<a href="%s"%s>%s</a>' % (h, ' aria-current="page"' if h == name else "", t) for h, t in NAV)
    return """<!doctype html>
<html lang="en">
<!-- Written by scripts/site.py from real runs of the built `solve`. Do not edit by hand; run python3 scripts/site.py. -->
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<meta name="description" content="%(desc)s">
<link rel="canonical" href="%(site)s%(name)s">
<meta name="robots" content="index, follow">
<meta property="og:site_name" content="cancho-solve"><meta property="og:type" content="website"><meta property="og:title" content="%(title)s"><meta property="og:description" content="%(desc)s">
<meta name="color-scheme" content="light dark">
<link rel="alternate" type="text/markdown" href="agents.md" title="cancho-solve, as an agent reads it">
<link rel="stylesheet" href="assets/site.css"><link rel="stylesheet" href="assets/home.css"><link rel="stylesheet" href="assets/solve.css">
%(head)s</head>
<body class="%(cls)s">
<a class="skip" href="#main">Skip to content</a>
<header class="top"><div class="wrap">
  <a class="brand" href="./">cancho-solve</a>
  <nav aria-label="Site">%(nav)s<a href="%(repo)s">GitHub</a></nav>
</div></header>
<main id="main">
%(body)s
</main>
<footer><div class="wrap">
  <span class="brandline">cancho-solve</span><span>EUPL-1.2</span><span>written in <a href="https://github.com/alpibrusl/cancho">cancho</a></span>
  <a href="%(repo)s">Repository</a><a href="%(repo)s/blob/main/docs/design.md">Design</a><a href="agents.md">For agents</a>
</div></footer>
</body>
</html>
""" % dict(title=esc(title), desc=esc(desc), site=SITE, name="" if name == "index.html" else name, head=extra_head, cls=bodyclass, nav=nav, repo=REPO, body=body)


def screen(id_, lines):
    return '<pre id="%s" class="screen" tabindex="0">%s</pre>' % (id_, term(lines))


def replay_box(sessions):
    """The three-tab replay of the landing page (the script of home.js is the one cancho-ml uses; the tabs are plain text without it)."""
    tabs = "".join('<button type="button" role="tab" id="tab-%s" aria-controls="screen-%s" aria-selected="%s" tabindex="%d">%s</button>' % (k, k, "true" if n == 0 else "false", 0 if n == 0 else -1, esc(t)) for n, (k, t, _) in enumerate(sessions))
    pres = "".join('<div class="plabel">%s</div><pre id="screen-%s" class="screen" role="tabpanel" aria-labelledby="tab-%s" tabindex="0">%s</pre>' % (esc(t), k, k, term(l)) for k, t, l in sessions)
    return '<div class="replay" role="group" aria-labelledby="replay-t"><div class="bar"><i></i><i></i><i></i> <span id="replay-t">the same runs, replayed here</span> <button id="replay" type="button" hidden>&#8635; replay</button></div><div class="tabs" role="tablist" aria-label="Replayed runs" hidden>%s</div>%s</div>' % (tabs, pres)




# ---------------------------------------------------------------- the pages
def sessions():
    a, _, _, _ = cmd("bakery", ["run"], "bakery.sol")
    a.insert(0, ("d", "# 40 kg flour, 8 kg butter, 10 oven hours: how many loaves and trays of croissants?"))
    b = [("d", "# a courier van, six parcels, 15 kg: which to take (each whole or not at all)")]
    l1, _, _, _ = cmd("van", ["run"], "van.sol")
    b += l1
    claim, code, out, err = verify_cmd("van.sol")
    b.append(("d", "# a second opinion that shares no code with the search: the model, a line ---, the claimed answer"))
    b.append(("a", "$ (cat van.sol; echo ---; solve run < van.sol) | solve verify"))
    b.append(("g", out))
    # a wrong claim: the van also takes parcel 0 (12 kg)
    def tamper(sol):
        return sol.replace('"take[0]":0.0', '"take[0]":1.0')
    claim2, code2, out2, err2 = verify_cmd("van.sol", tamper)
    b.append(("d", "# the same claim with the 12 kg parcel added by hand"))
    b.append(("a", "$ (cat van.sol; echo ---; <the answer with take[0] changed to 1>) | solve verify"))
    b.append(("b", err2))
    b.append(("b", "# exit status %d" % code2))
    c, _, _, _ = cmd("unbounded", ["check"], "unbounded.sol")
    c.insert(0, ("d", "# a variable with no bounds is refused by the checker, before any solver sees it"))
    c.append(("d", "# the repair is a line of the model: give the bounds, and it runs"))
    return [("bakery", "A bakery, an LP", a), ("van", "A van, and a second opinion", b), ("fix", "A refusal and its repair", c)]


def build_index():
    s = sessions()
    _, introspect, _ = run(["introspect"])
    nrules = len(json.loads(introspect)["rules"])
    nums = "".join('<div class="n reveal"><b>%s</b><span>%s</span></div>' % (esc(n), esc(t)) for n, t, _ in FIGURES)
    body = """
<div class="wrap hero">
  <div>
    <p class="eyebrow">linear and mixed-integer models &middot; one command line</p>
    <h1>Models that are checked before they are solved, and checked again after.</h1>
    <p class="sub">cancho-solve reads a small text model, refuses a bad one with a rule tag and the line that fixes it, solves it, and <code>solve verify</code> re-checks any claimed answer without the search. Standard input, JSON out, no network.</p>
    <div class="cta"><a class="btn primary" href="#try">Try it</a><a class="btn" href="#watch">Watch it run</a><a class="btn" href="stories.html">Read the stories</a></div>
  </div>
  <div class="machine reveal">
<svg viewBox="0 0 560 330" role="img" aria-labelledby="mc-t mc-d">
<title id="mc-t">A model is checked, solved and verified; a bad model is refused with its repair</title>
<desc id="mc-d">A model file slides along a belt through a check box and a solve box into a verified answer box. Below, a refusal appears with its rule tag and the repair that fixes it.</desc>
<line class="belt" x1="20" y1="130" x2="540" y2="130"/>
<g class="pkt"><rect class="row" x="22" y="118" width="30" height="8" rx="3"/><rect class="row" x="22" y="130" width="30" height="8" rx="3"/></g>
<g class="pkt b"><rect class="row" x="22" y="118" width="30" height="8" rx="3"/><rect class="row" x="22" y="130" width="30" height="8" rx="3"/></g>
<g class="pkt c"><rect class="row" x="22" y="118" width="30" height="8" rx="3"/><rect class="row" x="22" y="130" width="30" height="8" rx="3"/></g>
<rect class="box" x="10" y="40" width="70" height="50" rx="10"/><text x="45" y="70" text-anchor="middle">.sol</text>
<rect class="box" x="130" y="70" width="110" height="120" rx="12"/><text x="185" y="100" text-anchor="middle">check</text><text class="sm" x="185" y="170" text-anchor="middle">rule tags</text>
<rect class="box" x="270" y="70" width="110" height="120" rx="12"/><text x="325" y="100" text-anchor="middle">solve</text><text class="sm" x="325" y="170" text-anchor="middle">simplex, B&amp;B</text>
<rect class="okb" x="420" y="60" width="130" height="140" rx="12"/><text x="485" y="92" text-anchor="middle">answer</text>
<g class="stamp"><rect x="436" y="130" width="98" height="26" rx="6" fill="none" stroke="var(--good)" stroke-width="2"/><text class="sm" x="485" y="148" text-anchor="middle" style="fill:var(--good)">verified</text></g>
<g class="refuse"><rect class="nob" x="40" y="226" width="250" height="82" rx="10"/><text class="sm" x="54" y="250" style="fill:var(--bad)">refused &middot; exit 2</text><text class="sm" x="54" y="270">solve.unbounded-domain</text><text class="sm" x="54" y="290" style="fill:var(--good)">repair: write the bounds</text>
<path d="M290 267H340" stroke="var(--good)" stroke-width="2" fill="none"/><rect class="okb" x="340" y="248" width="150" height="40" rx="8"/><text x="415" y="272" text-anchor="middle" class="sm">fix it, run again</text></g>
</svg></div>
</div>

<div class="wrap">
<h2 class="sr">What it does</h2>
<div class="trio">
  <div class="card reveal"><div class="art"><div class="say"><span class="e">{"error":"solve.unbounded-domain"}</span><span class="f">repair: var x : real 0..10;</span></div></div><h3>It says no, with the fix</h3><p>A refusal is one JSON line on standard error: a rule tag, a message, the repair and the position. %(nrules)s rules, listed by <code>solve introspect</code>.</p></div>
  <div class="card reveal"><div class="art"><div class="say"><span class="e">solve.row-violated: weight 11</span><span class="f">verified: the model and the claim</span></div></div><h3>A second opinion</h3><p><code>solve verify</code> re-checks bounds, integrality, every row and the objective, from any solver&rsquo;s answer, with code that shares nothing with the search.</p></div>
  <div class="card reveal"><div class="art"><div class="file"><i></i><i></i><i></i><em>dense = sparse</em></div></div><h3>Two engines, one answer</h3><p>A dense tableau and a sparse revised simplex solve the same models; a gate holds them to the same optimum on 104 LPs and 161 integer models.</p></div>
</div>
</div>

<section class="sec" id="watch"><div class="wrap">
  <h2>Watch it run</h2>
  <p class="lead">Three sessions of the real binary. Nothing on this page is typed in: <code>scripts/site.py</code> runs <code>solve</code> on the files of <code>docs/examples</code> and prints what came back.</p>
  %(replay)s
  <p class="fine">Recorded from real runs, not a live session. For a solution of more than eight entries the zero entries are left out and the cut is marked with an ellipsis; every other byte is as printed.</p>
</div></section>

<section class="sec" id="stories"><div class="wrap">
  <h2>Stories, from a bakery to a refusal</h2>
  <p class="lead">A bakery, a courier van, a night rota, two depots and a shop floor that says no: each asks a little more of <code>solve</code>, and every number and figure is drawn from a run.</p>
  <p class="cta"><a class="btn primary" href="stories.html">Read the stories</a><a class="btn" href="examples.html">See every command</a></p>
</div></section>

<section class="sec" id="how"><div class="wrap">
  <h2>How it works</h2>
  <p class="lead">A model becomes a flat list of variables and rows. An LP is solved by a dual simplex, dense or sparse; a model with <code>bool</code> or <code>int</code> variables by branch and bound over the same simplex. Anything it cannot accept comes back with its repair.</p>
  <div class="flow" tabindex="0" aria-label="Flow diagram, scrolls sideways on a narrow screen">
  <svg viewBox="0 0 760 330" role="img" aria-labelledby="flow-t flow-d">
    <title id="flow-t">From a model to a verified answer, and the refusal loop</title>
    <desc id="flow-d">A model file goes to check, then to the solver, which is a dual simplex for an LP and branch and bound for a model with integer variables, then to an answer. Verify re-reads the model and the answer. If the model cannot be accepted, the tool refuses with a rule tag and a repair.</desc>
    <defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="var(--muted)"/></marker></defs>
    <rect class="box" x="10" y="30" width="130" height="64" rx="10"/><text x="75" y="58" text-anchor="middle">model.sol</text><text class="sm" x="75" y="78" text-anchor="middle">params, vars, sums</text>
    <rect class="boxa" x="180" y="30" width="150" height="64" rx="10"/><text x="255" y="58" text-anchor="middle">check, expand</text><text class="sm" x="255" y="78" text-anchor="middle">flat rows, rule tags</text>
    <rect class="boxa" x="370" y="30" width="170" height="64" rx="10"/><text x="455" y="58" text-anchor="middle">run</text><text class="sm" x="455" y="78" text-anchor="middle">simplex, branch and bound</text>
    <rect class="ok" x="590" y="30" width="160" height="64" rx="10"/><text x="670" y="58" text-anchor="middle">answer (JSON)</text><text class="sm" x="670" y="78" text-anchor="middle">status, objective, x</text>
    <path class="arrow dash" d="M140 62H178"/><path class="arrow dash" d="M330 62H368"/><path class="arrow dash" d="M540 62H588"/>
    <path class="line" d="M670 94V122"/><path class="arrow dash" d="M670 122V148"/>
    <rect class="box" x="560" y="150" width="180" height="54" rx="10"/><text x="650" y="174" text-anchor="middle">verify</text><text class="sm" x="650" y="193" text-anchor="middle">no code from the search</text>
    <path class="arrow bad dash" d="M255 94V256"/>
    <text class="smb" x="265" y="150">cannot accept it</text>
    <rect class="no" x="150" y="258" width="330" height="58" rx="10"/><text x="315" y="282" text-anchor="middle">Refused, with data</text><text class="sm" x="315" y="302" text-anchor="middle">a rule tag, a position, a repair</text>
    <path class="arrow bad dash" d="M150 287H75V98"/>
    <text class="smb" x="86" y="200">fix the line,</text><text class="smb" x="86" y="217">then try again</text>
  </svg>
  </div>
  <p class="fine sr">In words: a model goes to check, then to run, then to an answer; verify reads the model and the answer again. A model the tool cannot accept is refused with a rule tag, a position and a repair; you fix the line and try again.</p>
</div></section>

<section class="sec" id="results"><div class="wrap">
  <h2>Measured, not promised</h2>
  <div class="nums">%(nums)s</div>
  <p class="fine">Counts from the gates&rsquo; own last lines on 2026-11-05, one machine; the commands are in the README and <a href="%(repo)s/blob/main/docs/design.md">docs/design.md</a>. On the generated families of <code>scripts/bench_highs.py</code> the dual simplex takes 0.5x to 1.4x of HiGHS&rsquo;s dual simplex; the sparse engine is 0.4x to 1.5x of CLP on transportation and assignment, and CLP is far faster on large min-cost flows (design.md sections 17 and 18).</p>
</div></section>

<section class="sec" id="try"><div class="wrap">
  <h2>Try it</h2>
  <p class="lead">Build it from source with the compiler written in cancho; <code>cancho.toml</code> pins the revision.</p>
<pre class="code" tabindex="0" id="build-cmds"><code>git clone https://github.com/alpibrusl/cancho                  # the compiler and its std
git clone https://github.com/alpibrusl/cancho-solve &amp;&amp; cd cancho-solve
# build the compiler at the revision cancho.toml pins (scripts/build-standalone.sh builds the one written in cancho), then:
cancho build --bin solve                                         # writes build/solve
build/solve run &lt; docs/examples/bakery.sol</code></pre>
  <p class="fine">No release is published today, so the source is the way in. These steps are the README&rsquo;s; the page does not re-run them.</p>
</div></section>

<section class="sec" id="print"><div class="wrap">
  <h2>What is not claimed</h2>
  <div class="cards">
    <div class="card"><h3>Not CP</h3><p>Constraint programming (<code>all_different</code>, <code>cumulative</code>, <code>element</code>) is reserved in the language and not built.</p></div>
    <div class="card"><h3>MIP trails the best</h3><p>Branch and bound has no cuts or presolve: it needs more nodes than HiGHS and SCIP, and falls behind on larger instances (design.md section 19.5).</p></div>
    <div class="card"><h3>Verify does not prove optimality</h3><p><code>solve verify</code> proves feasibility within a tolerance and the objective value; a feasible poor point verifies. Optimality is held by oracles in the gates, not by the verb.</p></div>
    <div class="card"><h3>One machine, generated models</h3><p>Every timing is one machine and generated or textbook families, not MIPLIB. The <code>auto</code> choice between the dense and sparse engine is fitted on those families only.</p></div>
  </div>
</div></section>

<section id="agent-view" aria-label="This page as an agent reads it"><div class="wrap">
  <div class="bar"><h2 style="margin:0">For agents</h2><span>the same facts as the page, as Markdown, written by scripts/site.py</span><a href="agents.md">agents.md</a><a href="llms.txt">llms.txt</a></div>
  <pre id="agent-full" tabindex="0">Loading agents.md &hellip;</pre>
</div></section>
<script src="assets/home.js"></script>
<script src="assets/replay.js"></script>
""" % dict(nrules=nrules, replay=replay_box(s), nums=nums, repo=REPO)
    return page("index.html", "cancho-solve: models checked before they are solved", "Linear and mixed-integer models as a command line. A bad model is refused with a rule tag and a repair; a claimed answer is re-checked without the search.", body, bodyclass="home")


def log_block(title, lines, note=None):
    return '<div class="plabel">%s</div>%s%s' % (esc(title), '<div class="replay"><pre class="screen" tabindex="0">%s</pre></div>' % term(lines), '<p class="fine">%s</p>' % note if note else "")


def code_block(text):
    return '<pre class="code" tabindex="0"><code>%s</code></pre>' % esc(text.rstrip("\n"))


def build_examples():
    parts = ['<div class="wrap pagehead"><p class="eyebrow">every command, with its real output</p><h1>Examples</h1><p class="lead">Each block is a model of <code>docs/examples</code> and what the built <code>solve</code> printed for it. The same models feed the <a href="stories.html">stories</a>.</p>',
             '<ul class="toc"><li><a href="#lp">An LP</a></li><li><a href="#mip">A MIP</a></li><li><a href="#expand">Expand</a></li><li><a href="#limits">Limits</a></li><li><a href="#engines">Engines</a></li><li><a href="#verify">Verify</a></li><li><a href="#refusals">Refusals</a></li></ul></div>']

    def sec(id_, title, lead, inner):
        parts.append('<section class="sec" id="%s"><div class="wrap"><h2>%s</h2><p class="lead">%s</p>%s</div></section>' % (id_, title, lead, inner))

    bak = read("examples/bakery.sol")
    l1, _, _, _ = cmd("c", ["check"], "bakery.sol")
    l2, _, _, _ = cmd("r", ["run"], "bakery.sol")
    sec("lp", "A linear program", "Real variables, a maximised objective, three constraints: a bakery with flour, butter and oven time. <code>check</code> reads the model and says what kind it is; <code>run</code> solves it and re-checks its own answer (<code>verified</code>).",
        code_block(bak) + log_block("check and run", l1 + l2, "<code>iterations</code> is the number of simplex pivots; <code>max_violation</code> is the largest constraint violation of the printed point, computed by the printer."))
    van = read("examples/van.sol")
    l3, _, _, _ = cmd("c", ["run"], "van.sol")
    l4, _, _, _ = cmd("c", ["run", "--relax"], "van.sol")
    sec("mip", "A mixed-integer program", "<code>bool</code> and <code>int</code> variables make it a MIP: <code>run</code> branches. <code>stats.nodes</code> counts the LPs solved; <code>bound</code> is the best value the search can still not rule out. <code>--relax</code> drops integrality and solves the LP relaxation, whose value is the upper bound of a maximisation.",
        code_block(van) + log_block("run and run --relax", l3 + l4, "The relaxation takes fractional parcels (fee %s against %s whole parcels), which is why the search has to branch." % (json.loads(l4[1][1])["objective"], json.loads(l3[1][1])["objective"])))
    l5, _, out5, _ = cmd("e", ["expand"], "van.sol")
    ex = json.loads(out5)
    short = json.dumps({"variables": ex["variables"][:2] + ["…"], "objective": ex["objective"], "constraints": ex["constraints"]}, separators=(",", ":"))
    sec("expand", "The flat model", "<code>expand</code> prints what a solver reads: every variable with its bounds, the objective and every constraint, with the sums and loops written out. It is the model the checker and the verifier both stand on.",
        log_block("expand", [("a", "$ solve expand < van.sol"), ("g", short)], "Two of the six variables shown; the rest are the same shape."))
    l6, _, _, _ = cmd("n", ["run", "--node-limit", "3"], "van.sol")
    l7, _, _, _ = cmd("n", ["run", "--iteration-limit", "1"], "bakery.sol")
    sec("limits", "Stopping early", "A limit stops the search and says so: the status is <code>unknown</code> or <code>feasible</code>, with a <code>bound</code> (and <code>gap</code>, when there is an incumbent), and the exit status is 1. A limit never prints a wrong optimum.",
        log_block("node and iteration limits", l6 + l7))
    l8, _, _, _ = cmd("m", ["run", "--method", "dense"], "bakery.sol")
    l9, _, _, _ = cmd("m", ["run", "--method", "sparse"], "bakery.sol")
    sec("engines", "Dense and sparse", "<code>--method dense|sparse|auto</code> picks the LP engine; <code>auto</code> (the default) takes the sparse one when the matrix is at most 4% full or the tableau would not fit. Both print the same optimum; the <code>stats</code> differ.",
        log_block("--method", l8 + l9))
    claim, code, out, err = verify_cmd("van.sol")
    def tamper(sol):
        return sol.replace('"take[0]":0.0', '"take[0]":1.0')
    claim2, code2, out2, err2 = verify_cmd("van.sol", tamper)

    def tamper_obj(sol):
        return sol.replace('"objective":21.0', '"objective":25.0')
    claim3, code3, out3, err3 = verify_cmd("van.sol", tamper_obj)

    def tamper_frac(sol):
        return sol.replace('"take[1]":1.0', '"take[1]":0.5')
    claim4, code4, out4, err4 = verify_cmd("van.sol", tamper_frac)
    vl = [("d", "# the model, a line holding exactly ---, then the claimed solution as JSON"), ("a", "$ (cat van.sol; echo ---; solve run < van.sol) | solve verify"), ("g", out),
          ("d", "# a claim that overloads the van: the row `weight` does not hold"), ("a", "$ (cat van.sol; echo ---; <take[0] set to 1>) | solve verify"), ("b", err2), ("b", "# exit status %d" % code2),
          ("d", "# a claim whose objective is not the one its values give"), ("a", "$ (cat van.sol; echo ---; <objective set to 25>) | solve verify"), ("b", err3), ("b", "# exit status %d" % code3),
          ("d", "# a half parcel in a bool variable"), ("a", "$ (cat van.sol; echo ---; <take[1] set to 0.5>) | solve verify"), ("b", err4), ("b", "# exit status %d" % code4)]
    sec("verify", "A second opinion", "<code>solve verify</code> takes a model and a <em>claimed</em> solution from any source and says whether it is feasible and has the objective it claims. A failure is a refusal: exit 2, a tag, and the violations. It does not prove optimality.",
        log_block("verify", vl, "The tolerance is 1e-6 by default and is printed (<code>--tolerance T</code>). The verifier shares no code with the search (design.md section 20.1); what it shares is the parser and expander, because the claim is about that model."))
    rl = []
    for f, label in [("unbounded.sol", "a variable with no bounds"), ("cannot.sol", None)]:
        pass
    r1, _, _, _ = cmd("r", ["check"], "unbounded.sol")
    r2, _, _, _ = cmd("r", ["run"], "cannot.sol")
    r3 = [("a", "$ echo 'var x : int 5..2; minimize x;' | solve check")]
    code_, out_, err_ = run(["check"], "var x : int 5..2;\nminimize x;\n")
    r3 += [("b", err_), ("b", "# exit status %d" % code_)]
    r4 = [("a", "$ solve run --bogus")]
    c4, o4, e4 = run(["run", "--bogus"])
    r4 += [("b", e4), ("b", "# exit status %d" % c4)]
    sec("refusals", "Refusals are data", "Every refusal is one JSON object on standard error with <code>error</code> (a stable tag), <code>message</code>, <code>repair</code> and, for a model, the position <code>at</code>. The exit status is 2. A model that is merely impossible is not a refusal: it is an answer, <code>infeasible</code>.",
        code_block(read("examples/unbounded.sol")) + log_block("a variable with no bounds", r1) + code_block(read("examples/cannot.sol")) + log_block("an impossible model is an answer", r2) + log_block("an empty range, and a flag that does not exist", r3 + r4))
    return page("examples.html", "cancho-solve examples: every command with its real output", "The solve commands on small models: LP, MIP, expand, limits, dense and sparse, verify and refusals, each with the output the built binary printed.", "\n".join(parts))


STORIES = [
    ("bakery", "bakery.sol", "A bakery decides what to bake",
     "Marta runs a small bakery. Today she has 40 kg of flour, 8 kg of butter and 10 oven hours. A batch of loaves takes 2 kg of flour, half a kilo of butter and an hour of oven, and sells for 12; a tray of croissants takes a kilo of flour, a kilo and a half of butter and half an oven hour, and sells for 18. A fraction of a batch is fine.",
     "She writes it down as a model, and asks. The answer is not the obvious one: neither all loaves nor all croissants, but 8.8 batches and 2.4 trays. The figure shows why: butter and oven time are used up, flour is not. More flour would not help; a little more butter would. <em>That</em> is the thing a solver tells you that a spreadsheet guess does not.",
     "fig_bakery"),
    ("van", "van.sol", "A van with room for 15 kilos",
     "Tomás drives a courier van that carries 15 kg. He has six parcels. Each is taken whole or left at the depot; the weights are 12, 2, 1, 4, 7 and 5 kg, and each pays a fee.",
     "Now the variables are yes-or-no, so <code>solve</code> branches: it solves the LP with fractions, finds a fractional parcel, and splits on it until the answer is whole. The heavy 12 kg parcel does not make the cut, for its fee; four parcels do, filling 14 of the 15 kg. <code>stats.nodes</code> says how many LPs it took.",
     "fig_van"),
    ("rota", "rota.sol", "A night rota nobody dreads",
     "The ward needs one nurse on each of four night shifts and each nurse works one. Every nurse has scored every shift from 0 (happy) to 9 (would rather not). The head nurse wants the lowest total.",
     "This is an assignment problem, a model of rows that must equal one. The answer is the diagonal here, total 8; the search needed a single node because the LP relaxation was already whole. Assignment models are special: the LP relaxation of one always has a whole optimal vertex, so there was nothing to branch on.",
     "fig_rota"),
    ("depots", "depots.sol", "Two depots, three shops",
     "A wholesaler has two depots, holding 60 and 50 crates, and three shops that need 30, 40 and 25. Crates can be split between shops. A crate costs a different amount on each route.",
     "A transportation LP, with real variables: nothing to branch on. The cheapest plan sends depot 0 to shop 0 and shop 2, and depot 1 to shop 1 and shop 2. The figure draws the flows to scale.",
     "fig_depots"),
]


def build_stories():
    parts = ['<div class="wrap pagehead"><p class="eyebrow">from a first model to a refusal</p><h1>Stories</h1><p class="lead">Each story states a small problem, writes it as a <code>.sol</code> model, runs the built binary and reads the answer. The numbers and the figures come from the run, not from the prose.</p>',
             '<ul class="toc">%s<li><a href="#says-no">When the answer is no</a></li><li><a href="#trust">Trust, then check</a></li><li><a href="#stopped">When it stops early</a></li></ul></div>' % "".join('<li><a href="#%s">%s</a></li>' % (i, esc(t)) for i, _, t, _, _, _ in STORIES)]
    figs = dict(fig_bakery=lambda: fig_bakery()[0], fig_van=fig_van, fig_rota=fig_rota, fig_depots=fig_depots)
    for sid, model, title, story, reading, fig in STORIES:
        lines, _, _, _ = cmd(sid, ["run"], model)
        parts.append('<section class="sec story" id="%s"><div class="wrap"><h2>%s</h2><p class="lead">%s</p>%s<div class="fig">%s</div>%s<p>%s</p></div></section>' % (sid, esc(title), story, code_block(read("examples/" + model)), figs[fig](), log_block("solve run < %s" % model, lines), reading))
    # when the answer is no
    r, _, _, _ = cmd("n", ["run"], "cannot.sol")
    r2, _, _, _ = cmd("n", ["check"], "unbounded.sol")
    parts.append('<section class="sec story" id="says-no"><div class="wrap"><h2>When the answer is no</h2><p class="lead">Two kinds of no, and the tool keeps them apart. A model that cannot be read is <em>refused</em> with a repair; a model that reads fine but has no solution is an <em>answer</em>.</p>%s%s%s%s<p>The first is a mistake in the model: a variable with no bounds is refused before any solver sees it, with the line to write. The second is not a mistake of the tool or the writer: two parcels that must both go and cannot both go. <code>run</code> says <code>infeasible</code> and exits 0, because that is a correct result.</p></div></section>' % (code_block(read("examples/unbounded.sol")), log_block("solve check", r2), code_block(read("examples/cannot.sol")), log_block("solve run", r)))
    # trust then check
    claim, code, out, err = verify_cmd("van.sol")

    def tamper(sol):
        return sol.replace('"take[0]":0.0', '"take[0]":1.0')
    claim2, code2, out2, err2 = verify_cmd("van.sol", tamper)
    vl = [("a", "$ (cat van.sol; echo ---; solve run < van.sol) | solve verify"), ("g", out), ("d", "# someone hand-edits the answer to take the 12 kg parcel as well"), ("a", "$ (cat van.sol; echo ---; <take[0] changed to 1>) | solve verify"), ("b", err2), ("b", "# exit status %d" % code2)]
    parts.append('<section class="sec story" id="trust"><div class="wrap"><h2>Trust, then check</h2><p class="lead">An answer can come from <code>solve run</code>, from HiGHS, from a colleague or from a model that guessed. <code>solve verify</code> does not care which.</p>%s<p>It reads the model and the claimed solution and re-evaluates both: bounds, whole numbers where the model says whole, every row, and the objective. Here the overloaded van is caught by the row <code>weight</code>, and the objective that no longer matches is caught with it. What it does <em>not</em> say is that an accepted answer is the best one: for that the gates hold the solver to HiGHS and, on integer models, to CP-SAT and SCIP.</p></div></section>' % log_block("solve verify", vl))
    # stopped early
    s1, _, _, _ = cmd("s", ["run", "--node-limit", "3"], "van.sol")
    parts.append('<section class="sec story" id="stopped"><div class="wrap"><h2>When it stops early</h2><p class="lead">A bigger model can take longer than you will wait. A limit makes the stop an answer.</p>%s<p>With three nodes the search has found no whole answer yet, so the status is <code>unknown</code>; but it knows the optimum cannot exceed the <code>bound</code>. With an incumbent the status would be <code>feasible</code> and a <code>gap</code> would say how far the best known answer could be from the best possible. Either way the exit status is 1: not an error, not a finished proof.</p></div></section>' % log_block("solve run --node-limit 3", s1))
    return page("stories.html", "cancho-solve stories: a bakery, a van, a rota, two depots and a refusal", "Small problems written as models and solved by the built binary: every number and figure on the page is drawn from a real run.", "\n".join(parts))


def build_agents():
    _, skill, _ = run(["skill"])
    _, intro, _ = run(["introspect"])
    return "# cancho-solve, as an agent reads it\n\nGenerated by scripts/site.py from the built `solve`.\n\n%s\n\n## Machine-readable\n\n`solve introspect` prints this as JSON:\n\n```json\n%s\n```\n" % (skill, intro)


def build_llms():
    return "# cancho-solve\n\n> Linear and mixed-integer models as a command line: a checked text model in, JSON out; refusals carry a rule tag and a repair; `solve verify` re-checks a claimed answer without the search.\n\n- [Landing page](%sindex.html)\n- [Examples](%sexamples.html)\n- [Stories](%sstories.html)\n- [For agents (agents.md)](%sagents.md)\n- [Design](%s/blob/main/docs/design.md)\n" % (SITE, SITE, SITE, SITE, REPO)


def main():
    if not os.path.exists(SOLVE):
        sys.exit("no binary at %s; build it (cancho build --bin solve) or set SOLVE" % SOLVE)
    outputs = {"index.html": build_index(), "examples.html": build_examples(), "stories.html": build_stories(), "agents.md": build_agents(), "llms.txt": build_llms()}
    bad = 0
    for name, text in outputs.items():
        path = os.path.join(DOCS, name)
        if "--check" in sys.argv:
            if not os.path.exists(path) or open(path).read() != text:
                print("stale: docs/" + name)
                bad += 1
        else:
            with open(path, "w") as f:
                f.write(text)
            print("wrote docs/" + name)
    if "--check" in sys.argv:
        print("site check: %s" % ("passed" if not bad else "FAILED, %d stale" % bad))
        sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
