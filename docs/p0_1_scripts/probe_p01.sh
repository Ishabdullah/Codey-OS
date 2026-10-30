#!/usr/bin/env bash
# P0-1 re-run probes (NEW-1122). Each request is its own curl process; proxies unset; no shared client state.
# Usage: probe_p01.sh SCRATCH_DIR RESP_DIR   (world must be active: eval "$(python3 -m tools.world env p01rerun)")
# Writes RESP_DIR/<label>.body and prints "### [label] METHOD PATH -> HTTP code" + body to stdout.
set -u
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
S="$1"; RESP="$2"; mkdir -p "$RESP"; : > "$RESP/codes.txt"
PORT="${RESTORICON_API_PORT:?world env not loaded}"
PY=/data/data/com.termux/files/usr/bin/python3
tok() { "$PY" -c "import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$S/tokens.json" "$1"; }
getid() { "$PY" -c "import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$S/ids.json" "$2"; }

req() { # label method path token [json_body]
  local label="$1" m="$2" p="$3" t="$4" b="${5:-}"
  local args=(-s --noproxy '*' -o "$RESP/$label.body" -w '%{http_code}' -X "$m")
  [ -n "$t" ] && args+=(-H "Authorization: Bearer $t")
  [ -n "$b" ] && args+=(-H 'Content-Type: application/json' --data "$b")
  local code
  code=$(curl "${args[@]}" "http://127.0.0.1:$PORT$p")
  echo "$label $code" >> "$RESP/codes.txt"
  echo "### [$label] $m $p -> HTTP $code"
  cat "$RESP/$label.body"; echo
}

A=$(tok custA); B=$(tok custB); C=$(tok custC); T=$(tok tech); G=$(tok agent); SL=$(tok sales); M=$(tok manager); AD=$(tok admin)
iA=$(getid ids inv_A); iB=$(getid ids inv_B); iC=$(getid ids inv_C)
eA=$(getid ids est_A); eB=$(getid ids est_B); bA=$(getid ids best_A); bB=$(getid ids best_B)

echo "## STEP baseline admin snapshot of B invoice (for unchanged-check)"
req admin-GET-invoices-B-before GET "/api/v1/invoices/$iB" "$AD"

echo "## section 1: custA on own objects (positive) and B objects (denials)"
req custA-GET-projects-1 GET /api/v1/projects/1 "$A"
req custA-GET-projects-2 GET /api/v1/projects/2 "$A"
req custA-GET-invoices-1 GET "/api/v1/invoices/$iA" "$A"
req custA-GET-invoices-2 GET "/api/v1/invoices/$iB" "$A"
req custA-GET-invoices-list GET /api/v1/invoices "$A"
req custA-GET-portal-invoices GET /api/v1/portal/invoices "$A"
req custA-GET-contracts-1 GET /api/v1/contracts/1 "$A"
req custA-GET-contracts-2 GET /api/v1/contracts/2 "$A"
req custA-GET-documents-1 GET /api/v1/documents/1 "$A"
req custA-GET-documents-2 GET /api/v1/documents/2 "$A"
req custA-GET-documents-2-download GET /api/v1/documents/2/download "$A"
req custA-GET-documents-1-download GET /api/v1/documents/1/download "$A"
req custA-GET-estimates-1 GET "/api/v1/estimates/$eA" "$A"
req custA-GET-estimates-2 GET "/api/v1/estimates/$eB" "$A"
req custA-GET-estimates-list GET /api/v1/estimates "$A"
req custA-GET-estimator-own GET "/api/v1/estimator/estimates/$bA" "$A"
req custA-GET-estimator-B GET "/api/v1/estimator/estimates/$bB" "$A"
req custA-GET-customers-1 GET /api/v1/customers/1 "$A"
req custA-GET-customers-2 GET /api/v1/customers/2 "$A"
req custA-GET-customers-list GET /api/v1/customers "$A"
req custA-GET-milestones-B GET /api/v1/operations/projects/2/milestones "$A"
req custA-GET-portal-profile GET /api/v1/portal/profile "$A"
req custA-GET-portal-projects GET /api/v1/portal/projects "$A"
req custA-GET-portal-projects-2 GET /api/v1/portal/projects/2 "$A"
req custA-GET-portal-estimates GET /api/v1/portal/estimates "$A"
req custA-GET-portal-messages GET /api/v1/portal/messages "$A"
req custA-GET-communications GET /api/v1/communications "$A"
req custA-GET-documents-list GET /api/v1/documents "$A"
req custA-GET-users GET /api/v1/users "$A"

echo "## section 2: custB positive controls on own objects"
req custB-GET-invoices-2 GET "/api/v1/invoices/$iB" "$B"
req custB-GET-invoices-1 GET "/api/v1/invoices/$iA" "$B"
req custB-GET-portal-estimates GET /api/v1/portal/estimates "$B"
req custB-GET-portal-messages GET /api/v1/portal/messages "$B"

echo "## section 3: bypass / filter params as custA (must leak nothing of B)"
req custA-BYPASS-communications GET "/api/v1/communications?customer_id=2" "$A"
req custA-BYPASS-documents GET "/api/v1/documents?customer_id=2" "$A"
req custA-BYPASS-invoices GET "/api/v1/invoices?customer_id=2" "$A"
req custA-BYPASS-estimates GET "/api/v1/estimates?customer_id=2" "$A"
req custA-BYPASS-projects GET "/api/v1/projects?customer_id=2" "$A"
req custA-BYPASS-portal-projects GET "/api/v1/portal/projects?customer_id=2" "$A"
req custA-BYPASS-portal-invoices GET "/api/v1/portal/invoices?project_id=2" "$A"
req custA-BYPASS-portal-documents GET "/api/v1/portal/documents?project_id=2" "$A"

echo "## section 4: global search (NEW-1122 search oracle)"
req custA-SEARCH-note GET "/api/v1/search?q=INTERNAL-NOTE" "$A"
req custA-SEARCH-B-note GET "/api/v1/search?q=INTERNAL-NOTE-INV-B" "$A"
req admin-SEARCH-note GET "/api/v1/search?q=INTERNAL-NOTE" "$AD"
req manager-SEARCH-note GET "/api/v1/search?q=INTERNAL-NOTE" "$M"
req sales-SEARCH-note GET "/api/v1/search?q=INTERNAL-NOTE" "$SL"

echo "## section 5: staff negative controls (must still see notes and cost keys)"
req admin-GET-invoices-1 GET "/api/v1/invoices/$iA" "$AD"
req admin-GET-invoices-list GET /api/v1/invoices "$AD"
req manager-GET-invoices-1 GET "/api/v1/invoices/$iA" "$M"
req manager-GET-invoices-list GET /api/v1/invoices "$M"
req sales-GET-invoices-1 GET "/api/v1/invoices/$iA" "$SL"
req admin-GET-estimates-1 GET "/api/v1/estimates/$eA" "$AD"
req admin-GET-estimates-list GET /api/v1/estimates "$AD"
req manager-GET-estimates-1 GET "/api/v1/estimates/$eA" "$M"
req sales-GET-estimates-1 GET "/api/v1/estimates/$eA" "$SL"
req sales-GET-estimates-list GET /api/v1/estimates "$SL"
req admin-GET-estimator-A GET "/api/v1/estimator/estimates/$bA" "$AD"
req tech-GET-invoices GET /api/v1/invoices "$T"
req tech-GET-customers GET /api/v1/customers "$T"
req tech-GET-communications GET /api/v1/communications "$T"
req agent-GET-invoices GET /api/v1/invoices "$G"
req agent-GET-communications GET /api/v1/communications "$G"

echo "## section 6: custom-perm customer C (write:financials)"
req custC-GET-invoices-3 GET "/api/v1/invoices/$iC" "$C"
req custC-PAY-own-3 POST "/api/v1/invoices/$iC/pay" "$C" '{"amount": 50.0, "payment_method": "check", "reference": "C-SELF-PAY"}'
req custC-PAY-B-2 POST "/api/v1/invoices/$iB/pay" "$C" '{"amount": 1.0, "payment_method": "check", "reference": "C-ON-B"}'
req custC-GET-invoices-2 GET "/api/v1/invoices/$iB" "$C"
req admin-GET-invoices-C-after-pay GET "/api/v1/invoices/$iC" "$AD"

echo "## section 7: writes on B denied to custA; own portal write works"
req custA-DENY-pay-B POST "/api/v1/invoices/$iB/pay" "$A" '{"amount": 1.0, "payment_method": "check", "reference": "A-ON-B"}'
req custA-DENY-customer-B-update POST /api/v1/customers/2/update "$A" '{"notes": "HACKED"}'
req custA-DENY-project-B-update POST /api/v1/projects/2/update "$A" '{"notes": "HACKED"}'
req custA-DENY-estimator-B-line POST "/api/v1/estimator/estimates/$bB/lines" "$A" '{"description":"x","unit_cost_cents":1}'
req custA-DENY-contract-B-sign POST /api/v1/portal/contracts/2/sign "$A" '{"signature_data": "data:image/png;base64,AAAA"}'
req custA-POSITIVE-portal-message POST /api/v1/portal/messages "$A" '{"content": "A-SECOND-MSG-OK", "subject": "Portal Message"}'

echo "## section 8: auth 401s"
req noauth-portal-projects GET /api/v1/portal/projects ""
req noauth-projects-1 GET /api/v1/projects/1 ""
req garbage-bearer-portal-projects GET /api/v1/portal/projects "garbage-token-not-a-real-token"
req garbage-bearer-projects-1 GET /api/v1/projects/1 "garbage-token-not-a-real-token"
req garbage-query-token GET "/api/v1/portal/projects?token=garbage-token-not-a-real-token" ""

echo "## section 9: admin after-state of B invoice (unchanged-check)"
req admin-GET-invoices-B-after GET "/api/v1/invoices/$iB" "$AD"
req admin-GET-invoices-A-after GET "/api/v1/invoices/$iA" "$AD"
echo "## done"
