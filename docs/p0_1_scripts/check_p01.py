"""P0-1 re-run assertions over the probe response bodies (NEW-1122). Reads only RESP dir files.

Usage: python3 docs/p0_1_scripts/check_p01.py RESP_DIR
Prints one PASS/FAIL line per assertion with the measured value. Exit 1 if any FAIL.
"""
import json
import os
import sys

R = sys.argv[1]
NOTE_A = "INTERNAL-NOTE-INV-A"
NOTE_B = "INTERNAL-NOTE-INV-B"
COST_KEYS = ("cost", "unit_cost", "category")
results = []


def body(label):
    with open(os.path.join(R, label + ".body")) as f:
        return f.read()


def code(label):
    for line in open(os.path.join(R, "codes.txt")):
        l, c = line.split()
        if l == label:
            return int(c)
    raise KeyError(label)


def js(label):
    try:
        return json.loads(body(label))
    except ValueError:
        return None


def check(name, ok, measured):
    results.append((name, bool(ok), measured))


def keyset_walk(obj, keys, path=""):
    """return list of (path) where a dict key in keys appears"""
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys:
                hits.append(f"{path}.{k}")
            hits += keyset_walk(v, keys, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += keyset_walk(v, keys, f"{path}[{i}]")
    return hits


# ---- custA invoice redaction
for lab in ("custA-GET-invoices-1", "custA-GET-invoices-list", "custA-GET-portal-invoices"):
    raw = body(lab)
    j = js(lab)
    invs = [j["invoice"]] if "invoice" in j else j.get("invoices", [])
    check(f"{lab}: HTTP 200", code(lab) == 200, f"HTTP {code(lab)}")
    check(f"{lab}: notes null on every invoice", invs and all(i.get("notes") is None for i in invs), [i.get("notes") for i in invs])
    check(f"{lab}: INTERNAL-NOTE absent from whole body", "INTERNAL-NOTE" not in raw, "absent" if "INTERNAL-NOTE" not in raw else "PRESENT")
    pays = [p for i in invs for p in i.get("payments", [])]
    check(f"{lab}: payments[] non-empty (exercised)", len(pays) > 0, f"{len(pays)} payment(s)")
    check(f"{lab}: payments have no recorded_by_user_id", pays and not any("recorded_by_user_id" in p for p in pays), [sorted(p.keys()) for p in pays][:1])
    check(f"{lab}: amount/balance_due/line_items intact", invs and all(("amount" in i and "balance_due" in i and "line_items" in i) for i in invs), [(i.get("amount"), i.get("balance_due"), i.get("line_items")) for i in invs])

# ---- custA estimate redaction
for lab in ("custA-GET-estimates-1", "custA-GET-estimates-list"):
    j = js(lab)
    ests = [j["estimate"]] if "estimate" in j else j.get("estimates", [])
    lines = [l for e in ests for l in (e.get("line_items") or [])]
    check(f"{lab}: HTTP 200", code(lab) == 200, f"HTTP {code(lab)}")
    check(f"{lab}: no cost/unit_cost/category keys anywhere", not keyset_walk(j, COST_KEYS), keyset_walk(j, COST_KEYS))
    check(f"{lab}: lines present and carry description/quantity/unit_price", lines and all(all(k in l for k in ("description", "quantity", "unit_price")) for l in lines), [sorted(l.keys()) for l in lines])
    check(f"{lab}: estimate notes null", ests and all(e.get("notes") is None for e in ests), [e.get("notes") for e in ests])
    check(f"{lab}: INTERNAL-NOTE absent", "INTERNAL-NOTE" not in body(lab), "absent" if "INTERNAL-NOTE" not in body(lab) else "PRESENT")

# ---- custA global search: no invoice/estimate hits
for lab in ("custA-SEARCH-note", "custA-SEARCH-B-note"):
    j = js(lab)
    check(f"{lab}: no invoice hits", j is not None and len(j.get("results", j).get("invoices", [])) == 0, body(lab)[:400])
    check(f"{lab}: no estimate hits", j is not None and len(j.get("results", j).get("estimates", [])) == 0, "see body")
    # the response echoes the caller's own query string, so assert on the results section only
    check(f"{lab}: INTERNAL-NOTE absent from results section", "INTERNAL-NOTE" not in json.dumps((j or {}).get("results", {})), "absent" if "INTERNAL-NOTE" not in json.dumps((j or {}).get("results", {})) else "PRESENT")

# ---- staff negative controls
for lab in ("admin-GET-invoices-1", "admin-GET-invoices-list", "manager-GET-invoices-1", "manager-GET-invoices-list", "sales-GET-invoices-1"):
    check(f"{lab}: still shows INTERNAL-NOTE-INV-A", NOTE_A in body(lab), f"HTTP {code(lab)} note_present={NOTE_A in body(lab)}")
    check(f"{lab}: payments still carry recorded_by_user_id", "recorded_by_user_id" in body(lab), f"present={'recorded_by_user_id' in body(lab)}")
for lab in ("admin-GET-estimates-1", "admin-GET-estimates-list", "manager-GET-estimates-1", "sales-GET-estimates-1", "sales-GET-estimates-list"):
    check(f"{lab}: cost/unit_cost/category still present", all(k in body(lab) for k in ('"cost"', '"unit_cost"', '"category"')) if code(lab) == 200 else False, f"HTTP {code(lab)} keys={[k for k in COST_KEYS if k in body(lab)]}")
for lab in ("admin-SEARCH-note", "manager-SEARCH-note", "sales-SEARCH-note"):
    check(f"{lab}: staff search finds internal note", "INTERNAL-NOTE" in body(lab), f"HTTP {code(lab)} hits_inv={NOTE_A in body(lab) or NOTE_B in body(lab)}")

# ---- custC custom-perm customer
check("custC-GET-invoices-3: own invoice redacted (notes null, note absent)", code("custC-GET-invoices-3") == 200 and js("custC-GET-invoices-3")["invoice"]["notes"] is None and "INTERNAL-NOTE-INV-C" not in body("custC-GET-invoices-3"), f"HTTP {code('custC-GET-invoices-3')}")
check("custC-PAY-own-3: own pay returns redacted response", code("custC-PAY-own-3") == 200 and "INTERNAL-NOTE-INV-C" not in body("custC-PAY-own-3") and "recorded_by_user_id" not in body("custC-PAY-own-3") and js("custC-PAY-own-3")["invoice"]["notes"] is None, f"HTTP {code('custC-PAY-own-3')}")
check("custC-PAY-B-2: paying B's invoice -> 403", code("custC-PAY-B-2") == 403, f"HTTP {code('custC-PAY-B-2')}")
check("custC-GET-invoices-2: B's invoice -> 403", code("custC-GET-invoices-2") == 403, f"HTTP {code('custC-GET-invoices-2')}")
check("B invoice unchanged by all probes (admin before == after)", body("admin-GET-invoices-B-before") == body("admin-GET-invoices-B-after"), "identical" if body("admin-GET-invoices-B-before") == body("admin-GET-invoices-B-after") else "CHANGED")

# ---- earlier RUN 2 isolation checks (unchanged expectations)
expect = {
    "custA-GET-projects-1": 200, "custA-GET-projects-2": 403, "custA-GET-invoices-2": 403,
    "custA-GET-contracts-1": 200, "custA-GET-contracts-2": 403,
    "custA-GET-documents-1": 200, "custA-GET-documents-2": 403, "custA-GET-documents-2-download": 403,
    "custA-GET-documents-1-download": 200, "custA-GET-estimates-2": 403,
    "custA-GET-estimator-own": 200, "custA-GET-estimator-B": 403,
    "custA-GET-customers-1": 200, "custA-GET-customers-2": 403, "custA-GET-milestones-B": 403,
    "custA-GET-portal-projects-2": 403, "custB-GET-invoices-2": 200, "custB-GET-invoices-1": 403,
    "custA-DENY-pay-B": 403, "custA-DENY-customer-B-update": 403, "custA-DENY-project-B-update": 403,
    "custA-DENY-estimator-B-line": 403, "custA-POSITIVE-portal-message": 201,
    "noauth-portal-projects": 401, "noauth-projects-1": 401, "garbage-bearer-portal-projects": 401,
    "garbage-bearer-projects-1": 401, "garbage-query-token": 401,
    "tech-GET-invoices": 403, "tech-GET-customers": 403, "tech-GET-communications": 403,
}
for lab, want in expect.items():
    check(f"{lab}: HTTP {want}", code(lab) == want, f"HTTP {code(lab)}")
# bypass params must not leak B's rows
for lab in ("custA-BYPASS-communications", "custA-BYPASS-documents", "custA-BYPASS-invoices", "custA-BYPASS-estimates", "custA-BYPASS-projects", "custA-BYPASS-portal-projects", "custA-BYPASS-portal-invoices", "custA-BYPASS-portal-documents"):
    check(f"{lab}: no B rows (no 'B-PRIVATE-MSG-XYZ', no 'Bob Bravo', no INV-B)", code(lab) == 200 and not any(s in body(lab) for s in ("B-PRIVATE-MSG-XYZ", "Bob Bravo", "INV-B-001", "INTERNAL-NOTE-B", "B St 1")), f"HTTP {code(lab)}")
check("custA-GET-users: 403 (no user list)", code("custA-GET-users") == 403, f"HTTP {code('custA-GET-users')}")
check("custA-GET-portal-projects: only own project id 1", code("custA-GET-portal-projects") == 200 and [p["id"] for p in js("custA-GET-portal-projects")["projects"]] == [1], body("custA-GET-portal-projects")[:120])
check("custB-GET-portal-messages: own message only (B-PRIVATE present, A-OWN absent)", "B-PRIVATE-MSG-XYZ" in body("custB-GET-portal-messages") and "A-OWN-MSG-123" not in body("custB-GET-portal-messages"), "checked")
check("custA-GET-portal-messages: A-OWN present, B-PRIVATE absent", "A-OWN-MSG-123" in body("custA-GET-portal-messages") and "B-PRIVATE-MSG-XYZ" not in body("custA-GET-portal-messages"), "checked")

width = max(len(n) for n, _, _ in results)
fails = 0
for name, ok, meas in results:
    fails += (not ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}  | measured: {meas}")
print(f"TOTAL {len(results)} assertions, {fails} FAIL")
sys.exit(1 if fails else 0)
