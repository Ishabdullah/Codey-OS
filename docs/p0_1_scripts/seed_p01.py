"""P0-1 re-run seed (NEW-1122 re-verification). Disposable world ONLY.

Usage (after `eval "$(python3 -m tools.world env NAME)"` in the same shell):
    python3 docs/p0_1_scripts/seed_p01.py bootstrap      # in-process: creates the admin user (no server yet)
    python3 docs/p0_1_scripts/seed_p01.py seed OUT_DIR   # over HTTP against RESTORICON_API_PORT; writes OUT_DIR/ids.json, OUT_DIR/tokens.json

Refuses to run unless RESTORICON_WORLD_NAME is set and RESTORICON_DB_PATH is inside a world state dir.
Uses http.client (no proxy handling). Never passes --world production.
"""
import http.client
import json
import os
import sys

PW = "Passw0rd123!"


def _guard():
    name = os.environ.get("RESTORICON_WORLD_NAME", "")
    db = os.environ.get("RESTORICON_DB_PATH", "")
    if not name or "/.codeyOS-worlds/" not in db or "/.codeyOS/" in db:
        sys.exit("refusing: not inside a disposable world (RESTORICON_WORLD_NAME / RESTORICON_DB_PATH)")


def bootstrap():
    _guard()
    from restoricon_core.database import DatabaseManager
    from restoricon_core.auth import AuthService

    db = DatabaseManager()
    auth = AuthService(db)
    u = auth.create_user("admin_p01", PW, "World Admin", "admin@p01.test", role="admin")
    print("bootstrapped admin id", u.id)


class Api:
    def __init__(self):
        self.port = int(os.environ["RESTORICON_API_PORT"])
        self.token = None

    def call(self, method, path, body=None, token=None, raw=None, ctype="application/json"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        headers = {}
        tok = token or self.token
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
        data = None
        if raw is not None:
            data = raw
            headers["Content-Type"] = ctype
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=headers)
        r = conn.getresponse()
        txt = r.read().decode(errors="replace")
        conn.close()
        print(f"### {method} {path} -> HTTP {r.status}\n{txt[:600]}")
        try:
            return r.status, json.loads(txt)
        except ValueError:
            return r.status, txt


def multipart(fields, filename, content):
    b = "----p01boundary"
    parts = []
    for k, v in fields.items():
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    parts.append(
        f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/plain\r\n\r\n{content}\r\n--{b}--\r\n"
    )
    return "".join(parts).encode(), f"multipart/form-data; boundary={b}"


def seed(outdir):
    _guard()
    os.makedirs(outdir, exist_ok=True)
    api = Api()
    ids, toks = {}, {}
    st, r = api.call("POST", "/api/v1/auth/login", {"username": "admin_p01", "password": PW})
    api.token = r["token"]
    toks["admin"] = r["token"]

    def mk_customer(key, first, last, email, note):
        _, r = api.call("POST", "/api/v1/customers", {"first_name": first, "last_name": last, "email": email, "phone": "555", "notes": note})
        ids[f"cust_{key}"] = r["customer"]["id"]

    mk_customer("A", "Alice", "Alpha", "alice@custA.test", "INTERNAL-NOTE-A: margin target 42pct")
    mk_customer("B", "Bob", "Bravo", "bob@custB.test", "INTERNAL-NOTE-B: margin target 42pct")
    mk_customer("C", "Carl", "Charlie", "carl@custC.test", "INTERNAL-NOTE-C")

    def mk_user(key, username, role, **kw):
        body = {"username": username, "password": PW, "full_name": username, "email": f"{username}@p01.test", "role": role}
        body.update(kw)
        _, r = api.call("POST", "/api/v1/users", body)
        ids[f"user_{key}"] = r["user"]["id"]

    mk_user("custA", "custa", "customer", customer_id=ids["cust_A"])
    mk_user("custB", "custb", "customer", customer_id=ids["cust_B"])
    mk_user("custC", "custc", "customer", customer_id=ids["cust_C"], custom_permissions={"write:financials": True})
    mk_user("tech", "tech_p01", "technician")
    mk_user("agent", "agent_p01", "ai_agent")
    mk_user("sales", "sales_p01", "sales")
    mk_user("manager", "manager_p01", "manager")

    def mk_project(key, cust):
        _, r = api.call("POST", "/api/v1/projects", {"customer_id": cust, "title": f"Project {key} kitchen", "property_address": f"{key} St 1", "project_type": "remodel", "notes": f"INTERNAL-NOTE-PROJ-{key}"})
        ids[f"proj_{key}"] = r["project"]["id"]

    mk_project("A", ids["cust_A"])
    mk_project("B", ids["cust_B"])
    mk_project("C", ids["cust_C"])

    def mk_invoice(key, cust, proj, num, amount, note):
        _, r = api.call("POST", "/api/v1/invoices", {"customer_id": cust, "project_id": proj, "invoice_number": num, "amount": amount, "notes": note})
        ids[f"inv_{key}"] = r["invoice"]["id"]

    mk_invoice("A", ids["cust_A"], ids["proj_A"], "INV-A-001", 5000.0, "INTERNAL-NOTE-INV-A")
    mk_invoice("B", ids["cust_B"], ids["proj_B"], "INV-B-001", 7000.0, "INTERNAL-NOTE-INV-B")
    mk_invoice("C", ids["cust_C"], ids["proj_C"], "INV-C-001", 900.0, "INTERNAL-NOTE-INV-C")

    # payments recorded by admin (so recorded_by_user_id is populated)
    api.call("POST", f"/api/v1/invoices/{ids['inv_A']}/pay", {"amount": 1000.0, "payment_method": "check", "reference": "REF-A-1"})
    api.call("POST", f"/api/v1/invoices/{ids['inv_B']}/pay", {"amount": 2000.0, "payment_method": "check", "reference": "REF-B-1"})

    # legacy estimates: lines carry cost AND unit_cost AND category (NEW-1122 leak shape); EST-A assigned to sales
    legacy_lines = [{"description": "demo", "cost": 1234.0, "unit_cost": 99.0, "category": "labor", "quantity": 2, "unit_price": 150.0}]
    # create-time assignment is forced to the acting user (run 1: a supplied assigned_user_id was ignored),
    # so EST-A is created BY the sales user to make it assigned to sales.
    _, r = api.call("POST", "/api/v1/auth/login", {"username": "sales_p01", "password": PW})
    sales_tok = r["token"]
    _, r = api.call("POST", "/api/v1/estimates", {"customer_id": ids["cust_A"], "project_id": ids["proj_A"], "estimate_number": "EST-A-001", "line_items": legacy_lines, "notes": "INTERNAL-NOTE-EST-A"}, token=sales_tok)
    ids["est_A"] = r["estimate"]["id"]
    _, r = api.call("POST", "/api/v1/estimates", {"customer_id": ids["cust_B"], "project_id": ids["proj_B"], "estimate_number": "EST-B-001", "line_items": legacy_lines, "notes": "INTERNAL-NOTE-EST-B"})
    ids["est_B"] = r["estimate"]["id"]

    # estimator estimates (for the earlier RUN 2 checks): A and B, with one line each
    _, r = api.call("POST", "/api/v1/estimator/estimates", {"customer_id": ids["cust_A"], "project_id": ids["proj_A"], "title": "Estimator A kitchen"})
    ids["best_A"] = r["estimate"]["id"]
    _, r = api.call("POST", "/api/v1/estimator/estimates", {"customer_id": ids["cust_B"], "project_id": ids["proj_B"], "title": "Estimator B kitchen"})
    ids["best_B"] = r["estimate"]["id"]
    _, r = api.call("POST", f"/api/v1/estimator/estimates/{ids['best_A']}/lines", {"description": "INTERNAL-COST-LINE-A cabinets", "line_type": "material", "quantity": 2, "unit": "ea", "unit_cost_cents": 150000, "material_markup_bp": 3000})
    api.call("PATCH", f"/api/v1/estimator/estimates/{ids['best_A']}/lines/{r['line']['id']}", {"customer_description": "Kitchen cabinets (customer view)"})
    _, r = api.call("POST", f"/api/v1/estimator/estimates/{ids['best_B']}/lines", {"description": "INTERNAL-COST-LINE-B cabinets", "line_type": "material", "quantity": 2, "unit": "ea", "unit_cost_cents": 150000, "material_markup_bp": 3000})
    api.call("PATCH", f"/api/v1/estimator/estimates/{ids['best_B']}/lines/{r['line']['id']}", {"customer_description": "Kitchen cabinets B (customer view)"})

    # contracts + documents
    _, r = api.call("POST", "/api/v1/contracts", {"customer_id": ids["cust_A"], "project_id": ids["proj_A"], "title": "Contract A", "content": "Scope for customer A. INTERNAL-NOTE-CON-A", "contract_number": "CON-A-001"})
    ids["con_A"] = r["contract"]["id"]
    _, r = api.call("POST", "/api/v1/contracts", {"customer_id": ids["cust_B"], "project_id": ids["proj_B"], "title": "Contract B", "content": "Scope for customer B. INTERNAL-NOTE-CON-B", "contract_number": "CON-B-001"})
    ids["con_B"] = r["contract"]["id"]
    for key, cust, proj in (("A", "cust_A", "proj_A"), ("B", "cust_B", "proj_B")):
        raw, ct = multipart({"customer_id": ids[cust], "project_id": ids[proj], "document_type": "contract", "title": f"Doc-{key}-signed-scope"}, f"scope_{key}.txt", f"SCOPE-DOC-CONTENT-{key}")
        _, r = api.call("POST", "/api/v1/documents", raw=raw, ctype=ct)
        ids[f"doc_{key}"] = r["document"]["id"] if isinstance(r, dict) and "document" in r else None

    # custom-perm customer C: own invoice already seeded; nothing else needed
    # tokens
    for who, user in (("custA", "custa"), ("custB", "custb"), ("custC", "custc"), ("tech", "tech_p01"), ("agent", "agent_p01"), ("sales", "sales_p01"), ("manager", "manager_p01")):
        _, r = api.call("POST", "/api/v1/auth/login", {"username": user, "password": PW})
        toks[who] = r["token"]

    # portal messages from each customer (own) and an ai_agent comm for customer A
    api.call("POST", "/api/v1/portal/messages", {"content": "B-PRIVATE-MSG-XYZ", "subject": "Portal Message"}, token=toks["custB"])
    api.call("POST", "/api/v1/portal/messages", {"content": "A-OWN-MSG-123", "subject": "Portal Message"}, token=toks["custA"])
    api.call("POST", "/api/v1/communications", {"customer_id": ids["cust_A"], "channel": "email", "direction": "outbound", "subject": "AGENT-SUBJ-A", "content": "AGENT-AUTHORED-COMM-A"}, token=toks["agent"])

    with open(os.path.join(outdir, "ids.json"), "w") as f:
        json.dump(ids, f, indent=1)
    with open(os.path.join(outdir, "tokens.json"), "w") as f:
        json.dump(toks, f, indent=1)
    print("IDS", json.dumps(ids))


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "bootstrap":
        bootstrap()
    elif len(sys.argv) == 3 and sys.argv[1] == "seed":
        seed(sys.argv[2])
    else:
        sys.exit(__doc__)
