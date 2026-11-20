/* SHCC Stats — static single-page app over data.json (built by build_site.py) */
(() => {
  "use strict";

  // ---------- data ----------
  let D; // raw data
  const M = { SEASON: 0, GRADE: 1, CAT: 2, FMT: 3, DATE: 4, ROUND: 5, OPP: 6, RES: 7, TEXT: 8 };
  const CATS = ["Men's", "Women's", "Juniors"];
  const FORMATS = ["One Day", "Two Day", "T20"];
  let byPlayer; // per-player row indexes

  const $app = document.getElementById("app");
  const $tip = document.getElementById("tip");

  // ---------- state ----------
  const store = {
    get(k, d) { try { const v = localStorage.getItem("shcc:" + k); return v === null ? d : v; } catch { return d; } },
    set(k, v) { try { localStorage.setItem("shcc:" + k, v); } catch { /* ignore */ } },
  };
  let cat = store.get("cat", "0"); // "all" | "0" | "1" | "2"
  const leadersState = { tab: "bat", season: "all", fmt: "all", min: null, sort: null, asc: false, limit: 50 };
  const playersState = { q: "", sort: "m", asc: false, limit: 100 };
  const recordsState = { fmt: "all" };
  const seasonState = { season: null };
  const profileState = { chart: "runs" };

  // ---------- helpers ----------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtN = (n) => (n == null ? "–" : n.toLocaleString("en-AU"));
  const fx = (n, d = 2) => (n == null || !isFinite(n) ? "–" : n.toFixed(d));
  const overs = (b) => `${Math.floor(b / 6)}.${b % 6}`;
  const fig = (w, r) => `${w}/${r}`;
  const hs = (r, no) => `${r}${no ? "*" : ""}`;
  const dateStr = (d) => {
    if (!d) return "–";
    const dt = new Date(d + "T00:00:00");
    return dt.toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric" });
  };
  const resCls = (r) => (r === "-" ? "X" : r);
  const resLabel = (r) => ({ W: "W", L: "L", D: "D", T: "T", "-": "–" }[r]);
  const pname = (p) => D.players[p][0];
  const isReal = (p) => !D.players[p][1];
  const plink = (p) => `<a class="nm" href="#/player/${p}">${esc(pname(p))}</a>`;
  const seasonLabel = (s) => D.seasons[s];
  const endYear = (s) => +seasonLabel(s).slice(0, 4) + 1;
  const span = (a, b) => (a == null ? "–" : a === b ? seasonLabel(a) : `${seasonLabel(a).slice(0, 4)}–${endYear(b)}`);
  const catOk = (mi) => cat === "all" || D.matches[mi][M.CAT] === +cat;
  const catName = () => (cat === "all" ? "All competitions" : CATS[+cat]);
  const boltSvg = '<svg class="b" aria-hidden="true"><use href="#bolt"/></svg>';
  const divider = (t) => `<div class="divider"><h2>${esc(t)}</h2></div>`;

  // ---------- aggregation ----------
  function blank() {
    return { m: 0, inn: 0, no: 0, runs: 0, balls: 0, rwb: 0, hs: -1, hsNo: 0, f50: 0, h100: 0, ducks: 0, fours: 0, sixes: 0,
      bb: 0, mdn: 0, rc: 0, wk: 0, bestW: -1, bestR: 0, w5: 0, ct: 0, wkc: 0, st: 0, ro: 0, first: null, last: null, seasons: null };
  }
  function derive(s) {
    const outs = s.inn - s.no;
    s.avg = outs > 0 ? s.runs / outs : null;
    s.sr = s.balls > 0 ? (s.rwb * 100) / s.balls : null;
    s.bavg = s.wk > 0 ? s.rc / s.wk : null;
    s.econ = s.bb > 0 ? (s.rc * 6) / s.bb : null;
    s.bsr = s.wk > 0 ? s.bb / s.wk : null;
    s.dis = s.ct + s.wkc + s.st;
    s.ns = s.seasons ? s.seasons.size : 0;
    s.hsSort = s.hs < 0 ? -1 : s.hs + (s.hsNo ? 0.5 : 0);
    s.bestSort = s.bestW < 0 ? -1 : s.bestW * 1000 - s.bestR;
    return s;
  }
  function addBat(s, r) {
    s.inn++; s.runs += r[2]; s.fours += r[4]; s.sixes += r[5];
    if (r[3] > 0) { s.balls += r[3]; s.rwb += r[2]; }
    if (r[6]) s.no++;
    if (r[2] >= 100) s.h100++; else if (r[2] >= 50) s.f50++;
    if (r[2] === 0 && !r[6]) s.ducks++;
    if (r[2] > s.hs || (r[2] === s.hs && r[6])) { s.hs = r[2]; s.hsNo = r[6]; }
  }
  function addBowl(s, r) {
    s.bb += r[2]; s.mdn += r[3]; s.rc += r[4]; s.wk += r[5];
    if (r[5] >= 5) s.w5++;
    if (r[5] > s.bestW || (r[5] === s.bestW && r[4] < s.bestR)) { s.bestW = r[5]; s.bestR = r[4]; }
  }
  function addField(s, r) { s.ct += r[2]; s.wkc += r[3]; s.st += r[4]; s.ro += r[5]; }
  function addApp(s, mi) {
    s.m++;
    const se = D.matches[mi][M.SEASON];
    if (s.first == null || se < s.first) s.first = se;
    if (s.last == null || se > s.last) s.last = se;
    (s.seasons ||= new Set()).add(se);
  }

  /* Official Play Cricket adjustment rows (see build_site.py official_adjustments):
     [profile, season, cat, m, inn, no, runs, 50s, 100s, ducks, 4s, 6s, balls, mdns, runsConc, wkts, 5w, ct, wkCt, st, ro, hs, hsNo, bestW, bestR]
     They carry matches Play Cricket counts but doesn't publish scorecards for, so totals match the official career figures. */
  const A = { P: 0, S: 1, CAT: 2 };
  function addAdj(s, r) {
    if (r[3] > 0 || r[4] > 0 || r[12] > 0) {
      const se = r[1];
      if (s.first == null || se < s.first) s.first = se;
      if (s.last == null || se > s.last) s.last = se;
      (s.seasons ||= new Set()).add(se);
    }
    s.m += r[3]; s.inn += r[4]; s.no += r[5]; s.runs += r[6]; s.f50 += r[7]; s.h100 += r[8]; s.ducks += r[9];
    s.fours += r[10]; s.sixes += r[11]; s.bb += r[12]; s.mdn += r[13]; s.rc += r[14]; s.wk += r[15]; s.w5 += r[16];
    s.ct += r[17]; s.wkc += r[18]; s.st += r[19]; s.ro += r[20];
    if (r[21] >= 0 && (r[21] > s.hs || (r[21] === s.hs && r[22]))) { s.hs = r[21]; s.hsNo = r[22]; }
    if (r[23] >= 0 && (r[23] > s.bestW || (r[23] === s.bestW && r[24] < s.bestR))) { s.bestW = r[23]; s.bestR = r[24]; }
  }

  const aggCache = new Map();
  /** Aggregate per key. keyFn(row) → key (default player). filter(mi) → bool; filter.adj(row) → bool. */
  function aggregate(filter, cacheKey, keyFn = (r) => r[1], adjKeyFn = (r) => r[A.P]) {
    if (cacheKey && aggCache.has(cacheKey)) return aggCache.get(cacheKey);
    const out = new Map();
    const get = (k) => { let s = out.get(k); if (!s) { s = blank(); out.set(k, s); } return s; };
    for (const r of D.app) if (filter(r[0])) addApp(get(keyFn(r)), r[0]);
    for (const r of D.bat) if (filter(r[0])) addBat(get(keyFn(r)), r);
    for (const r of D.bowl) if (filter(r[0])) addBowl(get(keyFn(r)), r);
    for (const r of D.field) if (filter(r[0])) addField(get(keyFn(r)), r);
    if (filter.adj) for (const r of D.adj) if (filter.adj(r)) addAdj(get(adjKeyFn(r)), r);
    out.forEach(derive);
    if (cacheKey) aggCache.set(cacheKey, out);
    return out;
  }
  function filterFor({ season = "all", fmt = "all" } = {}) {
    const f = (mi) => {
      const m = D.matches[mi];
      return (cat === "all" || m[M.CAT] === +cat) && (season === "all" || m[M.SEASON] === +season) && (fmt === "all" || m[M.FMT] === +fmt);
    };
    // Official totals aren't split by format, so they only apply to "All formats".
    if (fmt === "all") f.adj = (r) => (cat === "all" || r[A.CAT] === +cat) && (season === "all" || r[A.S] === +season);
    return f;
  }
  const agg = (opts = {}) => aggregate(filterFor(opts), `${cat}|${opts.season ?? "all"}|${opts.fmt ?? "all"}`);

  // ---------- small components ----------
  function board(title, items, more) {
    const body = items.length
      ? items.map((it, i) => `<div class="row"><span class="rk">${i + 1}</span>${it.name}<span class="val">${it.val}${it.small ? `<small>${it.small}</small>` : ""}</span>${it.sub ? `<span class="sub">${it.sub}</span>` : ""}</div>`).join("")
      : `<p class="empty">No data for this selection.</p>`;
    return `<section class="board"><h3>${esc(title)}</h3>${body}${more ? `<a class="more" href="${more}">Full list →</a>` : ""}</section>`;
  }
  function topBy(map, key, n, extra) {
    return [...map.entries()].filter(([p, s]) => isReal(p) && s[key] > 0 && (!extra || extra(s)))
      .sort((a, b) => b[1][key] - a[1][key]).slice(0, n);
  }
  function selectHtml(id, label, options, value) {
    return `<label class="field"><span class="eyebrow">${label}</span><select id="${id}">${options.map(([v, t]) => `<option value="${v}"${String(v) === String(value) ? " selected" : ""}>${esc(t)}</option>`).join("")}</select></label>`;
  }
  const seasonOptions = (allLabel = "All-time") => [["all", allLabel], ...D.seasons.map((s, i) => [i, s]).reverse()];
  const fmtOptions = [["all", "All formats"], ...FORMATS.map((f, i) => [i, f])];

  /** Sortable table. cols: {key,label,cls,fmt(s,row),sortVal(s),qual,left} */
  function sortableTable(el, { cols, rows, sort, asc, limit, onSort, onMore, rank = true, rowKey }) {
    const col = cols.find((c) => c.key === sort) || cols[0];
    const val = col.sortVal || ((r) => r[col.key]);
    const sorted = rows.slice().sort((a, b) => {
      const va = val(a), vb = val(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === "string") return asc ? va.localeCompare(vb) : vb.localeCompare(va);
      return asc ? va - vb : vb - va;
    });
    const shown = limit ? sorted.slice(0, limit) : sorted;
    const head = (rank ? '<th class="l">#</th>' : "") + cols.map((c) => `<th class="${c.left ? "l" : ""}${c.key === col.key ? " sorted" + (asc ? " asc" : "") : ""}">${c.nosort ? esc(c.label) : `<button data-k="${c.key}" title="Sort by ${esc(c.title || c.label)}">${esc(c.label)}</button>`}</th>`).join("");
    const body = shown.map((r, i) => `<tr>${rank ? `<td class="rk l">${i + 1}</td>` : ""}${cols.map((c) => `<td class="${c.left ? "l " : ""}${c.cls || ""}${c.key === col.key ? " key" : ""}">${c.fmt ? c.fmt(r) : esc(r[c.key])}</td>`).join("")}</tr>`).join("");
    el.innerHTML = `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body || `<tr><td class="l dim" colspan="${cols.length + 1}">No data for this selection.</td></tr>`}</tbody></table></div>
      <div class="table-foot"><span>${fmtN(shown.length)} of ${fmtN(sorted.length)}</span>${limit && sorted.length > limit ? '<button class="btn" data-more>Show more</button>' : ""}</div>`;
    el.querySelectorAll("th button").forEach((b) => b.addEventListener("click", () => {
      const k = b.dataset.k;
      const c = cols.find((x) => x.key === k);
      onSort(k, k === col.key ? !asc : !!c.asc);
    }));
    const mb = el.querySelector("[data-more]");
    if (mb && onMore) mb.addEventListener("click", onMore);
  }

  // ---------- pages ----------
  function pageHome() {
    const f = (mi) => catOk(mi);
    let played = 0, wins = 0, losses = 0;
    const seasonsSeen = new Set();
    const recent = [];
    D.matches.forEach((m, i) => {
      if (!f(i) || m[M.RES] === "-") return;
      played++; seasonsSeen.add(m[M.SEASON]);
      if (m[M.RES] === "W") wins++;
      if (m[M.RES] === "L") losses++;
      recent.push(i);
    });
    const all = agg();
    let runs = 0, wkts = 0, tons = 0, players = 0;
    all.forEach((s, p) => { runs += s.runs; wkts += s.wk; tons += s.h100; if (isReal(p) && s.m) players++; });

    const latest = D.seasons.length - 1;
    const cur = agg({ season: latest });
    const curRuns = topBy(cur, "runs", 5).map(([p, s]) => ({ name: plink(p), val: s.runs, small: `HS ${hs(s.hs, s.hsNo)}` }));
    const curWk = topBy(cur, "wk", 5).map(([p, s]) => ({ name: plink(p), val: s.wk, small: `BB ${fig(s.bestW, s.bestR)}` }));

    const atRuns = topBy(all, "runs", 5).map(([p, s]) => ({ name: plink(p), val: fmtN(s.runs), small: span(s.first, s.last) }));
    const atWk = topBy(all, "wk", 5).map(([p, s]) => ({ name: plink(p), val: fmtN(s.wk), small: span(s.first, s.last) }));
    const atM = topBy(all, "m", 5).map(([p, s]) => ({ name: plink(p), val: fmtN(s.m), small: span(s.first, s.last) }));
    const atCt = topBy(all, "dis", 5).map(([p, s]) => ({ name: plink(p), val: fmtN(s.dis), small: s.st ? `${s.st} st` : "" }));

    const last = recent.slice(-8).reverse();

    $app.innerHTML = `
      <section class="hero">
        <p class="eyebrow">SHCC ${boltSvg} Since ${esc(D.seasons[0])}</p>
        <h1 class="display">Club<span class="teal">Records</span></h1>
        <p class="lede">Every SHCC innings, spell and catch on record. ${esc(catName())}.</p>
      </section>
      <div class="tiles">
        <div class="tile"><span class="num">${fmtN(seasonsSeen.size)}</span><span class="eyebrow">Seasons</span></div>
        <div class="tile"><span class="num">${fmtN(played)}</span><span class="eyebrow">Matches</span></div>
        <div class="tile"><span class="num">${fmtN(wins)}<small>${played ? Math.round((wins / played) * 100) + "%" : ""}</small></span><span class="eyebrow">Wins</span></div>
        <div class="tile"><span class="num">${fmtN(players)}</span><span class="eyebrow">Players</span></div>
        <div class="tile"><span class="num">${fmtN(runs)}</span><span class="eyebrow">Runs</span></div>
        <div class="tile"><span class="num">${fmtN(wkts)}</span><span class="eyebrow">Wickets</span></div>
        <div class="tile"><span class="num">${fmtN(tons)}</span><span class="eyebrow">Centuries</span></div>
      </div>

      ${divider(`${seasonLabel(latest)} season`)}
      <div class="boards">
        ${board("Top batters", curRuns, `#/leaders?tab=bat&season=${latest}`)}
        ${board("Top bowlers", curWk, `#/leaders?tab=bowl&season=${latest}`)}
      </div>

      ${divider("All-time leaders")}
      <div class="boards">
        ${board("Most runs", atRuns, "#/leaders?tab=bat")}
        ${board("Most wickets", atWk, "#/leaders?tab=bowl")}
        ${board("Most matches", atM, "#/leaders?tab=app")}
        ${board("Most dismissals", atCt, "#/leaders?tab=field")}
      </div>

      ${divider("Latest results")}
      ${resultsTable(last, true)}
      <p class="note"><a class="more teal" href="#/seasons">All seasons →</a></p>
    `;
  }

  function resultsTable(list, showSeason) {
    if (!list.length) return '<p class="empty">No results.</p>';
    return `<div class="table-wrap"><table><thead><tr>
      <th class="l">Date</th><th class="l">Grade</th>${showSeason ? "" : '<th class="l">Round</th>'}<th class="l">Opponent</th><th class="l">Res</th><th class="l">Result</th></tr></thead><tbody>
      ${list.map((i) => { const m = D.matches[i]; return `<tr>
        <td class="l dim">${dateStr(m[M.DATE])}</td>
        <td class="l">${esc(D.grades[m[M.GRADE]])}</td>
        ${showSeason ? "" : `<td class="l dim">${esc(m[M.ROUND])}</td>`}
        <td class="l">${esc(m[M.OPP])}</td>
        <td class="l"><span class="res ${resCls(m[M.RES])}">${resLabel(m[M.RES])}</span></td>
        <td class="result-text">${esc(m[M.TEXT])}</td></tr>`; }).join("")}
      </tbody></table></div>`;
  }

  // Leaderboards
  const LB = {
    bat: {
      label: "Batting", minLabel: "Min innings", defMin: [20, 5], qualKey: "inn", def: "runs",
      cols: [
        { key: "name", label: "Player", left: true, asc: true, fmt: (r) => plink(r.p), sortVal: (r) => r.name },
        { key: "m", label: "M", title: "matches" }, { key: "inn", label: "Inn", title: "innings" }, { key: "no", label: "NO", title: "not outs" },
        { key: "runs", label: "Runs", fmt: (r) => fmtN(r.runs) },
        { key: "hs", label: "HS", title: "high score", fmt: (r) => hs(r.hs, r.hsNo), sortVal: (r) => r.hsSort },
        { key: "avg", label: "Avg", title: "average", qual: true, fmt: (r) => fx(r.avg) },
        { key: "sr", label: "SR", title: "strike rate", qual: true, fmt: (r) => fx(r.sr) },
        { key: "h100", label: "100s" }, { key: "f50", label: "50s" }, { key: "ducks", label: "0s", title: "ducks" },
        { key: "fours", label: "4s" }, { key: "sixes", label: "6s" },
        { key: "span", label: "Span", cls: "dim", nosort: true, fmt: (r) => span(r.first, r.last) },
      ],
      include: (s) => s.inn > 0,
    },
    bowl: {
      label: "Bowling", minLabel: "Min wickets", defMin: [20, 5], qualKey: "wk", def: "wk",
      cols: [
        { key: "name", label: "Player", left: true, asc: true, fmt: (r) => plink(r.p), sortVal: (r) => r.name },
        { key: "m", label: "M", title: "matches" },
        { key: "bb", label: "Overs", fmt: (r) => overs(r.bb) },
        { key: "mdn", label: "Mdns", title: "maidens" }, { key: "rc", label: "Runs", title: "runs conceded", fmt: (r) => fmtN(r.rc) },
        { key: "wk", label: "Wkts", title: "wickets" },
        { key: "best", label: "BB", title: "best bowling", fmt: (r) => (r.bestW >= 0 ? fig(r.bestW, r.bestR) : "–"), sortVal: (r) => r.bestSort },
        { key: "bavg", label: "Avg", title: "average", qual: true, asc: true, fmt: (r) => fx(r.bavg) },
        { key: "econ", label: "Econ", title: "economy", qual: true, asc: true, fmt: (r) => fx(r.econ) },
        { key: "bsr", label: "SR", title: "strike rate", qual: true, asc: true, fmt: (r) => fx(r.bsr, 1) },
        { key: "w5", label: "5W", title: "five-wicket hauls" },
        { key: "span", label: "Span", cls: "dim", nosort: true, fmt: (r) => span(r.first, r.last) },
      ],
      include: (s) => s.bb > 0 || s.wk > 0,
    },
    field: {
      label: "Fielding", minLabel: null, def: "dis",
      cols: [
        { key: "name", label: "Player", left: true, asc: true, fmt: (r) => plink(r.p), sortVal: (r) => r.name },
        { key: "m", label: "M", title: "matches" },
        { key: "ct", label: "Ct", title: "catches" }, { key: "wkc", label: "WK Ct", title: "keeper catches" },
        { key: "st", label: "St", title: "stumpings" }, { key: "ro", label: "RO", title: "run outs" },
        { key: "dis", label: "Dis", title: "dismissals (ct + wk ct + st)" },
        { key: "span", label: "Span", cls: "dim", nosort: true, fmt: (r) => span(r.first, r.last) },
      ],
      include: (s) => s.dis + s.ro > 0,
    },
    app: {
      label: "Matches", minLabel: null, def: "m",
      cols: [
        { key: "name", label: "Player", left: true, asc: true, fmt: (r) => plink(r.p), sortVal: (r) => r.name },
        { key: "m", label: "Matches" }, { key: "ns", label: "Seasons" },
        { key: "runs", label: "Runs", fmt: (r) => fmtN(r.runs) }, { key: "wk", label: "Wkts" }, { key: "ct", label: "Ct" },
        { key: "first", label: "Debut", cls: "dim", asc: true, fmt: (r) => (r.first != null ? seasonLabel(r.first) : "–") },
        { key: "last", label: "Last", cls: "dim", fmt: (r) => (r.last != null ? seasonLabel(r.last) : "–") },
      ],
      include: (s) => s.m > 0,
    },
  };

  function pageLeaders(params) {
    const st = leadersState;
    if (params.tab && LB[params.tab]) { if (st.tab !== params.tab) { st.sort = null; st.min = null; } st.tab = params.tab; }
    if (params.season != null) { st.season = params.season; st.min = null; }
    const conf = LB[st.tab];
    const sort = st.sort || conf.def;
    const minDefault = conf.defMin ? conf.defMin[st.season === "all" ? 0 : 1] : 0;
    const min = st.min ?? minDefault;

    $app.innerHTML = `
      <div class="page-head"><p class="eyebrow">${esc(catName())} ${boltSvg} ${st.season === "all" ? "All-time" : esc(seasonLabel(+st.season))}</p><h1 class="page-title">Leaderboards</h1></div>
      <div class="tabs" role="tablist">${Object.entries(LB).map(([k, v]) => `<button role="tab" data-tab="${k}" class="${k === st.tab ? "on" : ""}" aria-selected="${k === st.tab}">${v.label}</button>`).join("")}</div>
      <div class="controls">
        ${selectHtml("lb-season", "Season", seasonOptions(), st.season)}
        ${selectHtml("lb-fmt", "Format", fmtOptions, st.fmt)}
        ${conf.minLabel ? `<label class="field"><span class="eyebrow">${conf.minLabel}</span><input type="number" id="lb-min" min="0" value="${min}"></label>` : ""}
      </div>
      <div id="lb-table"></div>
      <p class="note">${st.fmt === "all" ? "Totals match each player's Play Cricket career figures (Club: Sydenham-Hillside)." : "Format splits are built from published scorecards, so they can be slightly below Play Cricket's overall totals."}${conf.minLabel ? ` ${conf.minLabel} applies when ranking by average, economy or strike rate. Strike rates use only innings with balls recorded.` : ""}</p>
    `;
    const data = agg({ season: st.season, fmt: st.fmt });
    const col = conf.cols.find((c) => c.key === sort);
    let rows = [...data.entries()].filter(([p, s]) => isReal(p) && conf.include(s)).map(([p, s]) => ({ ...s, p, name: pname(p) }));
    if (col && col.qual) rows = rows.filter((r) => r[conf.qualKey] >= min && r[sort] != null);
    sortableTable(document.getElementById("lb-table"), {
      cols: conf.cols, rows, sort, asc: st.sort ? st.asc : false, limit: st.limit,
      onSort: (k, asc) => { st.sort = k; st.asc = asc; st.limit = 50; pageLeaders({}); },
      onMore: () => { st.limit += 100; pageLeaders({}); },
    });
    $app.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => { setHash(`#/leaders?tab=${b.dataset.tab}`); }));
    on("lb-season", (v) => { st.season = v; st.min = null; st.limit = 50; pageLeaders({}); });
    on("lb-fmt", (v) => { st.fmt = v; st.limit = 50; pageLeaders({}); });
    const mi = document.getElementById("lb-min");
    if (mi) mi.addEventListener("change", () => { st.min = Math.max(0, +mi.value || 0); pageLeaders({}); });
  }
  function on(id, fn) { const el = document.getElementById(id); if (el) el.addEventListener("change", () => fn(el.value)); }

  // Records
  function pageRecords() {
    const f = filterFor({ fmt: recordsState.fmt });
    const ctx = (mi) => { const m = D.matches[mi]; return `v ${esc(m[M.OPP])} ${boltSvg} ${esc(seasonLabel(m[M.SEASON]))}`; };

    const inns = D.bat.filter((r) => f(r[0]) && isReal(r[1])).sort((a, b) => b[2] - a[2] || b[6] - a[6] || a[3] - b[3]).slice(0, 10);
    const spells = D.bowl.filter((r) => f(r[0]) && isReal(r[1]) && r[5] > 0).sort((a, b) => b[5] - a[5] || a[4] - b[4]).slice(0, 10);
    const bySeason = aggregate(f, `rec|${cat}|${recordsState.fmt}`, (r) => r[1] * 1000 + D.matches[r[0]][M.SEASON], (r) => r[A.P] * 1000 + r[A.S]);
    const topSeason = (key, n) => [...bySeason.entries()].filter(([k, s]) => isReal(Math.floor(k / 1000)) && s[key] > 0)
      .sort((a, b) => b[1][key] - a[1][key]).slice(0, n);
    const seasonRuns = topSeason("runs", 10).map(([k, s]) => ({ name: plink(Math.floor(k / 1000)), val: s.runs, small: `${s.inn} inn`, sub: seasonLabel(k % 1000) }));
    const seasonWk = topSeason("wk", 10).map(([k, s]) => ({ name: plink(Math.floor(k / 1000)), val: s.wk, small: fx(s.bavg) + " avg", sub: seasonLabel(k % 1000) }));

    const all = agg({ fmt: recordsState.fmt });
    const club = (key, thr) => [...all.entries()].filter(([p, s]) => isReal(p) && s[key] >= thr).sort((a, b) => b[1][key] - a[1][key]);
    const clubBoard = (title, list, key, unit) => `<section class="board"><h3>${esc(title)} <span class="muted">${list.length}</span></h3>
      ${list.length ? list.map(([p, s], i) => `<div class="row"><span class="rk">${i + 1}</span>${plink(p)}<span class="val">${fmtN(s[key])}<small>${unit}</small></span></div>`).join("") : '<p class="empty">No members yet.</p>'}</section>`;

    $app.innerHTML = `
      <div class="page-head"><p class="eyebrow">${esc(catName())}</p><h1 class="page-title">Club Records</h1></div>
      <div class="controls">${selectHtml("rec-fmt", "Format", fmtOptions, recordsState.fmt)}</div>
      <div class="boards wide">
        ${board("Highest scores", inns.map((r) => ({ name: plink(r[1]), val: hs(r[2], r[6]), small: r[3] ? `(${r[3]})` : "", sub: ctx(r[0]) })))}
        ${board("Best bowling", spells.map((r) => ({ name: plink(r[1]), val: fig(r[5], r[4]), small: overs(r[2]) + " ov", sub: ctx(r[0]) })))}
        ${board("Most runs in a season", seasonRuns)}
        ${board("Most wickets in a season", seasonWk)}
      </div>
      ${divider("Milestone clubs")}
      <div class="boards">
        ${clubBoard("100 games", club("m", 100), "m", "games")}
        ${clubBoard("1000 runs", club("runs", 1000), "runs", "runs")}
        ${clubBoard("100 wickets", club("wk", 100), "wk", "wkts")}
      </div>
    `;
    on("rec-fmt", (v) => { recordsState.fmt = v; pageRecords(); });
  }

  // Upcoming milestones: players in the current season closing in on round career figures
  // (multiples of `step`) within the selected competition.
  const MILESTONES = [
    { key: "runs", title: "Runs", unit: "runs", get: (s) => s.runs, step: 500, win: (t) => Math.min(250, t * 0.1) },
    { key: "wk", title: "Wickets", unit: "wkts", get: (s) => s.wk, step: 50, win: (t) => Math.max(5, t * 0.1) },
    { key: "m", title: "Matches", unit: "games", get: (s) => s.m, step: 50, win: (t) => Math.max(5, t * 0.05) },
    { key: "dis", title: "Dismissals", unit: "dismissals", get: (s) => s.dis, step: 50, win: (t) => Math.max(5, t * 0.1) },
  ];
  function pageMilestones() {
    const latest = D.seasons.length - 1;
    // Milestones are always career totals across every competition (men's, women's and juniors),
    // regardless of the competition filter.
    const any = () => true; any.adj = () => true;
    const inLatest = (mi) => D.matches[mi][M.SEASON] === latest; inLatest.adj = (r) => r[A.S] === latest;
    const all = aggregate(any, "ms|all");
    const cur = aggregate(inLatest, "ms|cur");
    const players = [...all.entries()].filter(([p]) => isReal(p) && cur.get(p)?.m > 0);

    const upcoming = MILESTONES.map((ms) => {
      const list = [];
      for (const [p, s] of players) {
        const v = ms.get(s);
        const t = (Math.floor(v / ms.step) + 1) * ms.step;
        if (t - v > ms.win(t)) continue;
        list.push({ p, v, t, gap: t - v, close: (t - v) / ms.win(t) });
      }
      list.sort((a, b) => a.close - b.close || b.t - a.t || pname(a.p).localeCompare(pname(b.p)));
      return { ms, list };
    });

    // Thresholds crossed during the current season (career total before the season < t ≤ total now)
    const reached = [];
    for (const [p, s] of players) {
      const c = cur.get(p);
      if (!c) continue;
      for (const ms of MILESTONES) {
        const now = ms.get(s), before = now - ms.get(c);
        const t = Math.floor(now / ms.step) * ms.step;
        if (t > 0 && before < t) reached.push({ p, ms, t, now });
      }
    }
    reached.sort((a, b) => MILESTONES.indexOf(a.ms) - MILESTONES.indexOf(b.ms) || b.t - a.t || pname(a.p).localeCompare(pname(b.p)));

    const CAP = 15;
    const upBoard = ({ ms, list }) => board(`${ms.title}${list.length ? ` · ${list.length}` : ""}`,
      list.slice(0, CAP).map((x) => ({ name: plink(x.p), val: fmtN(x.gap), small: "to go",
        sub: `${fmtN(x.v)} → ${fmtN(x.t)} ${ms.unit}` })));

    $app.innerHTML = `
      <div class="page-head"><p class="eyebrow">All competitions ${boltSvg} ${esc(seasonLabel(latest))}</p><h1 class="page-title">Milestones</h1></div>
      <p class="lede" style="margin:0 0 20px">Players who have played in ${esc(seasonLabel(latest))} closing in on career milestones. Career totals combine men's, women's and junior cricket and match Play Cricket.</p>
      ${divider("Coming up")}
      <div class="boards">${upcoming.filter((u) => u.list.length).map(upBoard).join("") || '<p class="empty">No one is close to a milestone right now.</p>'}</div>
      ${divider(`Reached in ${seasonLabel(latest)}`)}
      <div class="boards wide">
        ${board(`Milestones reached${reached.length ? ` · ${reached.length}` : ""}`,
          reached.map((x) => ({ name: plink(x.p), val: fmtN(x.t), small: x.ms.unit, sub: `Now on ${fmtN(x.now)}` })))}
      </div>
    `;
  }

  // Players
  function pagePlayers() {
    const st = playersState;
    const data = agg();
    const cols = [
      { key: "name", label: "Player", left: true, asc: true, fmt: (r) => plink(r.p), sortVal: (r) => r.name },
      { key: "first", label: "Span", cls: "dim", asc: true, fmt: (r) => span(r.first, r.last) },
      { key: "m", label: "M", title: "matches" },
      { key: "runs", label: "Runs", fmt: (r) => fmtN(r.runs) },
      { key: "hs", label: "HS", fmt: (r) => (r.hs >= 0 ? hs(r.hs, r.hsNo) : "–"), sortVal: (r) => r.hsSort },
      { key: "avg", label: "Avg", fmt: (r) => fx(r.avg) },
      { key: "wk", label: "Wkts" },
      { key: "best", label: "BB", fmt: (r) => (r.bestW >= 0 ? fig(r.bestW, r.bestR) : "–"), sortVal: (r) => r.bestSort },
      { key: "ct", label: "Ct" },
    ];
    $app.innerHTML = `
      <div class="page-head"><p class="eyebrow">${esc(catName())}</p><h1 class="page-title">Players</h1></div>
      <div class="controls"><label class="field grow"><span class="eyebrow">Search</span><input type="search" id="pl-q" placeholder="Search by name" value="${esc(st.q)}" autocomplete="off"></label></div>
      <div id="pl-table"></div>`;
    const render = () => {
      const q = st.q.trim().toLowerCase();
      const rows = [...data.entries()].filter(([p, s]) => isReal(p) && s.m > 0 && (!q || pname(p).toLowerCase().includes(q))).map(([p, s]) => ({ ...s, p, name: pname(p) }));
      sortableTable(document.getElementById("pl-table"), {
        cols, rows, sort: st.sort, asc: st.asc, limit: st.limit, rank: false,
        onSort: (k, asc) => { st.sort = k; st.asc = asc; render(); },
        onMore: () => { st.limit += 200; render(); },
      });
    };
    const qi = document.getElementById("pl-q");
    qi.addEventListener("input", () => { st.q = qi.value; st.limit = 100; render(); });
    render();
  }

  // Player profile
  function indexPlayers() {
    byPlayer = D.players.map(() => ({ app: [], bat: [], bowl: [], field: [], adj: [] }));
    D.app.forEach((r) => byPlayer[r[1]].app.push(r));
    D.bat.forEach((r) => byPlayer[r[1]].bat.push(r));
    D.bowl.forEach((r) => byPlayer[r[1]].bowl.push(r));
    D.field.forEach((r) => byPlayer[r[1]].field.push(r));
    D.adj.forEach((r) => byPlayer[r[A.P]].adj.push(r));
  }
  /** keyFn(season, cat) → group key. Includes official adjustments. */
  function playerAgg(p, keyFn) {
    const out = new Map();
    const get = (k) => { let s = out.get(k); if (!s) { s = blank(); out.set(k, s); } return s; };
    const P = byPlayer[p];
    const k = (mi) => keyFn(D.matches[mi][M.SEASON], D.matches[mi][M.CAT]);
    P.app.forEach((r) => addApp(get(k(r[0])), r[0]));
    P.bat.forEach((r) => addBat(get(k(r[0])), r));
    P.bowl.forEach((r) => addBowl(get(k(r[0])), r));
    P.field.forEach((r) => addField(get(k(r[0])), r));
    P.adj.forEach((r) => addAdj(get(keyFn(r[A.S], r[A.CAT])), r));
    out.forEach(derive);
    return out;
  }
  /* Career milestone timeline. Walks scorecards in date order, but each season's contribution is
     reconciled with Play Cricket's official season totals (scorecard + adjustment rows): a season
     never adds more than its official figure, and official games/runs/wickets with no scorecard are
     credited at the end of that season. So milestones never exceed the official career totals. */
  function milestones(p) {
    const P = byPlayer[p];
    const STATS = [
      { label: "games", step: 50, adj: 3 },
      { label: "runs", step: 1000, adj: 6 },
      { label: "wickets", step: 50, adj: 15 },
    ];
    const perMatch = new Map(); // mi -> [games, runs, wkts]
    const row = (mi) => { let v = perMatch.get(mi); if (!v) { v = [0, 0, 0]; perMatch.set(mi, v); } return v; };
    P.app.forEach((r) => { row(r[0])[0] = 1; });
    P.bat.forEach((r) => { row(r[0])[1] += r[2]; });
    P.bowl.forEach((r) => { row(r[0])[2] += r[5]; });
    const bySeason = new Map(); // season -> { ms: [mi], official: [g, r, w] }
    const season = (s) => { let x = bySeason.get(s); if (!x) { x = { ms: [], official: [0, 0, 0] }; bySeason.set(s, x); } return x; };
    perMatch.forEach((v, mi) => { const x = season(D.matches[mi][M.SEASON]); x.ms.push(mi); v.forEach((n, i) => { x.official[i] += n; }); });
    P.adj.forEach((r) => { const x = season(r[A.S]); STATS.forEach((st, i) => { x.official[i] += r[st.adj]; }); });

    const ev = [];
    const tot = [0, 0, 0];
    const add = (i, n, at) => {
      if (n <= 0) return;
      const prev = tot[i]; tot[i] += n;
      const st = STATS[i];
      for (let k = Math.floor(prev / st.step) + 1; k <= Math.floor(tot[i] / st.step); k++) ev.push({ t: `${k * st.step} ${st.label}`, ...at });
    };
    const byDate = (a, b) => (D.matches[a][M.DATE] < D.matches[b][M.DATE] ? -1 : D.matches[a][M.DATE] > D.matches[b][M.DATE] ? 1 : a - b);
    for (const s of [...bySeason.keys()].sort((a, b) => a - b)) {
      const x = bySeason.get(s);
      const used = [0, 0, 0];
      for (const mi of x.ms.sort(byDate)) {
        perMatch.get(mi).forEach((n, i) => {
          const take = Math.min(n, Math.max(0, x.official[i] - used[i]));
          used[i] += take; add(i, take, { mi });
        });
      }
      x.official.forEach((n, i) => add(i, n - used[i], { s })); // official extras with no scorecard
    }
    return ev;
  }

  function pagePlayer(p) {
    if (!D.players[p]) { $app.innerHTML = '<p class="empty">Player not found.</p>'; return; }
    const name = pname(p);
    const parts = name.trim().split(" ");
    const surname = parts.length > 1 ? parts.pop() : parts[0];
    const given = parts.length && parts[0] !== surname ? parts.join(" ") : "";
    const tot = playerAgg(p, () => "t").get("t") || derive(blank());
    const byCat = playerAgg(p, (s, c) => c);
    const bySeason = playerAgg(p, (s) => s);
    const grades = new Map();
    byPlayer[p].app.forEach((r) => { const g = D.grades[D.matches[r[0]][M.GRADE]]; grades.set(g, (grades.get(g) || 0) + 1); });
    const topGrades = [...grades.entries()].sort((a, b) => b[1] - a[1]).slice(0, 2).map((x) => x[0]);
    const lastApp = byPlayer[p].app.map((r) => r[0]).sort((a, b) => (D.matches[a][M.DATE] < D.matches[b][M.DATE] ? 1 : -1))[0];
    const ev = milestones(p);
    const catRows = [0, 1, 2].filter((c) => byCat.has(c)).map((c) => ({ label: CATS[c], s: byCat.get(c) }));
    if (catRows.length > 1) catRows.push({ label: "Total", s: tot, total: true });
    if (catRows.length === 0) catRows.push({ label: "Total", s: tot, total: true });

    const batTable = `<div class="table-wrap"><table><thead><tr><th class="l">Batting</th><th>M</th><th>Inn</th><th>NO</th><th>Runs</th><th>HS</th><th>Avg</th><th>SR</th><th>100s</th><th>50s</th><th>4s</th><th>6s</th></tr></thead><tbody>
      ${catRows.map(({ label, s, total }) => `<tr class="${total ? "total" : ""}"><td class="l">${label}</td><td>${s.m}</td><td>${s.inn}</td><td>${s.no}</td><td class="key">${fmtN(s.runs)}</td><td>${s.hs >= 0 ? hs(s.hs, s.hsNo) : "–"}</td><td>${fx(s.avg)}</td><td>${fx(s.sr)}</td><td>${s.h100}</td><td>${s.f50}</td><td>${s.fours}</td><td>${s.sixes}</td></tr>`).join("")}</tbody></table></div>`;
    const bowlTable = `<div class="table-wrap"><table><thead><tr><th class="l">Bowling</th><th>Overs</th><th>Mdns</th><th>Runs</th><th>Wkts</th><th>BB</th><th>Avg</th><th>Econ</th><th>SR</th><th>5W</th><th>Ct</th><th>St</th></tr></thead><tbody>
      ${catRows.map(({ label, s, total }) => `<tr class="${total ? "total" : ""}"><td class="l">${label}</td><td>${overs(s.bb)}</td><td>${s.mdn}</td><td>${fmtN(s.rc)}</td><td class="key">${s.wk}</td><td>${s.bestW >= 0 ? fig(s.bestW, s.bestR) : "–"}</td><td>${fx(s.bavg)}</td><td>${fx(s.econ)}</td><td>${fx(s.bsr, 1)}</td><td>${s.w5}</td><td>${s.ct + s.wkc}</td><td>${s.st}</td></tr>`).join("")}</tbody></table></div>`;

    const seasonIdx = [...bySeason.keys()].sort((a, b) => b - a);
    const seasonTable = `<div class="table-wrap"><table><thead><tr><th class="l">Season</th><th>M</th><th>Inn</th><th>Runs</th><th>HS</th><th>Avg</th><th>Wkts</th><th>BB</th><th>Avg</th><th>Ct</th></tr></thead><tbody>
      ${seasonIdx.map((si) => { const s = bySeason.get(si); return `<tr><td class="l"><a class="teal" href="#/seasons/${si}">${seasonLabel(si)}</a></td><td>${s.m}</td><td>${s.inn}</td><td class="key">${s.runs}</td><td>${s.hs >= 0 ? hs(s.hs, s.hsNo) : "–"}</td><td>${fx(s.avg)}</td><td class="key">${s.wk}</td><td>${s.bestW >= 0 ? fig(s.bestW, s.bestR) : "–"}</td><td>${fx(s.bavg)}</td><td>${s.ct + s.wkc}</td></tr>`; }).join("")}</tbody></table></div>`;

    const ctx = (mi) => { const m = D.matches[mi]; return `v ${esc(m[M.OPP])} ${boltSvg} ${esc(seasonLabel(m[M.SEASON]))} ${boltSvg} ${esc(D.grades[m[M.GRADE]])}`; };
    const bestInns = byPlayer[p].bat.slice().sort((a, b) => b[2] - a[2] || b[6] - a[6]).slice(0, 5)
      .map((r) => ({ name: `<span class="nm">${hs(r[2], r[6])}${r[3] ? ` <span class="muted">(${r[3]})</span>` : ""}</span>`, val: "", sub: ctx(r[0]) }));
    const bestSpells = byPlayer[p].bowl.filter((r) => r[5] > 0).sort((a, b) => b[5] - a[5] || a[4] - b[4]).slice(0, 5)
      .map((r) => ({ name: `<span class="nm">${fig(r[5], r[4])} <span class="muted">(${overs(r[2])} ov)</span></span>`, val: "", sub: ctx(r[0]) }));

    $app.innerHTML = `
      <div class="profile-head">
        <div>
          <p class="eyebrow teal">Player profile ${boltSvg} ${span(tot.first, tot.last)}</p>
          <h1 class="surname">${esc(surname)}</h1>
          ${given ? `<p class="given">${esc(given)}</p>` : ""}
        </div>
        <dl class="detail">
          <div><dt>Matches</dt><dd>${fmtN(tot.m)}</dd></div>
          <div><dt>Seasons</dt><dd>${tot.ns}</dd></div>
          <div><dt>Main grade</dt><dd>${esc(topGrades[0] || "–")}</dd></div>
          <div><dt>Last played</dt><dd>${lastApp != null ? dateStr(D.matches[lastApp][M.DATE]) : "–"}</dd></div>
        </dl>
      </div>
      ${ev.length ? `<div class="milestones">${ev.map((e) => `<div class="ms"><strong>${esc(e.t)}</strong><span>${e.mi != null ? `${dateStr(D.matches[e.mi][M.DATE])} v ${esc(D.matches[e.mi][M.OPP])}` : `During ${esc(seasonLabel(e.s))}`}</span></div>`).join("")}</div>` : ""}

      <div class="tiles" style="margin-top:32px">
        <div class="tile"><span class="num">${fmtN(tot.runs)}</span><span class="eyebrow">Runs</span></div>
        <div class="tile"><span class="num">${tot.hs >= 0 ? hs(tot.hs, tot.hsNo) : "–"}</span><span class="eyebrow">High score</span></div>
        <div class="tile"><span class="num">${fx(tot.avg)}</span><span class="eyebrow">Bat avg</span></div>
        <div class="tile"><span class="num">${fmtN(tot.wk)}</span><span class="eyebrow">Wickets</span></div>
        <div class="tile"><span class="num">${tot.bestW >= 0 ? fig(tot.bestW, tot.bestR) : "–"}</span><span class="eyebrow">Best bowling</span></div>
        <div class="tile"><span class="num">${fmtN(tot.dis)}</span><span class="eyebrow">Dismissals</span></div>
      </div>

      ${divider("Career")}
      ${batTable}
      <div style="height:20px"></div>
      ${bowlTable}

      ${divider("By season")}
      <div class="chart-head">
        <span class="chart-title" id="chart-title"></span>
        <div class="seg" id="chart-toggle"><button data-c="runs">Runs</button><button data-c="wk">Wickets</button></div>
      </div>
      <div id="chart"></div>
      <div style="height:16px"></div>
      ${seasonTable}

      <p class="note">Career and season totals match Play Cricket (Club: Sydenham-Hillside). Play Cricket counts some games it doesn't publish scorecards for, so the lists below can't always account for every run.</p>

      ${divider("Best performances")}
      <div class="boards">
        ${board("Top scores", bestInns)}
        ${board("Best figures", bestSpells)}
      </div>
    `;

    const drawChart = () => {
      const key = profileState.chart;
      document.querySelectorAll("#chart-toggle button").forEach((b) => b.classList.toggle("on", b.dataset.c === key));
      document.getElementById("chart-title").textContent = key === "runs" ? "Runs per season" : "Wickets per season";
      if (tot.first == null) { document.getElementById("chart").innerHTML = ""; return; }
      const pts = [];
      for (let s = tot.first; s <= tot.last; s++) { const v = bySeason.get(s); pts.push({ s, v: v ? v[key] : 0, m: v ? v.m : 0 }); }
      const el = document.getElementById("chart");
      el.innerHTML = barChart(pts, key === "runs" ? "runs" : "wkts", el.clientWidth || 800);
      bindTips(document.getElementById("chart"));
    };
    document.querySelectorAll("#chart-toggle button").forEach((b) => b.addEventListener("click", () => { profileState.chart = b.dataset.c; drawChart(); }));
    drawChart();
  }

  function niceMax(v) {
    if (v <= 5) return 5;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    for (const k of [1, 2, 2.5, 5, 10]) if (k * p >= v) return k * p;
    return 10 * p;
  }
  function barChart(pts, unit, width) {
    const max = niceMax(Math.max(1, ...pts.map((p) => p.v)));
    const labelEvery = Math.ceil(pts.length / Math.max(4, Math.floor(width / 70)));
    // Fixed viewBox scaled uniformly, so text and rounded bar tops are never distorted.
    const W = Math.max(300, width), H = 220, L = 36, R = 6, T = 12, B = 24;
    const iw = W - L - R, ih = H - T - B;
    const slot = iw / pts.length;
    const bw = Math.max(4, Math.min(28, slot - 4)); // keeps a ≥2px gap between bars
    const y = (v) => T + ih - (v / max) * ih;
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${unit} per season">`;
    [0, max / 2, max].forEach((t) => { s += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(t)}" y2="${y(t)}"/><text class="axis" x="${L - 8}" y="${y(t) + 3}" text-anchor="end">${fmtN(Math.round(t))}</text>`; });
    pts.forEach((p, i) => {
      const cx = L + slot * i + slot / 2;
      const h = Math.max(0, ih - (y(p.v) - T));
      const r = Math.min(4, bw / 2, h);
      const x0 = cx - bw / 2, yb = T + ih, yt = yb - h;
      const path = h > 0 ? `M${x0},${yb} V${yt + r} Q${x0},${yt} ${x0 + r},${yt} H${x0 + bw - r} Q${x0 + bw},${yt} ${x0 + bw},${yt + r} V${yb} Z` : "";
      const tip = `<b>${esc(seasonLabel(p.s))}</b>${fmtN(p.v)} ${unit}<br><span>${p.m} match${p.m === 1 ? "" : "es"}</span>`;
      s += `<g data-tip="${esc(tip)}"><rect class="hit" x="${cx - slot / 2}" y="${T}" width="${slot}" height="${ih + B}"/>${path ? `<path class="bar" d="${path}"/>` : ""}</g>`;
      if (i % labelEvery === 0) s += `<text class="axis" x="${cx}" y="${H - 6}" text-anchor="middle">${esc(seasonLabel(p.s).slice(2, 4) + "/" + seasonLabel(p.s).slice(-2))}</text>`;
    });
    return s + "</svg>";
  }
  function bindTips(root) {
    root.querySelectorAll("[data-tip]").forEach((g) => {
      g.addEventListener("mousemove", (e) => {
        $tip.innerHTML = g.dataset.tip;
        $tip.style.opacity = 1;
        const w = $tip.offsetWidth;
        $tip.style.left = Math.min(window.innerWidth - w - 8, e.clientX + 12) + "px";
        $tip.style.top = e.clientY - $tip.offsetHeight - 12 + "px";
      });
      g.addEventListener("mouseleave", () => { $tip.style.opacity = 0; });
    });
  }

  // Seasons
  function pageSeasons(si) {
    if (si != null && D.seasons[si]) seasonState.season = si;
    if (seasonState.season == null) seasonState.season = D.seasons.length - 1;
    const s = seasonState.season;
    const list = [];
    const teams = new Map();
    D.matches.forEach((m, i) => {
      if (m[M.SEASON] !== s || !catOk(i)) return;
      list.push(i);
      if (m[M.RES] === "-") return;
      const g = D.grades[m[M.GRADE]];
      const t = teams.get(g) || { g, p: 0, W: 0, L: 0, D: 0, T: 0, cat: m[M.CAT] };
      t.p++; t[m[M.RES]]++;
      teams.set(g, t);
    });
    const data = agg({ season: s });
    const runs = topBy(data, "runs", 5).map(([p, x]) => ({ name: plink(p), val: x.runs, small: `HS ${hs(x.hs, x.hsNo)}` }));
    const wk = topBy(data, "wk", 5).map(([p, x]) => ({ name: plink(p), val: x.wk, small: `BB ${fig(x.bestW, x.bestR)}` }));
    const W = [...teams.values()].reduce((a, t) => a + t.W, 0), P = [...teams.values()].reduce((a, t) => a + t.p, 0);
    list.sort((a, b) => (D.matches[a][M.DATE] < D.matches[b][M.DATE] ? 1 : -1));

    $app.innerHTML = `
      <div class="page-head"><p class="eyebrow">${esc(catName())}</p><h1 class="page-title">${esc(seasonLabel(s))}</h1></div>
      <div class="controls">${selectHtml("se-season", "Season", seasonOptions().slice(1), s)}</div>
      <div class="tiles">
        <div class="tile"><span class="num">${P}</span><span class="eyebrow">Played</span></div>
        <div class="tile"><span class="num">${W}<small>${P ? Math.round((W / P) * 100) + "%" : ""}</small></span><span class="eyebrow">Won</span></div>
        <div class="tile"><span class="num">${teams.size}</span><span class="eyebrow">Teams</span></div>
      </div>
      ${divider("Season leaders")}
      <div class="boards">${board("Top batters", runs, `#/leaders?tab=bat&season=${s}`)}${board("Top bowlers", wk, `#/leaders?tab=bowl&season=${s}`)}</div>
      ${divider("Team records")}
      <div class="table-wrap"><table><thead><tr><th class="l">Grade</th><th>P</th><th>W</th><th>L</th><th>D/NR</th><th>T</th><th>Win %</th></tr></thead><tbody>
        ${[...teams.values()].sort((a, b) => a.cat - b.cat || b.p - a.p).map((t) => `<tr><td class="l">${esc(t.g)}</td><td>${t.p}</td><td class="key">${t.W}</td><td>${t.L}</td><td>${t.D}</td><td>${t.T}</td><td>${t.p ? Math.round((t.W / t.p) * 100) + "%" : "–"}</td></tr>`).join("") || '<tr><td class="l dim" colspan="7">No completed matches.</td></tr>'}
      </tbody></table></div>
      ${divider("Results")}
      ${resultsTable(list, false)}
    `;
    on("se-season", (v) => setHash(`#/seasons/${v}`));
  }

  // ---------- router ----------
  function setHash(h) { if (location.hash === h) route(); else location.hash = h; }
  function route() {
    const h = location.hash.replace(/^#/, "") || "/";
    const [path, qs] = h.split("?");
    const params = Object.fromEntries(new URLSearchParams(qs || ""));
    const seg = path.split("/").filter(Boolean);
    const page = seg[0] || "home";
    document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === page || (page === "player" && a.dataset.nav === "players")));
    $tip.style.opacity = 0;
    if (page === "leaders") pageLeaders(params);
    else if (page === "records") pageRecords();
    else if (page === "milestones") pageMilestones();
    else if (page === "players") pagePlayers();
    else if (page === "player") pagePlayer(+seg[1]);
    else if (page === "seasons") pageSeasons(seg[1] != null ? +seg[1] : null);
    else pageHome();
    const titles = { leaders: "Leaderboards", records: "Records", milestones: "Milestones", players: "Players", seasons: "Seasons" };
    document.title = page === "player" && D.players[+seg[1]] ? `${pname(+seg[1])} · SHCC Stats` : titles[page] ? `${titles[page]} · SHCC Stats` : "SHCC Stats";
  }
  function paintComp() {
    document.querySelectorAll("#comp-filter button").forEach((b) => { const on = b.dataset.cat === cat; b.classList.toggle("on", on); b.setAttribute("aria-pressed", on); });
  }
  document.querySelectorAll("#comp-filter button").forEach((b) => b.addEventListener("click", () => {
    cat = b.dataset.cat; store.set("cat", cat); paintComp(); leadersState.limit = 50; route();
  }));
  let lastPath = "";
  window.addEventListener("hashchange", () => {
    const path = location.hash.split("?")[0];
    route();
    if (path !== lastPath) window.scrollTo(0, 0);
    lastPath = path;
  });

  fetch("data.json").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }).then((d) => {
    D = d;
    indexPlayers();
    paintComp();
    document.getElementById("footer-note").textContent += ` Updated ${dateStr(D.built)}.`;
    lastPath = location.hash.split("?")[0];
    route();
  }).catch(() => {
    $app.innerHTML = '<p class="loading eyebrow">Could not load data.json. Run <code>python build_site.py</code> and serve the site folder over HTTP.</p>';
  });
})();
