"""Offline verification of archived experiment records and checkout hashes."""
import hashlib
import json
from pathlib import Path
from collections import Counter
from statistics import median
from math import isclose

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT/"evaluation/results/archived/final"

def check_hash(path, expected):
    raw = path.read_bytes()
    # Windows checkout may convert LF to CRLF. Report normalized matches separately.
    if hashlib.sha256(raw).hexdigest() == expected:
        return "exact"
    if any(hashlib.sha256(b).hexdigest()==expected for b in (raw.replace(b"\r\n",b"\n"),raw.replace(b"\r\n",b"\n").replace(b"\n",b"\r\n"))):
        return "line-ending equivalent"
    raise ValueError(f"Hash mismatch: {path}")

def main():
    a = json.loads((ARCHIVE/"controlled_tep_initial.json").read_text(encoding="utf-8"))
    b = json.loads((ARCHIVE/"representative_tep.json").read_text(encoding="utf-8"))
    assert b["complete"] and a["summary"]["repetitions"]==1
    assert a["characterization"]["input_sha256"]==b["config"]["inputs"]
    for k,v in a["input_sha256"].items():
        assert b["config"]["code_and_specs"][k]==v
    hashes = {}
    for k,v in b["config"]["code_and_specs"].items():
        hashes[k] = check_hash(ROOT/k.replace(chr(92),"/"),v)
    for k,v in b["config"]["inputs"].items():
        path = ROOT/k if k.startswith("bindings/") else ROOT.parent/"semantic/ontology2"/k
        hashes[k] = check_hash(path,v)
    comprehensive = a["runs"][0]
    representative = b["events"]
    assert len(comprehensive)==30 and len({e["scenario"] for e in comprehensive})==30
    assert len(representative)==15
    assert {(e["repetition"],e["scenario"]) for e in representative}=={(i,n) for i in range(3) for n in b["config"]["scenarios"]}
    def summarize(events):
        for e in events:
            f,s = e["full"],e["selective"]
            for k in ("verdict","committed","version","from_version","contracts"):
                assert f[k]==s[k], (e["scenario"],k)
            assert f["verdict"]==e["expected"]
            assert f["committed"]==(f["verdict"]=="V")
            assert f["version"]==f["from_version"]+int(f["committed"])
            assert f["executed_instances"]==s["executed_instances"]+s["reused_instances"]
        return {"pairs":len(events),"verdicts":dict(Counter(e["full"]["verdict"] for e in events)),
                **{s:{k:sum(e[s][k] for e in events) for k in ("executed_instances","reused_instances","shacl_calls")} for s in ("full","selective")}}
    x,y = summarize(comprehensive),summarize(representative)
    assert x["full"]["executed_instances"]==4661 and x["selective"]["executed_instances"]==1459
    assert y["full"]["executed_instances"]==2730 and y["selective"]["executed_instances"]==645
    for s in ("full","selective"):
        assert isclose(sum(e[s]["elapsed_seconds"] for e in comprehensive),a["summary"]["median_seconds"][s])
    for n in b["config"]["scenarios"]:
        rows = [e for e in representative if e["scenario"]==n]
        for s in ("full","selective"):
            t = [e[s]["elapsed_seconds"] for e in rows]
            for k,v in (("median_seconds",median(t)),("min_seconds",min(t)),("max_seconds",max(t))):
                assert isclose(v,b["summary"][n][s][k])
    print(json.dumps({"comprehensive":x,"representative":y,"hashes":hashes},indent=2))
    print("Archived records verified; no SHACL execution performed.")

if __name__=="__main__":
    main()
