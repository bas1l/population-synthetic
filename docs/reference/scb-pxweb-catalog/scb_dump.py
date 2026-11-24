"""Walk the SCB PxWeb AM + UF subtrees and dump FULL metadata for every table
(id, title, all variables with codes/texts/values/valueTexts) to JSONL.
UTF-8 throughout. Throttled to respect the ~30 req / 10 s SCB limit."""
import json, time, sys, urllib.request, urllib.error

BASE = "https://api.scb.se/OV0104/v1/doris/en/ssd"
ROOTS = ["AM", "UF"]
DELAY = 0.35
OUT = "scb_full_metadata.jsonl"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "scb-dump/1.0"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(4 * (attempt + 1)); continue
            sys.stderr.write(f"SKIP {url}: HTTP {e.code}\n"); return None
        except Exception as e:
            if attempt == 4:
                sys.stderr.write(f"FAIL {url}: {e}\n"); return None
            time.sleep(2 * (attempt + 1))
    return None

tables = []
def walk(path):
    time.sleep(DELAY)
    node = get(f"{BASE}/{path}")
    if node is None or isinstance(node, dict):
        return
    for entry in node:
        eid, etype = entry.get("id"), entry.get("type")
        child = f"{path}/{eid}"
        if etype == "t":
            tables.append((child, entry.get("text", "")))
        elif etype == "l":
            walk(child)

for root in ROOTS:
    walk(root)
sys.stderr.write(f"Discovered {len(tables)} tables. Dumping metadata...\n")

with open(OUT, "w", encoding="utf-8") as fh:
    for i, (path, title) in enumerate(tables):
        time.sleep(DELAY)
        meta = get(f"{BASE}/{path}")
        rec = {"id": path, "title": title, "variables": []}
        if meta and "variables" in meta:
            if meta.get("title"):
                rec["title"] = meta["title"]
            for v in meta["variables"]:
                rec["variables"].append({
                    "code": v.get("code"),
                    "text": v.get("text"),
                    "elimination": v.get("elimination", False),
                    "time": v.get("time", False),
                    "n_values": len(v.get("values", [])),
                    "values": v.get("values", []),
                    "valueTexts": v.get("valueTexts", []),
                })
        else:
            rec["error"] = "no metadata"
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        if (i + 1) % 50 == 0:
            sys.stderr.write(f"  ...{i+1}/{len(tables)}\n")
sys.stderr.write(f"DONE. Wrote {len(tables)} records to {OUT}\n")
