# -*- coding: utf-8 -*-
"""Generate a browsable HTML report from scb_full_metadata.jsonl."""
import json, re, html

recs = [json.loads(l) for l in open("scb_full_metadata.jsonl", encoding="utf-8")]

RANGE = re.compile(r"^\s*\d{1,3}\s*[–-]\s*\d{1,3}")
SINGLE = re.compile(r"^\s*\d{1,3}\s*(years?|år)?\s*$", re.I)
WORKING_TOTALS = {"20-64", "20-65", "20-66", "16-64", "16-74", "15-74",
                  "15-64", "20-74", "16-64", "18-64", "15-89", "16-89", "20-64"}
STATUS_KEYS = ["unemploy", "not in the labour force", "not in labour force",
               "in the labour force", "labour force", "arbetskraft", "arbetslös",
               "ej i arbetskraften", "sysselsatt"]

AREA_NAMES = {
    "AM0101": "Wages/salaries, private sector", "AM0102": "Wages, public sector",
    "AM0103": "Wage structure statistics", "AM0104": "Wages, municipalities",
    "AM0105": "Wages, county councils", "AM0106": "Wages, central government",
    "AM0108": "Labour cost index", "AM0109": "Short-term wages",
    "AM0110": "Labour cost / structure", "AM0114": "Job vacancies",
    "AM0201": "Occupational register", "AM0206": "Employment (short-term)",
    "AM0207": "RAMS — register-based labour market stats",
    "AM0208": "Occupational register (YREG)", "AM0209": "Staffing",
    "AM0210": "Register-based labour market status (BAS)",
    "AM0211": "Recruitment / job openings", "AM0301": "Work injuries",
    "AM0302": "Work environment", "AM0401": "AKU — Labour Force Survey",
    "AM0403": "AKU — Labour Force Survey (themes/NEET)",
    "AM0701": "Sickness / rehab", "AM0702": "Trade union / conflicts",
    "AM7001": "Working environment surveys",
    "UF0301": "Comprehensive school", "UF0306": "Adult education",
    "UF0315": "Upper secondary school", "UF0501": "Higher education — students",
    "UF0502": "Higher education — throughput", "UF0503": "Establishment after education",
    "UF0506": "Educational attainment of population", "UF0507": "Study participation",
    "UF0512": "Transition to higher education", "UF0521": "Doctoral studies",
    "UF0542": "Municipal adult education", "UF0549": "Education misc",
    "UF0550": "Education misc", "UF0601": "Education costs",
    "UF0701": "International / education indicators", "UF0702": "Educational register",
}

def _norm(v):
    return re.sub(r"\s|years?|år", "", v.lower()).replace("–", "-").replace("—", "-")

def classify_age(vals):
    if not vals:
        return ("none", "—")
    singles = [v for v in vals if SINGLE.match(v)]
    bands = [v for v in vals if RANGE.match(v)]
    # a "total"-style band spans a wide working-age/whole-population range
    def is_total(v):
        m = re.match(r"^\s*(\d{1,3})\s*[–-]\s*(\d{1,3})", v)
        if not m:
            return _norm(v) in WORKING_TOTALS
        lo, hi = int(m.group(1)), int(m.group(2))
        return (hi - lo) >= 20 or _norm(v) in WORKING_TOTALS
    real_bands = [v for v in bands if not is_total(v)]
    if len(singles) >= 10:
        return ("single", f"single-year ({len(singles)} ages)")
    if len(real_bands) >= 4:
        return ("bands", f"{len(real_bands)} age bands")
    if bands and not real_bands:
        return ("total", "working-age total only")
    if real_bands:
        return ("bands", f"{len(real_bands)} band(s)")
    if bands:
        return ("total", "aggregate range only")
    return ("limited", f"{len(vals)} value(s)")

tables = []
counts = {"age_real": 0, "edu": 0, "status": 0, "all3": 0}
for r in recs:
    parts = r["id"].split("/")
    area = parts[1] if len(parts) > 1 else "?"
    vars_out, has_age_var, age_vals = [], False, []
    has_edu = has_status = False
    year = "—"
    for v in r.get("variables", []):
        code = (v.get("code") or "")
        text = (v.get("text") or "")
        vts = v.get("valueTexts", [])
        lc, lt = code.lower(), text.lower()
        if lc == "alder" or "age" in lt:
            has_age_var = True
            age_vals = vts
        if "utbild" in lc or "education" in lt:
            has_edu = True
        vt_join = " ".join(vts).lower()
        if lc == "arbetskraftstillh" or any(k in vt_join for k in STATUS_KEYS):
            has_status = True
        if v.get("time"):
            nums = [x for x in vts if re.search(r"\d", x)]
            if nums:
                year = f"{nums[0]}–{nums[-1]}" if len(nums) > 1 else nums[0]
        cap = 50
        vals_show = vts[:cap]
        vars_out.append({
            "c": code, "t": text, "e": bool(v.get("elimination")),
            "tm": bool(v.get("time")), "n": v.get("n_values", len(vts)),
            "v": vals_show, "more": max(0, len(vts) - cap),
        })
    age_kind, age_label = classify_age(age_vals) if has_age_var else ("none", "—")
    age_real = age_kind in ("single", "bands")
    if age_real: counts["age_real"] += 1
    if has_edu: counts["edu"] += 1
    if has_status: counts["status"] += 1
    all3 = age_real and has_edu and has_status
    if all3: counts["all3"] += 1
    tables.append({
        "id": r["id"], "title": r.get("title", ""), "area": area,
        "year": year, "nvars": len(vars_out), "vars": vars_out,
        "age": age_kind, "ageL": age_label, "edu": has_edu,
        "status": has_status, "all3": all3,
    })

tables.sort(key=lambda t: t["id"])
areas_sorted = sorted({t["area"] for t in tables})
data = {"tables": tables, "areas": [{"code": a, "name": AREA_NAMES.get(a, a),
        "n": sum(1 for t in tables if t["area"] == a)} for a in areas_sorted],
        "counts": counts, "total": len(tables)}

payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

# ---- HTML (page content only; harness wraps <head>/<body>) ----
tmpl = r"""<title>SCB PxWeb Table Catalog — Labour Market & Education</title>
<style>
:root{
  --ground:#f6f8fb; --surface:#ffffff; --surface-2:#eef2f7; --line:#dbe3ec;
  --ink:#141c26; --muted:#5a6a7a; --faint:#8a97a5;
  --accent:#1f5c9e; --accent-soft:#e6eef7;
  --ok:#2f7d5b; --ok-soft:#e3f1ea; --warn:#b8791f; --warn-soft:#f6ecda;
  --edu:#6a4bb0; --edu-soft:#ece6f6;
  --mono:ui-monospace,"SF Mono","Cascadia Code","Roboto Mono",Menlo,Consolas,monospace;
  --disp:"Segoe UI Variable Display","Inter",system-ui,-apple-system,sans-serif;
  --body:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}
@media (prefers-color-scheme:dark){
  :root{
    --ground:#0f151c; --surface:#161f29; --surface-2:#1d2833; --line:#2a3744;
    --ink:#e7edf3; --muted:#9fb0be; --faint:#6d7d8b;
    --accent:#5fa3e0; --accent-soft:#17293c;
    --ok:#5ec996; --ok-soft:#123026; --warn:#e0a94a; --warn-soft:#33280f;
    --edu:#b199e6; --edu-soft:#241a3a;
  }
}
:root[data-theme="dark"]{
  --ground:#0f151c; --surface:#161f29; --surface-2:#1d2833; --line:#2a3744;
  --ink:#e7edf3; --muted:#9fb0be; --faint:#6d7d8b;
  --accent:#5fa3e0; --accent-soft:#17293c;
  --ok:#5ec996; --ok-soft:#123026; --warn:#e0a94a; --warn-soft:#33280f;
  --edu:#b199e6; --edu-soft:#241a3a;
}
:root[data-theme="light"]{
  --ground:#f6f8fb; --surface:#ffffff; --surface-2:#eef2f7; --line:#dbe3ec;
  --ink:#141c26; --muted:#5a6a7a; --faint:#8a97a5;
  --accent:#1f5c9e; --accent-soft:#e6eef7;
  --ok:#2f7d5b; --ok-soft:#e3f1ea; --warn:#b8791f; --warn-soft:#f6ecda;
  --edu:#6a4bb0; --edu-soft:#ece6f6;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--body);
  font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:0 20px}
header.top{border-bottom:1px solid var(--line);background:
  linear-gradient(180deg,var(--accent-soft),transparent);padding:34px 0 22px}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--accent);margin:0 0 8px}
h1{font-family:var(--disp);font-weight:650;font-size:clamp(24px,3.4vw,34px);
  margin:0 0 6px;letter-spacing:-.01em;text-wrap:balance}
.sub{color:var(--muted);max-width:64ch;margin:0}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:10px;
  padding:10px 14px;min-width:96px}
.stat .num{font-family:var(--disp);font-weight:650;font-size:22px;
  font-variant-numeric:tabular-nums;line-height:1}
.stat .lbl{font-size:11.5px;color:var(--muted);margin-top:4px;letter-spacing:.02em}
.stat.hl{border-color:var(--ok);background:var(--ok-soft)}
.toolbar{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--ground) 88%,transparent);
  backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:12px 0;margin-bottom:6px}
.toolrow{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
#q{flex:1 1 260px;min-width:200px;font:inherit;padding:9px 12px;border-radius:9px;
  border:1px solid var(--line);background:var(--surface);color:var(--ink)}
#q:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.filters{display:flex;flex-wrap:wrap;gap:6px}
.filt{font:inherit;font-size:13px;cursor:pointer;padding:7px 11px;border-radius:999px;
  border:1px solid var(--line);background:var(--surface);color:var(--muted);
  display:inline-flex;gap:6px;align-items:center}
.filt[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff}
.filt:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.hint{color:var(--faint);font-size:12.5px;margin:8px 0 0}
main{padding:14px 0 60px}
.area{margin:26px 0 6px;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.area h2{font-family:var(--disp);font-size:15px;font-weight:640;margin:0;letter-spacing:.01em}
.area .code{font-family:var(--mono);font-size:12px;color:var(--accent)}
.area .cnt{font-size:12px;color:var(--faint);font-variant-numeric:tabular-nums}
.area .bar{flex:1;height:1px;background:var(--line)}
details.tbl{background:var(--surface);border:1px solid var(--line);border-radius:10px;
  margin:7px 0;overflow:hidden}
details.tbl[open]{border-color:var(--accent)}
summary{list-style:none;cursor:pointer;padding:11px 14px;display:flex;gap:12px;
  align-items:center;flex-wrap:wrap}
summary::-webkit-details-marker{display:none}
.tid{font-family:var(--mono);font-size:12.5px;color:var(--accent);white-space:nowrap}
.ttl{flex:1 1 340px;min-width:0}
.yr{font-family:var(--mono);font-size:11.5px;color:var(--faint);white-space:nowrap;
  font-variant-numeric:tabular-nums}
.chips{display:flex;gap:5px;flex-wrap:wrap}
.chip{font-size:11px;font-family:var(--mono);letter-spacing:.02em;padding:3px 8px;
  border-radius:999px;border:1px solid transparent;white-space:nowrap}
.chip.age{background:var(--ok-soft);color:var(--ok);border-color:var(--ok)}
.chip.aget{background:var(--warn-soft);color:var(--warn);border-color:var(--warn)}
.chip.edu{background:var(--edu-soft);color:var(--edu);border-color:var(--edu)}
.chip.st{background:var(--accent-soft);color:var(--accent);border-color:var(--accent)}
.chip.all{background:var(--ok);color:#fff}
.body{padding:2px 14px 14px;border-top:1px solid var(--line)}
table{width:100%;border-collapse:collapse;font-size:13px}
.vscroll{overflow-x:auto}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--faint);font-weight:600;padding:8px 8px 6px;border-bottom:1px solid var(--line)}
td{padding:7px 8px;border-bottom:1px solid var(--surface-2);vertical-align:top}
tr:last-child td{border-bottom:none}
.vc{font-family:var(--mono);font-size:12px;color:var(--ink);white-space:nowrap}
.vt{color:var(--muted)}
.vn{font-variant-numeric:tabular-nums;color:var(--ink);text-align:right;white-space:nowrap}
.tag{font-family:var(--mono);font-size:10px;padding:1px 5px;border-radius:4px;
  background:var(--surface-2);color:var(--muted);margin-left:5px}
.vals{margin-top:3px;font-size:12px;color:var(--muted);line-height:1.55}
.vals b{color:var(--faint);font-weight:500}
.more{color:var(--warn)}
.empty{text-align:center;color:var(--muted);padding:50px 0}
footer{border-top:1px solid var(--line);padding:22px 0 40px;color:var(--faint);font-size:12.5px}
mark{background:color-mix(in srgb,var(--warn) 30%,transparent);color:inherit;border-radius:2px}
@media (max-width:600px){.yr{display:none}.ttl{flex-basis:100%}}
</style>

<header class="top"><div class="wrap">
  <p class="eyebrow">Statistics Sweden · PxWeb API · en/ssd</p>
  <h1>Labour Market &amp; Education Table Catalog</h1>
  <p class="sub">Every table under the <b>AM</b> (labour market) and <b>UF</b> (education) subject
  areas of the SCB PxWeb API, dumped live with full variable metadata. Use it to locate a table by
  the dimensions it can be filtered on — particularly <b>age</b>, <b>education</b>, and
  <b>labour-force status</b>.</p>
  <div class="stats" id="stats"></div>
</div></header>

<div class="toolbar"><div class="wrap"><div class="toolrow">
  <input id="q" type="search" placeholder="Search table ID, title, or variable (e.g. Alder, sysselsatt, AKU)…" autocomplete="off">
  <div class="filters" id="filters">
    <button class="filt" data-f="age" aria-pressed="false">Age (real bands)</button>
    <button class="filt" data-f="edu" aria-pressed="false">Education</button>
    <button class="filt" data-f="status" aria-pressed="false">Labour status</button>
    <button class="filt" data-f="all3" aria-pressed="false">All three</button>
  </div>
</div>
<p class="hint" id="hint"></p>
</div></div>

<main><div class="wrap" id="list"></div></main>

<footer><div class="wrap">
  Generated from live SCB PxWeb metadata (<span class="vc" style="color:var(--accent)">api.scb.se/OV0104/v1/doris/en/ssd</span>).
  Value lists are capped at 50 entries per variable for display; the complete dump (all value codes + labels)
  lives in <span class="vc">scb_full_metadata.jsonl</span>. Chip legend:
  <span class="chip age">age</span> real age breakdown ·
  <span class="chip aget">age·total</span> working-age total only ·
  <span class="chip edu">edu</span> education level ·
  <span class="chip st">status</span> labour-force status ·
  <span class="chip all">all&nbsp;3</span> combines age+edu+status.
</div></footer>

<script id="data" type="application/json">__PAYLOAD__</script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const stats = [
  ["total","Tables","",D.total],
  ["age","Age (real bands)","",D.counts.age_real],
  ["edu","Education","",D.counts.edu],
  ["status","Labour status","",D.counts.status],
  ["all3","Age+Edu+Status","hl",D.counts.all3],
];
document.getElementById("stats").innerHTML = stats.map(([k,l,c,n])=>
  `<div class="stat ${c}"><div class="num">${n}</div><div class="lbl">${l}</div></div>`).join("");

const areaName = Object.fromEntries(D.areas.map(a=>[a.code,a.name]));
const list = document.getElementById("list");
const active = new Set();
let query = "";

function chips(t){
  let h="";
  if(t.all3) h+=`<span class="chip all">all 3</span>`;
  if(t.age==="single"||t.age==="bands") h+=`<span class="chip age">${t.ageL}</span>`;
  else if(t.age==="total") h+=`<span class="chip aget">age · total only</span>`;
  else if(t.age!=="none") h+=`<span class="chip aget">age · ${t.ageL}</span>`;
  if(t.edu) h+=`<span class="chip edu">education</span>`;
  if(t.status) h+=`<span class="chip st">labour status</span>`;
  return h;
}
function esc(s){return (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}
function hl(s){
  s=esc(s); if(!query) return s;
  try{return s.replace(new RegExp("("+query.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")+")","ig"),"<mark>$1</mark>");}
  catch(e){return s;}
}
function varRows(t){
  return `<div class="vscroll"><table><thead><tr><th>Variable code</th><th>Label</th>
    <th style="text-align:right">Values</th></tr></thead><tbody>`+
    t.vars.map(v=>{
      const tags=(v.tm?`<span class="tag">time</span>`:``)+(v.e?`<span class="tag">eliminable</span>`:``);
      const vv=v.v.map(esc).join(" · ")+(v.more?` <span class="more">…(+${v.more} more)</span>`:``);
      return `<tr><td class="vc">${hl(v.c)}${tags}</td>
        <td class="vt">${hl(v.t)}<div class="vals"><b>values:</b> ${vv}</div></td>
        <td class="vn">${v.n}</td></tr>`;
    }).join("")+`</tbody></table></div>`;
}
function matches(t){
  for(const f of active){
    if(f==="age" && !(t.age==="single"||t.age==="bands")) return false;
    if(f==="edu" && !t.edu) return false;
    if(f==="status" && !t.status) return false;
    if(f==="all3" && !t.all3) return false;
  }
  if(query){
    const hay=(t.id+" "+t.title+" "+t.vars.map(v=>v.c+" "+v.t+" "+v.v.join(" ")).join(" ")).toLowerCase();
    if(!hay.includes(query.toLowerCase())) return false;
  }
  return true;
}
function render(){
  const shown=D.tables.filter(matches);
  const byArea={};
  shown.forEach(t=>(byArea[t.area]=byArea[t.area]||[]).push(t));
  const areas=Object.keys(byArea).sort();
  document.getElementById("hint").textContent=
    `${shown.length} of ${D.total} tables shown`+(query?` · matching “${query}”`:``)+
    (active.size?` · filters: ${[...active].join(", ")}`:``);
  if(!shown.length){list.innerHTML=`<p class="empty">No tables match. Clear the search or filters.</p>`;return;}
  list.innerHTML=areas.map(a=>{
    const rows=byArea[a].map(t=>`
      <details class="tbl" data-id="${t.id}">
        <summary>
          <span class="tid">${hl(t.id.split("/").slice(1).join("/"))}</span>
          <span class="ttl">${hl(t.title)}</span>
          <span class="yr">${t.year}</span>
          <span class="chips">${chips(t)}</span>
        </summary>
        <div class="body"></div>
      </details>`).join("");
    return `<div class="area"><h2>${esc(areaName[a]||a)}</h2><span class="code">${a}</span>
      <span class="cnt">${byArea[a].length}</span><span class="bar"></span></div>${rows}`;
  }).join("");
}
// lazy-fill variable tables on first open
list.addEventListener("toggle",e=>{
  const d=e.target; if(d.tagName!=="DETAILS"||!d.open) return;
  const body=d.querySelector(".body"); if(body.dataset.done) return;
  const t=D.tables.find(x=>x.id===d.dataset.id);
  body.innerHTML=varRows(t); body.dataset.done="1";
},true);

document.getElementById("q").addEventListener("input",e=>{query=e.target.value.trim();render();});
document.getElementById("filters").addEventListener("click",e=>{
  const b=e.target.closest(".filt"); if(!b) return;
  const f=b.dataset.f, on=b.getAttribute("aria-pressed")==="true";
  b.setAttribute("aria-pressed",String(!on));
  on?active.delete(f):active.add(f); render();
});
// stat cards act as filter shortcuts
document.getElementById("stats").addEventListener("click",e=>{
  const c=e.target.closest(".stat"); if(!c) return;
  const map=["","age","edu","status","all3"];
  const idx=[...c.parentNode.children].indexOf(c); const f=map[idx]; if(!f) return;
  const btn=document.querySelector(`.filt[data-f="${f}"]`); btn&&btn.click();
});
render();
</script>
"""
out = tmpl.replace("__PAYLOAD__", payload)
open("scb_report.html", "w", encoding="utf-8").write(out)
print("wrote scb_report.html", round(len(out)/1024), "KB")
print("counts:", data["counts"], "total", data["total"])
