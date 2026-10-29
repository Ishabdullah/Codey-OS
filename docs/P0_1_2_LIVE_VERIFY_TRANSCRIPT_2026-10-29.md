# P0-1 / P0-2 transcript (world p012) started 2026-10-29T06:02:10-04:00
## STEP 1 baseline
$ free -h
               total        used        free      shared  buff/cache   available
Mem:            10Gi       6.1Gi       107Mi        61Mi       5.0Gi       4.7Gi
Swap:           15Gi       2.5Gi        13Gi
$ ps aux | grep -E 'llama|restoricon|api.server'
$ ss -ltnp
Cannot open netlink socket: Permission denied
State Recv-Q Send-Q Local Address:Port Peer Address:PortProcess
$ stat live files
/data/data/com.termux/files/home/.codeyOS/restoricon.db size=4018176 mtime=2026-09-30 17:50:45.731747783 -0400 inode=2724812
/data/data/com.termux/files/home/.codeyOS/restoricon.db-wal size=1281352 mtime=2026-10-24 11:53:26.797089718 -0400 inode=2948088
/data/data/com.termux/files/home/.codeyOS/restoricon.db-shm size=32768 mtime=2026-10-28 17:56:33.473673891 -0400 inode=2948380
/data/data/com.termux/files/home/.codeyOS/action_gateway_audit.jsonl size=51219 mtime=2026-10-28 17:57:27.481673871 -0400 inode=3046699
/data/data/com.termux/files/home/.codeyOS/restoricon_documents size=3452 mtime=2026-09-22 08:11:50.997857761 -0400 inode=2491094
$ port probe 18770 (python connect_ex)
connect_ex 18770 = 111
### POST /api/v1/auth/login (admin)
HTTP 200
{"token": "G0JWy7_Ttwz1N77jYX7hWfkfrtNAykNmXnTCJr37EbY", "user": {"id": 1, "username": "admin_p012", "full_name": "World Admin", "email": "admin@p012.test", "phone": null, "role": "admin", "department": null, "customer_id": null, "custom_permissions": {}, "active": 1, "terminated_at": null, "territory_id": null, "subcontractor_id": null, "created_at": "2026-10-29T10:02:18.991484+00:00", "updated_at": "2026-10-29T10:02:18.991484+00:00"}}

### POST /api/v1/customers/upsert (A)
HTTP 400
{"error": "upsert_customer requires a non-empty external_id"}

Traceback (most recent call last):
  File "/data/data/com.termux/files/usr/tmp/claude-10247/-data-data-com-termux-files-home-Codey-OS/4c2d13df-1b8e-47d9-90f2-7c2c825a51f8/scratchpad/seed.py", line 18, in <module>
    ids[f"cust_{key}"] = b["customer"]["id"]
                         ~^^^^^^^^^^^^
KeyError: 'customer'
### POST /api/v1/auth/login (admin)
HTTP 200
{"token": "oew7n4zKmpDc4AQpjuR0NeNb25He8Rt6PktrmW42aPQ", "user": {"id": 1, "username": "admin_p012", "full_name": "World Admin", "email": "admin@p012.test", "phone": null, "role": "admin", "department": null, "customer_id": null, "custom_permissions": {}, "active": 1, "terminated_at": null, "territory_id": null, "subcontractor_id": null, "created_at": "2026-10-29T10:02:18.991484+00:00", "updated_at": "2026-10-29T10:02:18.991484+00:00"}}

### POST /api/v1/customers (A)
HTTP 201
{"customer": {"id": 1, "external_id": null, "customer_number": 1, "first_name": "Alice", "last_name": "Alpha", "company_name": null, "phone": "555-010A", "email": "alice@custA.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": "INTERNAL-NOTE-A: margin target 42pct", "custom_fields": {}, "created_at": "2026-10-29T10:02:50.318953+00:00", "last_contact_at": null, "next_followup_at": null}}

### POST /api/v1/customers (B)
HTTP 201
{"customer": {"id": 2, "external_id": null, "customer_number": 2, "first_name": "Bob", "last_name": "Bravo", "company_name": null, "phone": "555-010B", "email": "bob@custB.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": "INTERNAL-NOTE-B: margin target 42pct", "custom_fields": {}, "created_at": "2026-10-29T10:02:50.348786+00:00", "last_contact_at": null, "next_followup_at": null}}

### POST /api/v1/users (customer A login)
HTTP 201
{"user": {"id": 2, "username": "custa", "full_name": "Customer A", "email": "logina@custa.test", "phone": null, "role": "customer", "department": null, "customer_id": 1, "custom_permissions": {}, "active": 1, "terminated_at": null, "territory_id": null, "subcontractor_id": null, "created_at": "2026-10-29T10:02:50.380371+00:00", "updated_at": "2026-10-29T10:02:50.380371+00:00"}}

### POST /api/v1/users (customer B login)
HTTP 201
{"user": {"id": 3, "username": "custb", "full_name": "Customer B", "email": "loginb@custb.test", "phone": null, "role": "customer", "department": null, "customer_id": 2, "custom_permissions": {}, "active": 1, "terminated_at": null, "territory_id": null, "subcontractor_id": null, "created_at": "2026-10-29T10:02:50.477799+00:00", "updated_at": "2026-10-29T10:02:50.477799+00:00"}}

### POST /api/v1/users (technician)
HTTP 201
{"user": {"id": 4, "username": "tech_p012", "full_name": "Tech One", "email": "tech_p012@p012.test", "phone": null, "role": "technician", "department": null, "customer_id": null, "custom_permissions": {}, "active": 1, "terminated_at": null, "territory_id": null, "subcontractor_id": null, "created_at": "2026-10-29T10:02:50.575465+00:00", "updated_at": "2026-10-29T10:02:50.575465+00:00"}}

### POST /api/v1/users (ai_agent)
HTTP 201
{"user": {"id": 5, "username": "agent_p012", "full_name": "Agent One", "email": "agent_p012@p012.test", "phone": null, "role": "ai_agent", "department": null, "customer_id": null, "custom_permissions": {}, "active": 1, "terminated_at": null, "territory_id": null, "subcontractor_id": null, "created_at": "2026-10-29T10:02:50.692815+00:00", "updated_at": "2026-10-29T10:02:50.692815+00:00"}}

### POST /api/v1/projects (A)
HTTP 201
{"project": {"id": 1, "customer_id": 1, "title": "Project A kitchen", "property_address": "A St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 11111.0, "contract_amount": 0.0, "actual_cost": 9999.0, "profit": 1234.5, "notes": "INTERNAL-NOTE-PROJ-A", "warranty_info": null, "stage_entered_at": null, "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.780820+00:00", "updated_at": "2026-10-29T10:02:50.780820+00:00"}}

### POST /api/v1/projects (B)
HTTP 201
{"project": {"id": 2, "customer_id": 2, "title": "Project B kitchen", "property_address": "B St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 22222.0, "contract_amount": 0.0, "actual_cost": 8888.0, "profit": 2345.5, "notes": "INTERNAL-NOTE-PROJ-B", "warranty_info": null, "stage_entered_at": null, "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.803777+00:00", "updated_at": "2026-10-29T10:02:50.803777+00:00"}}

### POST /api/v1/invoices (A)
HTTP 201
{"invoice": {"id": 1, "invoice_number": "INV-A-001", "customer_id": 1, "project_id": 1, "status": "draft", "amount": 5000.0, "deposit_amount": 0.0, "balance_due": 5000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-A", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.836848+00:00", "updated_at": "2026-10-29T10:02:50.836848+00:00"}}

### POST /api/v1/invoices (B)
HTTP 201
{"invoice": {"id": 2, "invoice_number": "INV-B-001", "customer_id": 2, "project_id": 2, "status": "draft", "amount": 7000.0, "deposit_amount": 0.0, "balance_due": 7000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-B", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.876369+00:00", "updated_at": "2026-10-29T10:02:50.876369+00:00"}}

### POST /api/v1/contracts (A)
HTTP 201
{"contract": {"id": 1, "contract_number": "CON-A-001", "customer_id": 1, "project_id": 1, "estimate_id": null, "title": "Contract A", "template_name": null, "content": "Scope for customer A. INTERNAL-NOTE-CON-A", "status": "draft", "customer_signed_at": null, "customer_signature_data": null, "version": 1, "assigned_user_id": 1, "created_at": "2026-10-29T10:02:50.896805+00:00", "updated_at": "2026-10-29T10:02:50.896805+00:00"}}

### POST /api/v1/contracts (B)
HTTP 201
{"contract": {"id": 2, "contract_number": "CON-B-001", "customer_id": 2, "project_id": 2, "estimate_id": null, "title": "Contract B", "template_name": null, "content": "Scope for customer B. INTERNAL-NOTE-CON-B", "status": "draft", "customer_signed_at": null, "customer_signature_data": null, "version": 1, "assigned_user_id": 1, "created_at": "2026-10-29T10:02:50.922326+00:00", "updated_at": "2026-10-29T10:02:50.922326+00:00"}}

### POST /api/v1/estimates legacy (A)
HTTP 201
{"estimate": {"id": 1, "estimate_number": "EST-A-001", "customer_id": 1, "project_id": 1, "line_items": [{"description": "demo", "cost": 1234.0}], "subtotal": 0.0, "materials_cost": 0.0, "labor_cost": 0.0, "subcontractor_cost": 0.0, "markup_percent": 35.0, "tax_amount": 0.0, "discount_amount": 0.0, "total_amount": 0.0, "status": "draft", "expiration_date": null, "version": 1, "notes": "INTERNAL-NOTE-EST-A", "assigned_user_id": 1, "created_at": "2026-10-29T10:02:50.948279+00:00", "updated_at": "2026-10-29T10:02:50.948279+00:00"}}

### POST /api/v1/estimates legacy (B)
HTTP 201
{"estimate": {"id": 2, "estimate_number": "EST-B-001", "customer_id": 2, "project_id": 2, "line_items": [{"description": "demo", "cost": 1234.0}], "subtotal": 0.0, "materials_cost": 0.0, "labor_cost": 0.0, "subcontractor_cost": 0.0, "markup_percent": 35.0, "tax_amount": 0.0, "discount_amount": 0.0, "total_amount": 0.0, "status": "draft", "expiration_date": null, "version": 1, "notes": "INTERNAL-NOTE-EST-B", "assigned_user_id": 1, "created_at": "2026-10-29T10:02:50.977287+00:00", "updated_at": "2026-10-29T10:02:50.977287+00:00"}}

IDS {"cust_A": 1, "cust_B": 2, "user_cust_A": 2, "user_cust_B": 3, "user_technician": 4, "user_ai_agent": 5, "proj_A": 1, "proj_B": 2, "inv_A": 1, "inv_B": 2, "con_A": 1, "con_B": 2, "est_A": 1, "est_B": 2}
### POST /api/v1/auth/login (custA)
HTTP 200
{"token": "a_6TXrFRJGIjA5m6MY9ltmVGhh-3T4pTzVrzS5NFz6c", "user": {"id": 2, "username": "custa", "full_name": "Customer A", "email": "logina@custa.test", "phone": null, "role": "customer", "department": null, "customer_id": 1, "custom_permissions": {}, "active": 1, "terminated_at": null, "territory_id": null, "subcontractor_id": null, "created_at": "2026-10-29T10:02:50.380371+00:00", "updated_at": "2026-10-29T10:02:50.380371+00:00"}}

### POST /api/v1/auth/login (custB)
HTTP 200
{"token": "Q_YZEKuSVA4e-Heln-NkheBTd_R-G6BfLbqmKkpNJnQ", "user": {"id": 3, "username": "custb", "full_name": "Customer B", "email": "loginb@custb.test", "phone": null, "role": "customer", "department": null, "customer_id": 2, "custom_permissions": {}, "active": 1, "terminated_at": null, "territory_id": null, "subcontractor_id": null, "created_at": "2026-10-29T10:02:50.477799+00:00", "updated_at": "2026-10-29T10:02:50.477799+00:00"}}

### POST /api/v1/auth/login (tech)
HTTP 200
{"token": "ABFBJnblGXz2FdDaF0-KohV3vjgwqCisnR-4Nr_YXgA", "user": {"id": 4, "username": "tech_p012", "full_name": "Tech One", "email": "tech_p012@p012.test", "phone": null, "role": "technician", "department": null, "customer_id": null, "custom_permissions": {}, "active": 1, "terminated_at": null, "territory_id": null, "subcontractor_id": null, "created_at": "2026-10-29T10:02:50.575465+00:00", "updated_at": "2026-10-29T10:02:50.575465+00:00"}}

### POST /api/v1/auth/login (agent)
HTTP 200
{"token": "2FaE1M5YU4zXyd0MAoYNW-8mPvVfzmGugv-nHiEcH9w", "user": {"id": 5, "username": "agent_p012", "full_name": "Agent One", "email": "agent_p012@p012.test", "phone": null, "role": "ai_agent", "department": null, "customer_id": null, "custom_permissions": {}, "active": 1, "terminated_at": null, "territory_id": null, "subcontractor_id": null, "created_at": "2026-10-29T10:02:50.692815+00:00", "updated_at": "2026-10-29T10:02:50.692815+00:00"}}

### POST /api/v1/estimator/estimates (A)
HTTP 201
{"estimate": {"id": 3, "estimate_number": "EST-2026-0001", "customer_id": 1, "project_id": 1, "created_by_user_id": 1, "created_by_name": "World Admin", "assigned_to_user_id": 1, "opportunity_id": null, "lead_id": null, "property_id": null, "title": "Estimator A kitchen", "current_version_id": 1, "accepted_version_id": null, "accepted_at": null, "converted_project_id": null, "contract_id": null, "source": "engine", "workflow_status": "DRAFT", "internal_review_required": 0, "expires_at": "2026-11-28T10:03:35.261867+00:00", "customer_notes": null, "terms": null, "sent_at": null, "last_viewed_at": null, "created_at": "2026-10-29T10:03:35.261770+00:00", "updated_at": "2026-10-29T10:03:35.261770+00:00", "cost_total_cents": null, "gross_profit_cents": null, "gross_margin_bp": null, "total_cents": null, "lines": []}}

### POST /api/v1/estimator/estimates/3/lines (A)
HTTP 400
{"error": "add_line: unknown field(s) ['unit_cost']"}

### POST /api/v1/estimator/estimates (B)
HTTP 201
{"estimate": {"id": 4, "estimate_number": "EST-2026-0002", "customer_id": 2, "project_id": 2, "created_by_user_id": 1, "created_by_name": "World Admin", "assigned_to_user_id": 1, "opportunity_id": null, "lead_id": null, "property_id": null, "title": "Estimator B kitchen", "current_version_id": 2, "accepted_version_id": null, "accepted_at": null, "converted_project_id": null, "contract_id": null, "source": "engine", "workflow_status": "DRAFT", "internal_review_required": 0, "expires_at": "2026-11-28T10:03:35.297698+00:00", "customer_notes": null, "terms": null, "sent_at": null, "last_viewed_at": null, "created_at": "2026-10-29T10:03:35.297592+00:00", "updated_at": "2026-10-29T10:03:35.297592+00:00", "cost_total_cents": null, "gross_profit_cents": null, "gross_margin_bp": null, "total_cents": null, "lines": []}}

### POST /api/v1/estimator/estimates/4/lines (B)
HTTP 400
{"error": "add_line: unknown field(s) ['unit_cost']"}

### POST /api/v1/documents multipart (A)
HTTP 201
{"document": {"id": 1, "customer_id": 1, "project_id": 1, "document_type": "contract", "title": "Doc-A-signed-scope", "file_path": "/data/data/com.termux/files/home/.codeyOS-worlds/p012/state/restoricon_documents/contracts/projects/1/1793268215_scope_A.txt", "file_size_bytes": 0, "mime_type": "application/octet-stream", "tags": [], "permissions": [], "expiration_date": null, "created_at": "2026-10-29T10:03:35.351617+00:00", "updated_at": "2026-10-29T10:03:35.351617+00:00"}}

### POST /api/v1/documents multipart (B)
HTTP 201
{"document": {"id": 2, "customer_id": 2, "project_id": 2, "document_type": "contract", "title": "Doc-B-signed-scope", "file_path": "/data/data/com.termux/files/home/.codeyOS-worlds/p012/state/restoricon_documents/contracts/projects/2/1793268215_scope_B.txt", "file_size_bytes": 0, "mime_type": "application/octet-stream", "tags": [], "permissions": [], "expiration_date": null, "created_at": "2026-10-29T10:03:35.373940+00:00", "updated_at": "2026-10-29T10:03:35.373940+00:00"}}

### POST /api/v1/operations/projects/B/milestones (admin)
HTTP 500
{"error": "Internal server error: ProjectMilestone.__init__() got an unexpected keyword argument 'title'"}

### POST /api/v1/portal/messages (custB, B-only message)
HTTP 201
{"message": {"id": 1, "timestamp": "2026-10-29T10:03:35.401230+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "B-PRIVATE-MSG-XYZ", "actor_id": 3, "actor_role": "customer", "actor_type": "human", "customer_id": 2, "project_id": 2, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}}

### POST /api/v1/portal/messages (custA, A message)
HTTP 201
{"message": {"id": 2, "timestamp": "2026-10-29T10:03:35.418762+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-OWN-MSG-123", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}}

### POST /api/v1/communications (ai_agent, customer A, outbound email)
HTTP 201
{"communication": {"id": 3, "timestamp": "2026-10-29T10:03:35.437385+00:00", "channel": "email", "direction": "outbound", "subject": "AGENT-SUBJ-A", "content": "AGENT-AUTHORED-COMM-A", "actor_id": 5, "actor_role": "ai_agent", "actor_type": "agent", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}}

### POST /api/v1/communications (admin, customer A, outbound email)
HTTP 201
{"communication": {"id": 4, "timestamp": "2026-10-29T10:03:35.455000+00:00", "channel": "email", "direction": "outbound", "subject": "HUMAN-SUBJ-A", "content": "HUMAN-AUTHORED-COMM-A", "actor_id": 1, "actor_role": "admin", "actor_type": "human", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}}

IDS2 {"cust_A": 1, "cust_B": 2, "user_cust_A": 2, "user_cust_B": 3, "user_technician": 4, "user_ai_agent": 5, "proj_A": 1, "proj_B": 2, "inv_A": 1, "inv_B": 2, "con_A": 1, "con_B": 2, "est_A": 1, "est_B": 2, "best_A": 3, "best_A_ver": null, "best_B": 4, "best_B_ver": null, "doc_A": 1, "doc_B": 2}
Traceback (most recent call last):
  File "/data/data/com.termux/files/usr/tmp/claude-10247/-data-data-com-termux-files-home-Codey-OS/4c2d13df-1b8e-47d9-90f2-7c2c825a51f8/scratchpad/seed3.py", line 4, in <module>
    st = json.load(open(sys.argv[2])); ids = st["ids"]; ADMIN = st["admin_token"]
                                                                ~~^^^^^^^^^^^^^^^
KeyError: 'admin_token'
### POST /api/v1/estimator/estimates/3/lines (A)
HTTP 201
{"line": {"id": 1, "estimate_version_id": 1, "sort_order": 0, "line_type": "material", "section": null, "category": null, "description": "INTERNAL-COST-LINE-A cabinets", "customer_description": null, "visible_to_customer": 1, "price_book_item_id": null, "retailer_product_id": null, "price_observation_id": null, "retailer_code_snapshot": null, "product_title_snapshot": null, "package_qty": null, "package_unit": null, "unit_cost_cents": 150000, "quantity": 2.0, "unit": "ea", "waste_pct_bp": 0, "material_markup_bp": 3000, "labor_type": null, "labor_rate_id": null, "labor_qty": null, "labor_unit": null, "labor_cost_rate_cents": null, "labor_bill_rate_cents": null, "equipment_id": null, "equipment_cost_cents": null, "equipment_markup_bp": 0, "subcontractor_id": null, "sub_cost_cents": null, "sub_markup_bp": 0, "taxable": 1, "discount_cents": 0, "price_override_cents": null, "override_reason": null, "packages_needed": 2, "material_cost_cents": 300000, "labor_cost_cents": 0, "cost_total_cents": 300000, "sell_total_cents": 390000, "tax_cents": 0, "line_total_cents": 390000, "internal_note": null, "created_at": "2026-10-29T10:03:57.632470+00:00", "updated_at": "2026-10-29T10:03:57.632470+00:00"}}

### POST /api/v1/estimator/estimates/4/lines (B)
HTTP 201
{"line": {"id": 2, "estimate_version_id": 2, "sort_order": 0, "line_type": "material", "section": null, "category": null, "description": "INTERNAL-COST-LINE-B cabinets", "customer_description": null, "visible_to_customer": 1, "price_book_item_id": null, "retailer_product_id": null, "price_observation_id": null, "retailer_code_snapshot": null, "product_title_snapshot": null, "package_qty": null, "package_unit": null, "unit_cost_cents": 150000, "quantity": 2.0, "unit": "ea", "waste_pct_bp": 0, "material_markup_bp": 3000, "labor_type": null, "labor_rate_id": null, "labor_qty": null, "labor_unit": null, "labor_cost_rate_cents": null, "labor_bill_rate_cents": null, "equipment_id": null, "equipment_cost_cents": null, "equipment_markup_bp": 0, "subcontractor_id": null, "sub_cost_cents": null, "sub_markup_bp": 0, "taxable": 1, "discount_cents": 0, "price_override_cents": null, "override_reason": null, "packages_needed": 2, "material_cost_cents": 300000, "labor_cost_cents": 0, "cost_total_cents": 300000, "sell_total_cents": 390000, "tax_cents": 0, "line_total_cents": 390000, "internal_note": null, "created_at": "2026-10-29T10:03:57.676670+00:00", "updated_at": "2026-10-29T10:03:57.676670+00:00"}}

### POST /api/v1/operations/projects/2/milestones (admin, B)
HTTP 201
{"status": "created", "milestone": {"id": 1, "project_id": 2, "name": "MILESTONE-B-ONLY", "stage": "intake", "target_date": null, "completion_date": null, "status": "pending", "dependencies": [], "notes": "B-INTERNAL-MS-NOTE", "created_at": "2026-10-29T10:03:57.702046+00:00", "updated_at": "2026-10-29T10:03:57.702046+00:00"}}

### GET /api/v1/estimator/estimates/3 (admin, A est, control)
HTTP 200
{"estimate": {"id": 3, "estimate_number": "EST-2026-0001", "customer_id": 1, "project_id": 1, "created_by_user_id": 1, "created_by_name": "World Admin", "assigned_to_user_id": 1, "opportunity_id": null, "lead_id": null, "property_id": null, "title": "Estimator A kitchen", "current_version_id": 1, "accepted_version_id": null, "accepted_at": null, "converted_project_id": null, "contract_id": null, "source": "engine", "workflow_status": "DRAFT", "internal_review_required": 0, "expires_at": "2026-11-28T10:03:35.261867+00:00", "customer_notes": null, "terms": null, "sent_at": null, "last_viewed_at": null, "created_at": "2026-10-29T10:03:35.261770+00:00", "updated_at": "2026-10-29T10:03:35.261770+00:00", "cost_total_cents": 300000, "gross_profit_cents": 90000, "gross_margin_bp": 2308, "total_cents": 390000, "lines": []}}

### POST /api/v1/projects/1/update (ai_agent, A project note)
HTTP 403
{"error": "Actor lacks permission to update projects"}

### POST /api/v1/projects/1/update (admin, human)
HTTP 200
{"project": {"id": 1, "customer_id": 1, "title": "Project A kitchen", "property_address": "A St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 11111.0, "contract_amount": 0.0, "actual_cost": 9999.0, "profit": 1234.5, "notes": "HUMAN-EDITED-NOTE-A", "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.780820+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.780820+00:00", "updated_at": "2026-10-29T10:04:15.134396+00:00"}}

### POST /api/v1/customers/1/update (ai_agent)
HTTP 200
{"customer": {"id": 1, "external_id": null, "customer_number": 1, "first_name": "Alice", "last_name": "Alpha", "company_name": null, "phone": "555-010A", "email": "alice@custa.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": "AGENT-EDITED-NOTE-CUST-A", "custom_fields": {}, "created_at": "2026-10-29T10:02:50.318953+00:00", "last_contact_at": null, "next_followup_at": null}}

## STEP PRE-MATRIX row counts
$ sqlite3(ro) SELECT (SELECT COUNT(*) FROM audit_log) AS audit_rows, (SELECT COUNT(*) FROM communication_history) AS comm_rows
audit_rows | comm_rows
29 | 4

## client pid=20670 ; proxy env (names only, values redacted if any):
CLAUDE_CODE_PROXY_RESOLVES_HOSTS=<set>
## section: NEGATIVE CONTROL + DENIAL for customer A (token=custA) on customer B objects
### [custA] GET /api/v1/projects/1
HTTP 200
{"project": {"id": 1, "customer_id": 1, "title": "Project A kitchen", "property_address": "A St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 0.0, "contract_amount": 0.0, "actual_cost": 0.0, "profit": 0.0, "notes": null, "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.780820+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.780820+00:00", "updated_at": "2026-10-29T10:04:15.134396+00:00"}}

### [custA] GET /api/v1/projects/2
HTTP 403
{"error": "Customer cannot view other customers' projects"}

### [custA] GET /api/v1/invoices/1
HTTP 200
{"invoice": {"id": 1, "invoice_number": "INV-A-001", "customer_id": 1, "project_id": 1, "status": "draft", "amount": 5000.0, "deposit_amount": 0.0, "balance_due": 5000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-A", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.836848+00:00", "updated_at": "2026-10-29T10:02:50.836848+00:00"}}

### [custA] GET /api/v1/invoices/2
HTTP 403
{"error": "Customer cannot access another customer's invoice"}

### [custA] GET /api/v1/contracts/1
HTTP 200
{"contract": {"id": 1, "contract_number": "CON-A-001", "customer_id": 1, "project_id": 1, "estimate_id": null, "title": "Contract A", "template_name": null, "content": "Scope for customer A. INTERNAL-NOTE-CON-A", "status": "draft", "customer_signed_at": null, "customer_signature_data": null, "version": 1, "assigned_user_id": 1, "created_at": "2026-10-29T10:02:50.896805+00:00", "updated_at": "2026-10-29T10:02:50.896805+00:00", "resolved_signed_at": null}}

### [custA] GET /api/v1/contracts/2
HTTP 403
{"error": "Customer cannot access another customer's contract"}

### [custA] GET /api/v1/documents/1
HTTP 200
{"document": {"id": 1, "customer_id": 1, "project_id": 1, "document_type": "contract", "title": "Doc-A-signed-scope", "file_path": "/data/data/com.termux/files/home/.codeyOS-worlds/p012/state/restoricon_documents/contracts/projects/1/1793268215_scope_A.txt", "file_size_bytes": 0, "mime_type": "application/octet-stream", "tags": [], "permissions": [], "expiration_date": null, "created_at": "2026-10-29T10:03:35.351617+00:00", "updated_at": "2026-10-29T10:03:35.351617+00:00"}}

### [custA] GET /api/v1/documents/2
HTTP 403
{"error": "Actor cannot access another customer's document"}

### [custA] GET /api/v1/documents/2/download
HTTP 403
{"error": "Actor cannot access another customer's document"}

### [custA] GET /api/v1/estimates/1
HTTP 200
{"estimate": {"id": 1, "estimate_number": "EST-A-001", "customer_id": 1, "project_id": 1, "line_items": [{"description": "demo", "cost": 1234.0}], "subtotal": 0.0, "materials_cost": 0.0, "labor_cost": 0.0, "subcontractor_cost": 0.0, "markup_percent": 0.0, "tax_amount": 0.0, "discount_amount": 0.0, "total_amount": 0.0, "status": "draft", "expiration_date": null, "version": 1, "notes": null, "assigned_user_id": 1, "created_at": "2026-10-29T10:02:50.948279+00:00", "updated_at": "2026-10-29T10:02:50.948279+00:00"}}

### [custA] GET /api/v1/estimates/2
HTTP 403
{"error": "Customer cannot access another customer's estimate"}

### [custA] GET /api/v1/estimator/estimates/3
HTTP 200
{"estimate": {"id": 3, "estimate_number": "EST-2026-0001", "customer_id": 1, "project_id": 1, "created_by_user_id": 1, "created_by_name": "World Admin", "assigned_to_user_id": 1, "opportunity_id": null, "lead_id": null, "property_id": null, "title": "Estimator A kitchen", "current_version_id": 1, "accepted_version_id": null, "accepted_at": null, "converted_project_id": null, "contract_id": null, "source": "engine", "workflow_status": "DRAFT", "internal_review_required": 0, "expires_at": "2026-11-28T10:03:35.261867+00:00", "customer_notes": null, "terms": null, "sent_at": null, "last_viewed_at": null, "created_at": "2026-10-29T10:03:35.261770+00:00", "updated_at": "2026-10-29T10:03:35.261770+00:00", "cost_total_cents": null, "gross_profit_cents": null, "gross_margin_bp": null, "total_cents": 390000, "lines": []}}

### [custA] GET /api/v1/estimator/estimates/4
HTTP 403
{"error": "Actor lacks permission to view this estimate"}

### [custA] GET /api/v1/customers/1
HTTP 200
{"customer": {"id": 1, "external_id": null, "customer_number": 1, "first_name": "Alice", "last_name": "Alpha", "company_name": null, "phone": "555-010A", "email": "alice@custa.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": null, "custom_fields": {}, "created_at": "2026-10-29T10:02:50.318953+00:00", "last_contact_at": null, "next_followup_at": null}}

### [custA] GET /api/v1/customers/2
HTTP 403
{"error": "Actor lacks permission to access this customer record"}

### [custA] GET /api/v1/operations/projects/2/milestones
HTTP 403
{"error": "Customer cannot view milestones for other customers' projects"}

## section: portal routes, custA token
### [custA] GET /api/v1/portal/profile
HTTP 200
{"profile": {"id": 1, "external_id": null, "customer_number": 1, "first_name": "Alice", "last_name": "Alpha", "company_name": null, "phone": "555-010A", "email": "alice@custa.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": null, "custom_fields": {}, "created_at": "2026-10-29T10:02:50.318953+00:00", "last_contact_at": null, "next_followup_at": null}}

### [custA] GET /api/v1/portal/projects
HTTP 200
{"projects": [{"id": 1, "customer_id": 1, "title": "Project A kitchen", "property_address": "A St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 0.0, "contract_amount": 0.0, "actual_cost": 0.0, "profit": 0.0, "notes": null, "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.780820+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.780820+00:00", "updated_at": "2026-10-29T10:04:15.134396+00:00"}]}

### [custA] GET /api/v1/portal/projects/1
HTTP 200
{"project": {"id": 1, "customer_id": 1, "title": "Project A kitchen", "property_address": "A St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 0.0, "contract_amount": 0.0, "actual_cost": 0.0, "profit": 0.0, "notes": null, "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.780820+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.780820+00:00", "updated_at": "2026-10-29T10:04:15.134396+00:00"}}

### [custA] GET /api/v1/portal/projects/2
HTTP 403
{"error": "Customer cannot view other customers' projects"}

### [custA] GET /api/v1/portal/projects/2/milestones
HTTP 403
{"error": "Customer cannot view milestones for other customers' projects"}

### [custA] GET /api/v1/portal/estimates
HTTP 400
{"error": "line 'line-1' is visible to customer but has no customer_description"}

### [custA] GET /api/v1/portal/contracts
HTTP 200
{"contracts": [{"id": 1, "contract_number": "CON-A-001", "customer_id": 1, "project_id": 1, "estimate_id": null, "title": "Contract A", "template_name": null, "content": "Scope for customer A. INTERNAL-NOTE-CON-A", "status": "draft", "customer_signed_at": null, "customer_signature_data": null, "version": 1, "assigned_user_id": 1, "created_at": "2026-10-29T10:02:50.896805+00:00", "updated_at": "2026-10-29T10:02:50.896805+00:00"}]}

### [custA] GET /api/v1/portal/invoices
HTTP 200
{"invoices": [{"id": 1, "invoice_number": "INV-A-001", "customer_id": 1, "project_id": 1, "status": "draft", "amount": 5000.0, "deposit_amount": 0.0, "balance_due": 5000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-A", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.836848+00:00", "updated_at": "2026-10-29T10:02:50.836848+00:00"}]}

### [custA] GET /api/v1/portal/documents
HTTP 200
{"documents": [{"id": 1, "customer_id": 1, "project_id": 1, "document_type": "contract", "title": "Doc-A-signed-scope", "file_path": "/data/data/com.termux/files/home/.codeyOS-worlds/p012/state/restoricon_documents/contracts/projects/1/1793268215_scope_A.txt", "file_size_bytes": 0, "mime_type": "application/octet-stream", "tags": [], "permissions": [], "expiration_date": null, "created_at": "2026-10-29T10:03:35.351617+00:00", "updated_at": "2026-10-29T10:03:35.351617+00:00"}]}

### [custA] GET /api/v1/portal/messages
HTTP 200
{"messages": [{"id": 2, "timestamp": "2026-10-29T10:03:35.418762+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-OWN-MSG-123", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}]}

## section: portal routes, custB token (positive control for B's own data)
### [custB] GET /api/v1/portal/profile
HTTP 200
{"profile": {"id": 2, "external_id": null, "customer_number": 2, "first_name": "Bob", "last_name": "Bravo", "company_name": null, "phone": "555-010B", "email": "bob@custb.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": null, "custom_fields": {}, "created_at": "2026-10-29T10:02:50.348786+00:00", "last_contact_at": null, "next_followup_at": null}}

### [custB] GET /api/v1/portal/projects
HTTP 200
{"projects": [{"id": 2, "customer_id": 2, "title": "Project B kitchen", "property_address": "B St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 0.0, "contract_amount": 0.0, "actual_cost": 0.0, "profit": 0.0, "notes": null, "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.803777+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.803777+00:00", "updated_at": "2026-10-29T10:02:50.803777+00:00"}]}

### [custB] GET /api/v1/portal/projects/2
HTTP 200
{"project": {"id": 2, "customer_id": 2, "title": "Project B kitchen", "property_address": "B St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 0.0, "contract_amount": 0.0, "actual_cost": 0.0, "profit": 0.0, "notes": null, "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.803777+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.803777+00:00", "updated_at": "2026-10-29T10:02:50.803777+00:00"}}

### [custB] GET /api/v1/portal/projects/2/milestones
HTTP 200
{"milestones": [{"id": 1, "project_id": 2, "name": "MILESTONE-B-ONLY", "stage": "intake", "target_date": null, "completion_date": null, "status": "pending", "dependencies": [], "notes": "B-INTERNAL-MS-NOTE", "created_at": "2026-10-29T10:03:57.702046+00:00", "updated_at": "2026-10-29T10:03:57.702046+00:00"}]}

### [custB] GET /api/v1/portal/messages
HTTP 200
{"messages": [{"id": 1, "timestamp": "2026-10-29T10:03:35.401230+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "B-PRIVATE-MSG-XYZ", "actor_id": 3, "actor_role": "customer", "actor_type": "human", "customer_id": 2, "project_id": 2, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}]}

## section: direct list endpoints as custA
### [custA] GET /api/v1/projects
HTTP 200
{"projects": [{"id": 1, "customer_id": 1, "title": "Project A kitchen", "property_address": "A St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 0.0, "contract_amount": 0.0, "actual_cost": 0.0, "profit": 0.0, "notes": null, "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.780820+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.780820+00:00", "updated_at": "2026-10-29T10:04:15.134396+00:00", "customer_name": "Alice Alpha"}]}

### [custA] GET /api/v1/customers
HTTP 200
{"customers": [{"id": 1, "external_id": null, "customer_number": 1, "first_name": "Alice", "last_name": "Alpha", "company_name": null, "phone": "555-010A", "email": "alice@custa.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": null, "custom_fields": {}, "created_at": "2026-10-29T10:02:50.318953+00:00", "last_contact_at": null, "next_followup_at": null}]}

### [custA] GET /api/v1/invoices
HTTP 200
{"invoices": [{"id": 1, "invoice_number": "INV-A-001", "customer_id": 1, "project_id": 1, "status": "draft", "amount": 5000.0, "deposit_amount": 0.0, "balance_due": 5000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-A", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.836848+00:00", "updated_at": "2026-10-29T10:02:50.836848+00:00"}]}

### [custA] GET /api/v1/contracts
HTTP 200
{"contracts": [{"id": 1, "contract_number": "CON-A-001", "customer_id": 1, "project_id": 1, "estimate_id": null, "title": "Contract A", "template_name": null, "content": "Scope for customer A. INTERNAL-NOTE-CON-A", "status": "draft", "customer_signed_at": null, "customer_signature_data": null, "version": 1, "assigned_user_id": 1, "created_at": "2026-10-29T10:02:50.896805+00:00", "updated_at": "2026-10-29T10:02:50.896805+00:00", "resolved_signed_at": null}]}

### [custA] GET /api/v1/documents
HTTP 200
{"documents": [{"id": 1, "customer_id": 1, "project_id": 1, "document_type": "contract", "title": "Doc-A-signed-scope", "file_path": "/data/data/com.termux/files/home/.codeyOS-worlds/p012/state/restoricon_documents/contracts/projects/1/1793268215_scope_A.txt", "file_size_bytes": 0, "mime_type": "application/octet-stream", "tags": [], "permissions": [], "expiration_date": null, "created_at": "2026-10-29T10:03:35.351617+00:00", "updated_at": "2026-10-29T10:03:35.351617+00:00", "customer_name": "Alice Alpha", "project_name": "Project A kitchen"}]}

### [custA] GET /api/v1/estimates
HTTP 200
{"estimates": [{"id": 3, "estimate_number": "EST-2026-0001", "customer_id": 1, "project_id": 1, "line_items": [], "subtotal": 0.0, "materials_cost": 0.0, "labor_cost": 0.0, "subcontractor_cost": 0.0, "markup_percent": 0.0, "tax_amount": 0.0, "discount_amount": 0.0, "total_amount": 0.0, "status": "draft", "expiration_date": null, "version": 1, "notes": null, "assigned_user_id": null, "created_at": "2026-10-29T10:03:35.261770+00:00", "updated_at": "2026-10-29T10:03:35.261770+00:00"}, {"id": 1, "estimate_number": "EST-A-001", "customer_id": 1, "project_id": 1, "line_items": [{"description": "demo", "cost": 1234.0}], "subtotal": 0.0, "materials_cost": 0.0, "labor_cost": 0.0, "subcontractor_cost": 0.0, "markup_percent": 0.0, "tax_amount": 0.0, "discount_amount": 0.0, "total_amount": 0.0, "status": "draft", "expiration_date": null, "version": 1, "notes": null, "assigned_user_id": 1, "created_at": "2026-10-29T10:02:50.948279+00:00", "updated_at": "2026-10-29T10:02:50.948279+00:00"}]}

### [custA] GET /api/v1/estimator/estimates
HTTP 200
{"estimates": [{"id": 3, "estimate_number": "EST-2026-0001", "customer_id": 1, "project_id": 1, "created_by_user_id": 1, "created_by_name": "World Admin", "assigned_to_user_id": 1, "opportunity_id": null, "lead_id": null, "property_id": null, "title": "Estimator A kitchen", "current_version_id": 1, "accepted_version_id": null, "accepted_at": null, "converted_project_id": null, "contract_id": null, "source": "engine", "workflow_status": "DRAFT", "internal_review_required": 0, "expires_at": "2026-11-28T10:03:35.261867+00:00", "customer_notes": null, "terms": null, "sent_at": null, "last_viewed_at": null, "created_at": "2026-10-29T10:03:35.261770+00:00", "updated_at": "2026-10-29T10:03:35.261770+00:00", "cost_total_cents": null, "gross_profit_cents": null, "gross_margin_bp": null, "total_cents": 390000, "lines": []}, {"id": 1, "estimate_number": "EST-A-001", "customer_id": 1, "project_id": 1, "created_by_user_id": null, "created_by_name": null, "assigned_to_user_id": null, "opportunity_id": null, "lead_id": null, "property_id": null, "title": null, "current_version_id": null, "accepted_version_id": null, "accepted_at": null, "converted_project_id": null, "contract_id": null, "source": "engine", "workflow_status": "DRAFT", "internal_review_required": 0, "expires_at": null, "customer_notes": null, "terms": null, "sent_at": null, "last_viewed_at": null, "created_at": "2026-10-29T10:02:50.948279+00:00", "updated_at": "2026-10-29T10:02:50.948279+00:00", "cost_total_cents": null, "gro

### [custA] GET /api/v1/communications
HTTP 200
{"communications": [{"id": 4, "timestamp": "2026-10-29T10:03:35.455000+00:00", "channel": "email", "direction": "outbound", "subject": "HUMAN-SUBJ-A", "content": "HUMAN-AUTHORED-COMM-A", "actor_id": 1, "actor_role": "admin", "actor_type": "human", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 3, "timestamp": "2026-10-29T10:03:35.437385+00:00", "channel": "email", "direction": "outbound", "subject": "AGENT-SUBJ-A", "content": "AGENT-AUTHORED-COMM-A", "actor_id": 5, "actor_role": "ai_agent", "actor_type": "agent", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 2, "timestamp": "2026-10-29T10:03:35.418762+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-OWN-MSG-123", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}]}

### [custA] GET /api/v1/users
HTTP 403
{"error": "Actor lacks permission to list users"}

## section: write denials as custA (and the positive write control: own portal message)
### [custA-POSITIVE] POST /api/v1/portal/messages
HTTP 201
{"message": {"id": 5, "timestamp": "2026-10-29T10:04:47.043542+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-SECOND-MSG-OK", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}}

### [custA-DENY] POST /api/v1/portal/contracts/2/sign
HTTP 403
{"error": "Customer cannot sign another customer's contract"}

### [custA-DENY] POST /api/v1/estimator/estimates/4/lines
HTTP 403
{"error": "Actor lacks permission to write estimates"}

### [custA-DENY] POST /api/v1/projects/2/update
HTTP 403
{"error": "Actor lacks permission to update projects"}

## section: auth. no token and garbage token must be 401
### [no-token] GET /api/v1/portal/projects
HTTP 401
{"error": "Unauthorized or expired token"}

### [no-token] GET /api/v1/projects/1
HTTP 401
{"error": "Unauthorized or expired token"}

### [garbage-bearer] GET /api/v1/portal/projects
HTTP 401
{"error": "Unauthorized or expired token"}

### [garbage-bearer] GET /api/v1/projects/1
HTTP 401
{"error": "Unauthorized or expired token"}

### [garbage ?token=] GET /api/v1/portal/projects?token=garbage-token-not-a-real-token
HTTP 401
{"error": "Unauthorized or expired token"}

## section: P0-2 role-filtered reads of the same list endpoints (admin / technician / custA)
### [ADMIN] GET /api/v1/invoices
HTTP 200
{"invoices": [{"id": 2, "invoice_number": "INV-B-001", "customer_id": 2, "project_id": 2, "status": "draft", "amount": 7000.0, "deposit_amount": 0.0, "balance_due": 7000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-B", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.876369+00:00", "updated_at": "2026-10-29T10:02:50.876369+00:00"}, {"id": 1, "invoice_number": "INV-A-001", "customer_id": 1, "project_id": 1, "status": "draft", "amount": 5000.0, "deposit_amount": 0.0, "balance_due": 5000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-A", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.836848+00:00", "updated_at": "2026-10-29T10:02:50.836848+00:00"}]}

### [ADMIN] GET /api/v1/customers
HTTP 200
{"customers": [{"id": 2, "external_id": null, "customer_number": 2, "first_name": "Bob", "last_name": "Bravo", "company_name": null, "phone": "555-010B", "email": "bob@custb.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": "INTERNAL-NOTE-B: margin target 42pct", "custom_fields": {}, "created_at": "2026-10-29T10:02:50.348786+00:00", "last_contact_at": null, "next_followup_at": null}, {"id": 1, "external_id": null, "customer_number": 1, "first_name": "Alice", "last_name": "Alpha", "company_name": null, "phone": "555-010A", "email": "alice@custa.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": "AGENT-EDITED-NOTE-CUST-A", "custom_fields": {}, "created_at": "2026-10-29T10:02:50.318953+00:00", "last_contact_at": null, "next_followup_at": null}]}

### [ADMIN] GET /api/v1/communications
HTTP 200
{"communications": [{"id": 5, "timestamp": "2026-10-29T10:04:47.043542+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-SECOND-MSG-OK", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}, {"id": 4, "timestamp": "2026-10-29T10:03:35.455000+00:00", "channel": "email", "direction": "outbound", "subject": "HUMAN-SUBJ-A", "content": "HUMAN-AUTHORED-COMM-A", "actor_id": 1, "actor_role": "admin", "actor_type": "human", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 3, "timestamp": "2026-10-29T10:03:35.437385+00:00", "channel": "email", "direction": "outbound", "subject": "AGENT-SUBJ-A", "content": "AGENT-AUTHORED-COMM-A", "actor_id": 5, "actor_role": "ai_agent", "actor_type": "agent", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 2, "timestamp": "2026-10-29T10:03:35.418762+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-OWN-MSG-123", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider

### [TECH] GET /api/v1/invoices
HTTP 403
{"error": "Actor lacks permission to read invoices"}

### [TECH] GET /api/v1/customers
HTTP 403
{"error": "Actor lacks permission to list all customers"}

### [TECH] GET /api/v1/communications
HTTP 403
{"error": "Actor lacks permission to read communications"}

### [CUSTA] GET /api/v1/invoices
HTTP 200
{"invoices": [{"id": 1, "invoice_number": "INV-A-001", "customer_id": 1, "project_id": 1, "status": "draft", "amount": 5000.0, "deposit_amount": 0.0, "balance_due": 5000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-A", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.836848+00:00", "updated_at": "2026-10-29T10:02:50.836848+00:00"}]}

### [CUSTA] GET /api/v1/customers
HTTP 200
{"customers": [{"id": 1, "external_id": null, "customer_number": 1, "first_name": "Alice", "last_name": "Alpha", "company_name": null, "phone": "555-010A", "email": "alice@custa.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": null, "custom_fields": {}, "created_at": "2026-10-29T10:02:50.318953+00:00", "last_contact_at": null, "next_followup_at": null}]}

### [CUSTA] GET /api/v1/communications
HTTP 200
{"communications": [{"id": 5, "timestamp": "2026-10-29T10:04:47.043542+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-SECOND-MSG-OK", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}, {"id": 4, "timestamp": "2026-10-29T10:03:35.455000+00:00", "channel": "email", "direction": "outbound", "subject": "HUMAN-SUBJ-A", "content": "HUMAN-AUTHORED-COMM-A", "actor_id": 1, "actor_role": "admin", "actor_type": "human", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 3, "timestamp": "2026-10-29T10:03:35.437385+00:00", "channel": "email", "direction": "outbound", "subject": "AGENT-SUBJ-A", "content": "AGENT-AUTHORED-COMM-A", "actor_id": 5, "actor_role": "ai_agent", "actor_type": "agent", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 2, "timestamp": "2026-10-29T10:03:35.418762+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-OWN-MSG-123", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider

## section: ai_agent reads (role-filtered view for the agent actor)
### [agent] GET /api/v1/invoices
HTTP 200
{"invoices": [{"id": 2, "invoice_number": "INV-B-001", "customer_id": 2, "project_id": 2, "status": "draft", "amount": 7000.0, "deposit_amount": 0.0, "balance_due": 7000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-B", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.876369+00:00", "updated_at": "2026-10-29T10:02:50.876369+00:00"}, {"id": 1, "invoice_number": "INV-A-001", "customer_id": 1, "project_id": 1, "status": "draft", "amount": 5000.0, "deposit_amount": 0.0, "balance_due": 5000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-A", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.836848+00:00", "updated_at": "2026-10-29T10:02:50.836848+00:00"}]}

### [agent] GET /api/v1/communications
HTTP 200
{"communications": [{"id": 5, "timestamp": "2026-10-29T10:04:47.043542+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-SECOND-MSG-OK", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}, {"id": 4, "timestamp": "2026-10-29T10:03:35.455000+00:00", "channel": "email", "direction": "outbound", "subject": "HUMAN-SUBJ-A", "content": "HUMAN-AUTHORED-COMM-A", "actor_id": 1, "actor_role": "admin", "actor_type": "human", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 3, "timestamp": "2026-10-29T10:03:35.437385+00:00", "channel": "email", "direction": "outbound", "subject": "AGENT-SUBJ-A", "content": "AGENT-AUTHORED-COMM-A", "actor_id": 5, "actor_role": "ai_agent", "actor_type": "agent", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 2, "timestamp": "2026-10-29T10:03:35.418762+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-OWN-MSG-123", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider

## done
### PATCH /api/v1/estimator/estimates/3/lines/1 (admin, add customer_description)
HTTP 200
{"line": {"id": 1, "estimate_version_id": 1, "sort_order": 0, "line_type": "material", "section": null, "category": null, "description": "INTERNAL-COST-LINE-A cabinets", "customer_description": "Kitchen cabinets (customer view)", "visible_to_customer": 1, "price_book_item_id": null, "retailer_product_id": null, "price_observation_id": null, "retailer_code_snapshot": null, "product_title_snapshot": null, "package_qty": null, "package_unit": null, "unit_cost_cents": 150000, "quantity": 2.0, "unit": "ea", "waste_pct_bp": 0, "material_markup_bp": 3000, "labor_type": null, "labor_rate_id": null, "labor_qty": null, "labor_unit": null, "labor_cost_rate_cents": null, "labor_bill_rate_cents": null, "equipment_id": null, "equipment_cost_cents": null, "equipment_markup_bp": 0, "subcontractor_id": null, "sub_cost_cents": null, "sub_markup_bp": 0, "taxable": 1, "discount_cents": 0, "price_override_cents": null, "override_reason": null, "packages_needed": 2, "material_cost_cents": 300000, "labor_cost_cents": 0, "cost_total_cents": 300000, "sell_total_cents": 390000, "tax_cents": 0, "line_total_cents": 390000, "internal_note": null, "created_at": "2026-10-29T10:03:57.632470+00:00", "updated_at": "2026-10-29T10:05:21.449930+00:00"}}

### PATCH /api/v1/estimator/estimates/4/lines/2 (admin, add customer_description)
HTTP 200
{"line": {"id": 2, "estimate_version_id": 2, "sort_order": 0, "line_type": "material", "section": null, "category": null, "description": "INTERNAL-COST-LINE-B cabinets", "customer_description": "Kitchen cabinets B (customer view)", "visible_to_customer": 1, "price_book_item_id": null, "retailer_product_id": null, "price_observation_id": null, "retailer_code_snapshot": null, "product_title_snapshot": null, "package_qty": null, "package_unit": null, "unit_cost_cents": 150000, "quantity": 2.0, "unit": "ea", "waste_pct_bp": 0, "material_markup_bp": 3000, "labor_type": null, "labor_rate_id": null, "labor_qty": null, "labor_unit": null, "labor_cost_rate_cents": null, "labor_bill_rate_cents": null, "equipment_id": null, "equipment_cost_cents": null, "equipment_markup_bp": 0, "subcontractor_id": null, "sub_cost_cents": null, "sub_markup_bp": 0, "taxable": 1, "discount_cents": 0, "price_override_cents": null, "override_reason": null, "packages_needed": 2, "material_cost_cents": 300000, "labor_cost_cents": 0, "cost_total_cents": 300000, "sell_total_cents": 390000, "tax_cents": 0, "line_total_cents": 390000, "internal_note": null, "created_at": "2026-10-29T10:03:57.676670+00:00", "updated_at": "2026-10-29T10:05:21.469674+00:00"}}


## RUN 2 (authoritative: untruncated bodies, +portal-estimate fix, +extras). Run 1 above truncated each body at 1500 bytes.
## client pid=21297 ; proxy env (names only, values redacted if any):
CLAUDE_CODE_PROXY_RESOLVES_HOSTS=<set>
## section: NEGATIVE CONTROL + DENIAL for customer A (token=custA) on customer B objects
### [custA] GET /api/v1/projects/1
HTTP 200
{"project": {"id": 1, "customer_id": 1, "title": "Project A kitchen", "property_address": "A St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 0.0, "contract_amount": 0.0, "actual_cost": 0.0, "profit": 0.0, "notes": null, "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.780820+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.780820+00:00", "updated_at": "2026-10-29T10:04:15.134396+00:00"}}

### [custA] GET /api/v1/projects/2
HTTP 403
{"error": "Customer cannot view other customers' projects"}

### [custA] GET /api/v1/invoices/1
HTTP 200
{"invoice": {"id": 1, "invoice_number": "INV-A-001", "customer_id": 1, "project_id": 1, "status": "draft", "amount": 5000.0, "deposit_amount": 0.0, "balance_due": 5000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-A", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.836848+00:00", "updated_at": "2026-10-29T10:02:50.836848+00:00"}}

### [custA] GET /api/v1/invoices/2
HTTP 403
{"error": "Customer cannot access another customer's invoice"}

### [custA] GET /api/v1/contracts/1
HTTP 200
{"contract": {"id": 1, "contract_number": "CON-A-001", "customer_id": 1, "project_id": 1, "estimate_id": null, "title": "Contract A", "template_name": null, "content": "Scope for customer A. INTERNAL-NOTE-CON-A", "status": "draft", "customer_signed_at": null, "customer_signature_data": null, "version": 1, "assigned_user_id": 1, "created_at": "2026-10-29T10:02:50.896805+00:00", "updated_at": "2026-10-29T10:02:50.896805+00:00", "resolved_signed_at": null}}

### [custA] GET /api/v1/contracts/2
HTTP 403
{"error": "Customer cannot access another customer's contract"}

### [custA] GET /api/v1/documents/1
HTTP 200
{"document": {"id": 1, "customer_id": 1, "project_id": 1, "document_type": "contract", "title": "Doc-A-signed-scope", "file_path": "/data/data/com.termux/files/home/.codeyOS-worlds/p012/state/restoricon_documents/contracts/projects/1/1793268215_scope_A.txt", "file_size_bytes": 0, "mime_type": "application/octet-stream", "tags": [], "permissions": [], "expiration_date": null, "created_at": "2026-10-29T10:03:35.351617+00:00", "updated_at": "2026-10-29T10:03:35.351617+00:00"}}

### [custA] GET /api/v1/documents/2
HTTP 403
{"error": "Actor cannot access another customer's document"}

### [custA] GET /api/v1/documents/2/download
HTTP 403
{"error": "Actor cannot access another customer's document"}

### [custA] GET /api/v1/estimates/1
HTTP 200
{"estimate": {"id": 1, "estimate_number": "EST-A-001", "customer_id": 1, "project_id": 1, "line_items": [{"description": "demo", "cost": 1234.0}], "subtotal": 0.0, "materials_cost": 0.0, "labor_cost": 0.0, "subcontractor_cost": 0.0, "markup_percent": 0.0, "tax_amount": 0.0, "discount_amount": 0.0, "total_amount": 0.0, "status": "draft", "expiration_date": null, "version": 1, "notes": null, "assigned_user_id": 1, "created_at": "2026-10-29T10:02:50.948279+00:00", "updated_at": "2026-10-29T10:02:50.948279+00:00"}}

### [custA] GET /api/v1/estimates/2
HTTP 403
{"error": "Customer cannot access another customer's estimate"}

### [custA] GET /api/v1/estimator/estimates/3
HTTP 200
{"estimate": {"id": 3, "estimate_number": "EST-2026-0001", "customer_id": 1, "project_id": 1, "created_by_user_id": 1, "created_by_name": "World Admin", "assigned_to_user_id": 1, "opportunity_id": null, "lead_id": null, "property_id": null, "title": "Estimator A kitchen", "current_version_id": 1, "accepted_version_id": null, "accepted_at": null, "converted_project_id": null, "contract_id": null, "source": "engine", "workflow_status": "DRAFT", "internal_review_required": 0, "expires_at": "2026-11-28T10:03:35.261867+00:00", "customer_notes": null, "terms": null, "sent_at": null, "last_viewed_at": null, "created_at": "2026-10-29T10:03:35.261770+00:00", "updated_at": "2026-10-29T10:03:35.261770+00:00", "cost_total_cents": null, "gross_profit_cents": null, "gross_margin_bp": null, "total_cents": 390000, "lines": []}}

### [custA] GET /api/v1/estimator/estimates/4
HTTP 403
{"error": "Actor lacks permission to view this estimate"}

### [custA] GET /api/v1/customers/1
HTTP 200
{"customer": {"id": 1, "external_id": null, "customer_number": 1, "first_name": "Alice", "last_name": "Alpha", "company_name": null, "phone": "555-010A", "email": "alice@custa.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": null, "custom_fields": {}, "created_at": "2026-10-29T10:02:50.318953+00:00", "last_contact_at": null, "next_followup_at": null}}

### [custA] GET /api/v1/customers/2
HTTP 403
{"error": "Actor lacks permission to access this customer record"}

### [custA] GET /api/v1/operations/projects/2/milestones
HTTP 403
{"error": "Customer cannot view milestones for other customers' projects"}

## section: portal routes, custA token
### [custA] GET /api/v1/portal/profile
HTTP 200
{"profile": {"id": 1, "external_id": null, "customer_number": 1, "first_name": "Alice", "last_name": "Alpha", "company_name": null, "phone": "555-010A", "email": "alice@custa.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": null, "custom_fields": {}, "created_at": "2026-10-29T10:02:50.318953+00:00", "last_contact_at": null, "next_followup_at": null}}

### [custA] GET /api/v1/portal/projects
HTTP 200
{"projects": [{"id": 1, "customer_id": 1, "title": "Project A kitchen", "property_address": "A St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 0.0, "contract_amount": 0.0, "actual_cost": 0.0, "profit": 0.0, "notes": null, "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.780820+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.780820+00:00", "updated_at": "2026-10-29T10:04:15.134396+00:00"}]}

### [custA] GET /api/v1/portal/projects/1
HTTP 200
{"project": {"id": 1, "customer_id": 1, "title": "Project A kitchen", "property_address": "A St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 0.0, "contract_amount": 0.0, "actual_cost": 0.0, "profit": 0.0, "notes": null, "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.780820+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.780820+00:00", "updated_at": "2026-10-29T10:04:15.134396+00:00"}}

### [custA] GET /api/v1/portal/projects/2
HTTP 403
{"error": "Customer cannot view other customers' projects"}

### [custA] GET /api/v1/portal/projects/2/milestones
HTTP 403
{"error": "Customer cannot view milestones for other customers' projects"}

### [custA] GET /api/v1/portal/estimates
HTTP 200
{"estimates": [{"lines": [{"description": "Kitchen cabinets (customer view)", "quantity": "2", "unit": "ea", "price_cents": 390000}], "subtotal_cents": 390000, "discount_cents": 0, "tax_cents": 0, "total_cents": 390000, "terms": "", "customer_notes": ""}]}

### [custA] GET /api/v1/portal/contracts
HTTP 200
{"contracts": [{"id": 1, "contract_number": "CON-A-001", "customer_id": 1, "project_id": 1, "estimate_id": null, "title": "Contract A", "template_name": null, "content": "Scope for customer A. INTERNAL-NOTE-CON-A", "status": "draft", "customer_signed_at": null, "customer_signature_data": null, "version": 1, "assigned_user_id": 1, "created_at": "2026-10-29T10:02:50.896805+00:00", "updated_at": "2026-10-29T10:02:50.896805+00:00"}]}

### [custA] GET /api/v1/portal/invoices
HTTP 200
{"invoices": [{"id": 1, "invoice_number": "INV-A-001", "customer_id": 1, "project_id": 1, "status": "draft", "amount": 5000.0, "deposit_amount": 0.0, "balance_due": 5000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-A", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.836848+00:00", "updated_at": "2026-10-29T10:02:50.836848+00:00"}]}

### [custA] GET /api/v1/portal/documents
HTTP 200
{"documents": [{"id": 1, "customer_id": 1, "project_id": 1, "document_type": "contract", "title": "Doc-A-signed-scope", "file_path": "/data/data/com.termux/files/home/.codeyOS-worlds/p012/state/restoricon_documents/contracts/projects/1/1793268215_scope_A.txt", "file_size_bytes": 0, "mime_type": "application/octet-stream", "tags": [], "permissions": [], "expiration_date": null, "created_at": "2026-10-29T10:03:35.351617+00:00", "updated_at": "2026-10-29T10:03:35.351617+00:00"}]}

### [custA] GET /api/v1/portal/messages
HTTP 200
{"messages": [{"id": 5, "timestamp": "2026-10-29T10:04:47.043542+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-SECOND-MSG-OK", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}, {"id": 2, "timestamp": "2026-10-29T10:03:35.418762+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-OWN-MSG-123", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}]}

## section: portal routes, custB token (positive control for B's own data)
### [custB] GET /api/v1/portal/profile
HTTP 200
{"profile": {"id": 2, "external_id": null, "customer_number": 2, "first_name": "Bob", "last_name": "Bravo", "company_name": null, "phone": "555-010B", "email": "bob@custb.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": null, "custom_fields": {}, "created_at": "2026-10-29T10:02:50.348786+00:00", "last_contact_at": null, "next_followup_at": null}}

### [custB] GET /api/v1/portal/projects
HTTP 200
{"projects": [{"id": 2, "customer_id": 2, "title": "Project B kitchen", "property_address": "B St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 0.0, "contract_amount": 0.0, "actual_cost": 0.0, "profit": 0.0, "notes": null, "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.803777+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.803777+00:00", "updated_at": "2026-10-29T10:02:50.803777+00:00"}]}

### [custB] GET /api/v1/portal/projects/2
HTTP 200
{"project": {"id": 2, "customer_id": 2, "title": "Project B kitchen", "property_address": "B St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 0.0, "contract_amount": 0.0, "actual_cost": 0.0, "profit": 0.0, "notes": null, "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.803777+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.803777+00:00", "updated_at": "2026-10-29T10:02:50.803777+00:00"}}

### [custB] GET /api/v1/portal/projects/2/milestones
HTTP 200
{"milestones": [{"id": 1, "project_id": 2, "name": "MILESTONE-B-ONLY", "stage": "intake", "target_date": null, "completion_date": null, "status": "pending", "dependencies": [], "notes": "B-INTERNAL-MS-NOTE", "created_at": "2026-10-29T10:03:57.702046+00:00", "updated_at": "2026-10-29T10:03:57.702046+00:00"}]}

### [custB] GET /api/v1/portal/messages
HTTP 200
{"messages": [{"id": 1, "timestamp": "2026-10-29T10:03:35.401230+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "B-PRIVATE-MSG-XYZ", "actor_id": 3, "actor_role": "customer", "actor_type": "human", "customer_id": 2, "project_id": 2, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}]}

## section: direct list endpoints as custA
### [custA] GET /api/v1/projects
HTTP 200
{"projects": [{"id": 1, "customer_id": 1, "title": "Project A kitchen", "property_address": "A St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 0.0, "contract_amount": 0.0, "actual_cost": 0.0, "profit": 0.0, "notes": null, "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.780820+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.780820+00:00", "updated_at": "2026-10-29T10:04:15.134396+00:00", "customer_name": "Alice Alpha"}]}

### [custA] GET /api/v1/customers
HTTP 200
{"customers": [{"id": 1, "external_id": null, "customer_number": 1, "first_name": "Alice", "last_name": "Alpha", "company_name": null, "phone": "555-010A", "email": "alice@custa.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": null, "custom_fields": {}, "created_at": "2026-10-29T10:02:50.318953+00:00", "last_contact_at": null, "next_followup_at": null}]}

### [custA] GET /api/v1/invoices
HTTP 200
{"invoices": [{"id": 1, "invoice_number": "INV-A-001", "customer_id": 1, "project_id": 1, "status": "draft", "amount": 5000.0, "deposit_amount": 0.0, "balance_due": 5000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-A", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.836848+00:00", "updated_at": "2026-10-29T10:02:50.836848+00:00"}]}

### [custA] GET /api/v1/contracts
HTTP 200
{"contracts": [{"id": 1, "contract_number": "CON-A-001", "customer_id": 1, "project_id": 1, "estimate_id": null, "title": "Contract A", "template_name": null, "content": "Scope for customer A. INTERNAL-NOTE-CON-A", "status": "draft", "customer_signed_at": null, "customer_signature_data": null, "version": 1, "assigned_user_id": 1, "created_at": "2026-10-29T10:02:50.896805+00:00", "updated_at": "2026-10-29T10:02:50.896805+00:00", "resolved_signed_at": null}]}

### [custA] GET /api/v1/documents
HTTP 200
{"documents": [{"id": 1, "customer_id": 1, "project_id": 1, "document_type": "contract", "title": "Doc-A-signed-scope", "file_path": "/data/data/com.termux/files/home/.codeyOS-worlds/p012/state/restoricon_documents/contracts/projects/1/1793268215_scope_A.txt", "file_size_bytes": 0, "mime_type": "application/octet-stream", "tags": [], "permissions": [], "expiration_date": null, "created_at": "2026-10-29T10:03:35.351617+00:00", "updated_at": "2026-10-29T10:03:35.351617+00:00", "customer_name": "Alice Alpha", "project_name": "Project A kitchen"}]}

### [custA] GET /api/v1/estimates
HTTP 200
{"estimates": [{"id": 3, "estimate_number": "EST-2026-0001", "customer_id": 1, "project_id": 1, "line_items": [], "subtotal": 0.0, "materials_cost": 0.0, "labor_cost": 0.0, "subcontractor_cost": 0.0, "markup_percent": 0.0, "tax_amount": 0.0, "discount_amount": 0.0, "total_amount": 0.0, "status": "draft", "expiration_date": null, "version": 1, "notes": null, "assigned_user_id": null, "created_at": "2026-10-29T10:03:35.261770+00:00", "updated_at": "2026-10-29T10:03:35.261770+00:00"}, {"id": 1, "estimate_number": "EST-A-001", "customer_id": 1, "project_id": 1, "line_items": [{"description": "demo", "cost": 1234.0}], "subtotal": 0.0, "materials_cost": 0.0, "labor_cost": 0.0, "subcontractor_cost": 0.0, "markup_percent": 0.0, "tax_amount": 0.0, "discount_amount": 0.0, "total_amount": 0.0, "status": "draft", "expiration_date": null, "version": 1, "notes": null, "assigned_user_id": 1, "created_at": "2026-10-29T10:02:50.948279+00:00", "updated_at": "2026-10-29T10:02:50.948279+00:00"}]}

### [custA] GET /api/v1/estimator/estimates
HTTP 200
{"estimates": [{"id": 3, "estimate_number": "EST-2026-0001", "customer_id": 1, "project_id": 1, "created_by_user_id": 1, "created_by_name": "World Admin", "assigned_to_user_id": 1, "opportunity_id": null, "lead_id": null, "property_id": null, "title": "Estimator A kitchen", "current_version_id": 1, "accepted_version_id": null, "accepted_at": null, "converted_project_id": null, "contract_id": null, "source": "engine", "workflow_status": "DRAFT", "internal_review_required": 0, "expires_at": "2026-11-28T10:03:35.261867+00:00", "customer_notes": null, "terms": null, "sent_at": null, "last_viewed_at": null, "created_at": "2026-10-29T10:03:35.261770+00:00", "updated_at": "2026-10-29T10:03:35.261770+00:00", "cost_total_cents": null, "gross_profit_cents": null, "gross_margin_bp": null, "total_cents": 390000, "lines": []}, {"id": 1, "estimate_number": "EST-A-001", "customer_id": 1, "project_id": 1, "created_by_user_id": null, "created_by_name": null, "assigned_to_user_id": null, "opportunity_id": null, "lead_id": null, "property_id": null, "title": null, "current_version_id": null, "accepted_version_id": null, "accepted_at": null, "converted_project_id": null, "contract_id": null, "source": "engine", "workflow_status": "DRAFT", "internal_review_required": 0, "expires_at": null, "customer_notes": null, "terms": null, "sent_at": null, "last_viewed_at": null, "created_at": "2026-10-29T10:02:50.948279+00:00", "updated_at": "2026-10-29T10:02:50.948279+00:00", "cost_total_cents": null, "gross_profit_cents": null, "gross_margin_bp": null, "total_cents": null, "lines": []}]}

### [custA] GET /api/v1/communications
HTTP 200
{"communications": [{"id": 5, "timestamp": "2026-10-29T10:04:47.043542+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-SECOND-MSG-OK", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}, {"id": 4, "timestamp": "2026-10-29T10:03:35.455000+00:00", "channel": "email", "direction": "outbound", "subject": "HUMAN-SUBJ-A", "content": "HUMAN-AUTHORED-COMM-A", "actor_id": 1, "actor_role": "admin", "actor_type": "human", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 3, "timestamp": "2026-10-29T10:03:35.437385+00:00", "channel": "email", "direction": "outbound", "subject": "AGENT-SUBJ-A", "content": "AGENT-AUTHORED-COMM-A", "actor_id": 5, "actor_role": "ai_agent", "actor_type": "agent", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 2, "timestamp": "2026-10-29T10:03:35.418762+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-OWN-MSG-123", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}]}

### [custA] GET /api/v1/users
HTTP 403
{"error": "Actor lacks permission to list users"}

## section: write denials as custA (and the positive write control: own portal message)
### [custA-POSITIVE] POST /api/v1/portal/messages
HTTP 201
{"message": {"id": 6, "timestamp": "2026-10-29T10:05:36.549597+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-SECOND-MSG-OK", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}}

### [custA-DENY] POST /api/v1/portal/contracts/2/sign
HTTP 403
{"error": "Customer cannot sign another customer's contract"}

### [custA-DENY] POST /api/v1/estimator/estimates/4/lines
HTTP 403
{"error": "Actor lacks permission to write estimates"}

### [custA-DENY] POST /api/v1/projects/2/update
HTTP 403
{"error": "Actor lacks permission to update projects"}

## section: auth. no token and garbage token must be 401
### [no-token] GET /api/v1/portal/projects
HTTP 401
{"error": "Unauthorized or expired token"}

### [no-token] GET /api/v1/projects/1
HTTP 401
{"error": "Unauthorized or expired token"}

### [garbage-bearer] GET /api/v1/portal/projects
HTTP 401
{"error": "Unauthorized or expired token"}

### [garbage-bearer] GET /api/v1/projects/1
HTTP 401
{"error": "Unauthorized or expired token"}

### [garbage ?token=] GET /api/v1/portal/projects?token=garbage-token-not-a-real-token
HTTP 401
{"error": "Unauthorized or expired token"}

## section: P0-2 role-filtered reads of the same list endpoints (admin / technician / custA)
### [ADMIN] GET /api/v1/invoices
HTTP 200
{"invoices": [{"id": 2, "invoice_number": "INV-B-001", "customer_id": 2, "project_id": 2, "status": "draft", "amount": 7000.0, "deposit_amount": 0.0, "balance_due": 7000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-B", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.876369+00:00", "updated_at": "2026-10-29T10:02:50.876369+00:00"}, {"id": 1, "invoice_number": "INV-A-001", "customer_id": 1, "project_id": 1, "status": "draft", "amount": 5000.0, "deposit_amount": 0.0, "balance_due": 5000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-A", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.836848+00:00", "updated_at": "2026-10-29T10:02:50.836848+00:00"}]}

### [ADMIN] GET /api/v1/customers
HTTP 200
{"customers": [{"id": 2, "external_id": null, "customer_number": 2, "first_name": "Bob", "last_name": "Bravo", "company_name": null, "phone": "555-010B", "email": "bob@custb.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": "INTERNAL-NOTE-B: margin target 42pct", "custom_fields": {}, "created_at": "2026-10-29T10:02:50.348786+00:00", "last_contact_at": null, "next_followup_at": null}, {"id": 1, "external_id": null, "customer_number": 1, "first_name": "Alice", "last_name": "Alpha", "company_name": null, "phone": "555-010A", "email": "alice@custa.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": "AGENT-EDITED-NOTE-CUST-A", "custom_fields": {}, "created_at": "2026-10-29T10:02:50.318953+00:00", "last_contact_at": null, "next_followup_at": null}]}

### [ADMIN] GET /api/v1/communications
HTTP 200
{"communications": [{"id": 6, "timestamp": "2026-10-29T10:05:36.549597+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-SECOND-MSG-OK", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}, {"id": 5, "timestamp": "2026-10-29T10:04:47.043542+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-SECOND-MSG-OK", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}, {"id": 4, "timestamp": "2026-10-29T10:03:35.455000+00:00", "channel": "email", "direction": "outbound", "subject": "HUMAN-SUBJ-A", "content": "HUMAN-AUTHORED-COMM-A", "actor_id": 1, "actor_role": "admin", "actor_type": "human", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 3, "timestamp": "2026-10-29T10:03:35.437385+00:00", "channel": "email", "direction": "outbound", "subject": "AGENT-SUBJ-A", "content": "AGENT-AUTHORED-COMM-A", "actor_id": 5, "actor_role": "ai_agent", "actor_type": "agent", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 2, "timestamp": "2026-10-29T10:03:35.418762+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-OWN-MSG-123", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}, {"id": 1, "timestamp": "2026-10-29T10:03:35.401230+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "B-PRIVATE-MSG-XYZ", "actor_id": 3, "actor_role": "customer", "actor_type": "human", "customer_id": 2, "project_id": 2, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}]}

### [TECH] GET /api/v1/invoices
HTTP 403
{"error": "Actor lacks permission to read invoices"}

### [TECH] GET /api/v1/customers
HTTP 403
{"error": "Actor lacks permission to list all customers"}

### [TECH] GET /api/v1/communications
HTTP 403
{"error": "Actor lacks permission to read communications"}

### [CUSTA] GET /api/v1/invoices
HTTP 200
{"invoices": [{"id": 1, "invoice_number": "INV-A-001", "customer_id": 1, "project_id": 1, "status": "draft", "amount": 5000.0, "deposit_amount": 0.0, "balance_due": 5000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-A", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.836848+00:00", "updated_at": "2026-10-29T10:02:50.836848+00:00"}]}

### [CUSTA] GET /api/v1/customers
HTTP 200
{"customers": [{"id": 1, "external_id": null, "customer_number": 1, "first_name": "Alice", "last_name": "Alpha", "company_name": null, "phone": "555-010A", "email": "alice@custa.test", "mailing_address": null, "service_address": null, "customer_type": "residential", "customer_source": null, "assigned_user_id": null, "status": "lead", "territory_id": null, "tags": [], "notes": null, "custom_fields": {}, "created_at": "2026-10-29T10:02:50.318953+00:00", "last_contact_at": null, "next_followup_at": null}]}

### [CUSTA] GET /api/v1/communications
HTTP 200
{"communications": [{"id": 6, "timestamp": "2026-10-29T10:05:36.549597+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-SECOND-MSG-OK", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}, {"id": 5, "timestamp": "2026-10-29T10:04:47.043542+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-SECOND-MSG-OK", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}, {"id": 4, "timestamp": "2026-10-29T10:03:35.455000+00:00", "channel": "email", "direction": "outbound", "subject": "HUMAN-SUBJ-A", "content": "HUMAN-AUTHORED-COMM-A", "actor_id": 1, "actor_role": "admin", "actor_type": "human", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 3, "timestamp": "2026-10-29T10:03:35.437385+00:00", "channel": "email", "direction": "outbound", "subject": "AGENT-SUBJ-A", "content": "AGENT-AUTHORED-COMM-A", "actor_id": 5, "actor_role": "ai_agent", "actor_type": "agent", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 2, "timestamp": "2026-10-29T10:03:35.418762+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-OWN-MSG-123", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}]}

## section: ai_agent reads (role-filtered view for the agent actor)
### [agent] GET /api/v1/invoices
HTTP 200
{"invoices": [{"id": 2, "invoice_number": "INV-B-001", "customer_id": 2, "project_id": 2, "status": "draft", "amount": 7000.0, "deposit_amount": 0.0, "balance_due": 7000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-B", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.876369+00:00", "updated_at": "2026-10-29T10:02:50.876369+00:00"}, {"id": 1, "invoice_number": "INV-A-001", "customer_id": 1, "project_id": 1, "status": "draft", "amount": 5000.0, "deposit_amount": 0.0, "balance_due": 5000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-A", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.836848+00:00", "updated_at": "2026-10-29T10:02:50.836848+00:00"}]}

### [agent] GET /api/v1/communications
HTTP 200
{"communications": [{"id": 6, "timestamp": "2026-10-29T10:05:36.549597+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-SECOND-MSG-OK", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}, {"id": 5, "timestamp": "2026-10-29T10:04:47.043542+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-SECOND-MSG-OK", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}, {"id": 4, "timestamp": "2026-10-29T10:03:35.455000+00:00", "channel": "email", "direction": "outbound", "subject": "HUMAN-SUBJ-A", "content": "HUMAN-AUTHORED-COMM-A", "actor_id": 1, "actor_role": "admin", "actor_type": "human", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 3, "timestamp": "2026-10-29T10:03:35.437385+00:00", "channel": "email", "direction": "outbound", "subject": "AGENT-SUBJ-A", "content": "AGENT-AUTHORED-COMM-A", "actor_id": 5, "actor_role": "ai_agent", "actor_type": "agent", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 2, "timestamp": "2026-10-29T10:03:35.418762+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-OWN-MSG-123", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}, {"id": 1, "timestamp": "2026-10-29T10:03:35.401230+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "B-PRIVATE-MSG-XYZ", "actor_id": 3, "actor_role": "customer", "actor_type": "human", "customer_id": 2, "project_id": 2, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}]}

## section v2 extras
### [custA-POSITIVE] GET /api/v1/documents/1/download
HTTP 200
SCOPE-DOC-CONTENT-A

### [custA-DENY] GET /api/v1/documents/2/download
HTTP 403
{"error": "Actor cannot access another customer's document"}

### [ADMIN-CONTROL] GET /api/v1/projects/1
HTTP 200
{"project": {"id": 1, "customer_id": 1, "title": "Project A kitchen", "property_address": "A St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 11111.0, "contract_amount": 0.0, "actual_cost": 9999.0, "profit": 1234.5, "notes": "HUMAN-EDITED-NOTE-A", "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.780820+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.780820+00:00", "updated_at": "2026-10-29T10:04:15.134396+00:00"}}

### [ADMIN-CONTROL] GET /api/v1/estimator/estimates/4
HTTP 200
{"estimate": {"id": 4, "estimate_number": "EST-2026-0002", "customer_id": 2, "project_id": 2, "created_by_user_id": 1, "created_by_name": "World Admin", "assigned_to_user_id": 1, "opportunity_id": null, "lead_id": null, "property_id": null, "title": "Estimator B kitchen", "current_version_id": 2, "accepted_version_id": null, "accepted_at": null, "converted_project_id": null, "contract_id": null, "source": "engine", "workflow_status": "DRAFT", "internal_review_required": 0, "expires_at": "2026-11-28T10:03:35.297698+00:00", "customer_notes": null, "terms": null, "sent_at": null, "last_viewed_at": null, "created_at": "2026-10-29T10:03:35.297592+00:00", "updated_at": "2026-10-29T10:03:35.297592+00:00", "cost_total_cents": 300000, "gross_profit_cents": 90000, "gross_margin_bp": 2308, "total_cents": 390000, "lines": []}}

### [custA-ENUM] GET /api/v1/projects/999
HTTP 404
{"error": "Project not found"}

### [custA-ENUM] GET /api/v1/projects/2
HTTP 403
{"error": "Customer cannot view other customers' projects"}

### [custA-ENUM] GET /api/v1/invoices/999
HTTP 404
{"error": "Invoice not found"}

### [custA-ENUM] GET /api/v1/invoices/2
HTTP 403
{"error": "Customer cannot access another customer's invoice"}

### [custA-FILTER-BYPASS] GET /api/v1/communications?customer_id=2
HTTP 200
{"communications": [{"id": 6, "timestamp": "2026-10-29T10:05:36.549597+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-SECOND-MSG-OK", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}, {"id": 5, "timestamp": "2026-10-29T10:04:47.043542+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-SECOND-MSG-OK", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}, {"id": 4, "timestamp": "2026-10-29T10:03:35.455000+00:00", "channel": "email", "direction": "outbound", "subject": "HUMAN-SUBJ-A", "content": "HUMAN-AUTHORED-COMM-A", "actor_id": 1, "actor_role": "admin", "actor_type": "human", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 3, "timestamp": "2026-10-29T10:03:35.437385+00:00", "channel": "email", "direction": "outbound", "subject": "AGENT-SUBJ-A", "content": "AGENT-AUTHORED-COMM-A", "actor_id": 5, "actor_role": "ai_agent", "actor_type": "agent", "customer_id": 1, "project_id": null, "opportunity_id": null, "lead_id": null, "metadata": {}, "provider_message_id": null}, {"id": 2, "timestamp": "2026-10-29T10:03:35.418762+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "A-OWN-MSG-123", "actor_id": 2, "actor_role": "customer", "actor_type": "human", "customer_id": 1, "project_id": 1, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}]}

### [custA-FILTER-BYPASS] GET /api/v1/documents?customer_id=2
HTTP 200
{"documents": [{"id": 1, "customer_id": 1, "project_id": 1, "document_type": "contract", "title": "Doc-A-signed-scope", "file_path": "/data/data/com.termux/files/home/.codeyOS-worlds/p012/state/restoricon_documents/contracts/projects/1/1793268215_scope_A.txt", "file_size_bytes": 0, "mime_type": "application/octet-stream", "tags": [], "permissions": [], "expiration_date": null, "created_at": "2026-10-29T10:03:35.351617+00:00", "updated_at": "2026-10-29T10:03:35.351617+00:00", "customer_name": "Alice Alpha", "project_name": "Project A kitchen"}]}

### [custA-FILTER-BYPASS] GET /api/v1/invoices?customer_id=2
HTTP 200
{"invoices": [{"id": 1, "invoice_number": "INV-A-001", "customer_id": 1, "project_id": 1, "status": "draft", "amount": 5000.0, "deposit_amount": 0.0, "balance_due": 5000.0, "due_date": null, "payments": [], "notes": "INTERNAL-NOTE-INV-A", "assigned_user_id": null, "invoice_type": "other", "line_items": [], "created_at": "2026-10-29T10:02:50.836848+00:00", "updated_at": "2026-10-29T10:02:50.836848+00:00"}]}

### [custA-FILTER-BYPASS] GET /api/v1/projects?customer_id=2
HTTP 200
{"projects": [{"id": 1, "customer_id": 1, "title": "Project A kitchen", "property_address": "A St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 0.0, "contract_amount": 0.0, "actual_cost": 0.0, "profit": 0.0, "notes": null, "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.780820+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.780820+00:00", "updated_at": "2026-10-29T10:04:15.134396+00:00", "customer_name": "Alice Alpha"}]}

### [custA-FILTER-BYPASS] GET /api/v1/portal/projects?customer_id=2
HTTP 200
{"projects": [{"id": 1, "customer_id": 1, "title": "Project A kitchen", "property_address": "A St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 0.0, "contract_amount": 0.0, "actual_cost": 0.0, "profit": 0.0, "notes": null, "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.780820+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.780820+00:00", "updated_at": "2026-10-29T10:04:15.134396+00:00"}]}

### [custA-FILTER-BYPASS] GET /api/v1/portal/invoices?project_id=2
HTTP 200
{"invoices": []}

### [custA-FILTER-BYPASS] GET /api/v1/portal/documents?project_id=2
HTTP 200
{"documents": []}

### [custA-PORTAL-EST] GET /api/v1/portal/estimates
HTTP 200
{"estimates": [{"lines": [{"description": "Kitchen cabinets (customer view)", "quantity": "2", "unit": "ea", "price_cents": 390000}], "subtotal_cents": 390000, "discount_cents": 0, "tax_cents": 0, "total_cents": 390000, "terms": "", "customer_notes": ""}]}

### [custB-PORTAL-EST] GET /api/v1/portal/estimates
HTTP 200
{"estimates": [{"lines": [{"description": "Kitchen cabinets B (customer view)", "quantity": "2", "unit": "ea", "price_cents": 390000}], "subtotal_cents": 390000, "discount_cents": 0, "tax_cents": 0, "total_cents": 390000, "terms": "", "customer_notes": ""}]}

### [custB-DENY] GET /api/v1/estimator/estimates/3
HTTP 403
{"error": "Actor lacks permission to view this estimate"}

### [custB-DENY] GET /api/v1/invoices/1
HTTP 403
{"error": "Customer cannot access another customer's invoice"}

### [custB-DENY] GET /api/v1/documents/1/download
HTTP 403
{"error": "Actor cannot access another customer's document"}

### [custB-DENY] GET /api/v1/contracts/1
HTTP 403
{"error": "Customer cannot access another customer's contract"}

### [custB-PORTAL-MSG] GET /api/v1/portal/messages
HTTP 200
{"messages": [{"id": 1, "timestamp": "2026-10-29T10:03:35.401230+00:00", "channel": "web_chat", "direction": "inbound", "subject": "Portal Message", "content": "B-PRIVATE-MSG-XYZ", "actor_id": 3, "actor_role": "customer", "actor_type": "human", "customer_id": 2, "project_id": 2, "opportunity_id": null, "lead_id": null, "metadata": {"source": "customer_portal", "ip": "127.0.0.1"}, "provider_message_id": null}]}

## done

## EXTRA3 (role-filter and admin-cost controls)
## extra3: role-filter controls (separate curl process, pid=21649)
### [ADMIN-PROJECTS] GET /api/v1/projects
{"projects": [{"id": 2, "customer_id": 2, "title": "Project B kitchen", "property_address": "B St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 22222.0, "contract_amount": 0.0, "actual_cost": 8888.0, "profit": 2345.5, "notes": "INTERNAL-NOTE-PROJ-B", "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.803777+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.803777+00:00", "updated_at": "2026-10-29T10:02:50.803777+00:00", "customer_name": "Bob Bravo"}, {"id": 1, "customer_id": 1, "title": "Project A kitchen", "property_address": "A St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 11111.0, "contract_amount": 0.0, "actual_cost": 9999.0, "profit": 1234.5, "notes": "HUMAN-EDITED-NOTE-A", "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.780820+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.780820+00:00", "updated_at": "2026-10-29T10:04:15.134396+00:00", "customer_name": "Alice Alpha"}]}
HTTP 200

### [TECH-PROJECTS] GET /api/v1/projects
{"projects": []}
HTTP 200

### [TECH-DOCUMENTS] GET /api/v1/documents
{"documents": [{"id": 2, "customer_id": 2, "project_id": 2, "document_type": "contract", "title": "Doc-B-signed-scope", "file_path": "/data/data/com.termux/files/home/.codeyOS-worlds/p012/state/restoricon_documents/contracts/projects/2/1793268215_scope_B.txt", "file_size_bytes": 0, "mime_type": "application/octet-stream", "tags": [], "permissions": [], "expiration_date": null, "created_at": "2026-10-29T10:03:35.373940+00:00", "updated_at": "2026-10-29T10:03:35.373940+00:00", "customer_name": "Bob Bravo", "project_name": "Project B kitchen"}, {"id": 1, "customer_id": 1, "project_id": 1, "document_type": "contract", "title": "Doc-A-signed-scope", "file_path": "/data/data/com.termux/files/home/.codeyOS-worlds/p012/state/restoricon_documents/contracts/projects/1/1793268215_scope_A.txt", "file_size_bytes": 0, "mime_type": "application/octet-stream", "tags": [], "permissions": [], "expiration_date": null, "created_at": "2026-10-29T10:03:35.351617+00:00", "updated_at": "2026-10-29T10:03:35.351617+00:00", "customer_name": "Alice Alpha", "project_name": "Project A kitchen"}]}
HTTP 200

### [AGENT-PROJECTS] GET /api/v1/projects
{"projects": [{"id": 2, "customer_id": 2, "title": "Project B kitchen", "property_address": "B St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 22222.0, "contract_amount": 0.0, "actual_cost": 8888.0, "profit": 2345.5, "notes": "INTERNAL-NOTE-PROJ-B", "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.803777+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.803777+00:00", "updated_at": "2026-10-29T10:02:50.803777+00:00", "customer_name": "Bob Bravo"}, {"id": 1, "customer_id": 1, "title": "Project A kitchen", "property_address": "A St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 11111.0, "contract_amount": 0.0, "actual_cost": 9999.0, "profit": 1234.5, "notes": "HUMAN-EDITED-NOTE-A", "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.780820+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.780820+00:00", "updated_at": "2026-10-29T10:04:15.134396+00:00", "customer_name": "Alice Alpha"}]}
HTTP 200

### [CUSTB-PROJECTS] GET /api/v1/projects
{"projects": [{"id": 2, "customer_id": 2, "title": "Project B kitchen", "property_address": "B St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 0.0, "contract_amount": 0.0, "actual_cost": 0.0, "profit": 0.0, "notes": null, "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.803777+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.803777+00:00", "updated_at": "2026-10-29T10:02:50.803777+00:00", "customer_name": "Bob Bravo"}]}
HTTP 200

### [ADMIN-CONTROL] GET /api/v1/projects/1 (estimated_cost / actual_cost / notes)
{"project": {"id": 1, "customer_id": 1, "title": "Project A kitchen", "property_address": "A St 1", "project_type": "remodel", "status": "planning", "stage": "intake", "start_date": null, "expected_completion": null, "actual_completion": null, "project_manager_id": null, "assigned_employees": [], "subcontractors": [], "scope_of_work": null, "estimated_cost": 11111.0, "contract_amount": 0.0, "actual_cost": 9999.0, "profit": 1234.5, "notes": "HUMAN-EDITED-NOTE-A", "warranty_info": null, "stage_entered_at": "2026-10-29T10:02:50.780820+00:00", "insurance_claim_number": null, "insurance_carrier": null, "adjuster_name": null, "adjuster_phone": null, "adjuster_email": null, "deductible": null, "coverage_amount": null, "supplement_amount": null, "property_id": null, "created_at": "2026-10-29T10:02:50.780820+00:00", "updated_at": "2026-10-29T10:04:15.134396+00:00"}}
HTTP 200

## STEP P0-2 read-only SELECTs (world DB, mode=ro URI)
$ sqlite3(ro) SELECT (SELECT COUNT(*) FROM audit_log) AS audit_rows, (SELECT COUNT(*) FROM communication_history) AS comm_rows
audit_rows | comm_rows
31 | 6

$ sqlite3(ro) SELECT a.id, a.timestamp, u.username, a.actor_id, a.actor_role, a.actor_type, a.action, a.entity_type, a.entity_id, a.change_summary FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id ORDER BY a.id
id | timestamp | username | actor_id | actor_role | actor_type | action | entity_type | entity_id | change_summary
1 | 2026-10-29T10:02:44.425348+00:00 | admin_p012 | 1 | admin | human | auth_login | user | 1 | User admin_p012 authenticated
2 | 2026-10-29T10:02:50.286503+00:00 | admin_p012 | 1 | admin | human | auth_login | user | 1 | User admin_p012 authenticated
3 | 2026-10-29T10:02:50.326381+00:00 | admin_p012 | 1 | admin | human | create | customer | 1 | Created customer Alice Alpha
4 | 2026-10-29T10:02:50.350663+00:00 | admin_p012 | 1 | admin | human | create | customer | 2 | Created customer Bob Bravo
5 | 2026-10-29T10:02:50.460520+00:00 | admin_p012 | 1 | admin | human | user_created | user | 2 | User custa (customer) created
6 | 2026-10-29T10:02:50.550650+00:00 | admin_p012 | 1 | admin | human | user_created | user | 3 | User custb (customer) created
7 | 2026-10-29T10:02:50.666498+00:00 | admin_p012 | 1 | admin | human | user_created | user | 4 | User tech_p012 (technician) created
8 | 2026-10-29T10:02:50.758900+00:00 | admin_p012 | 1 | admin | human | user_created | user | 5 | User agent_p012 (ai_agent) created
9 | 2026-10-29T10:02:50.783030+00:00 | admin_p012 | 1 | admin | human | create | project | 1 | Created project 'Project A kitchen' for customer ID 1
10 | 2026-10-29T10:02:50.808158+00:00 | admin_p012 | 1 | admin | human | create | project | 2 | Created project 'Project B kitchen' for customer ID 2
11 | 2026-10-29T10:02:50.847347+00:00 | admin_p012 | 1 | admin | human | create | invoice | 1 | Created invoice #INV-A-001 for $5000.00
12 | 2026-10-29T10:02:50.877352+00:00 | admin_p012 | 1 | admin | human | create | invoice | 2 | Created invoice #INV-B-001 for $7000.00
13 | 2026-10-29T10:02:50.903012+00:00 | admin_p012 | 1 | admin | human | create | contract | 1 | Created contract #CON-A-001 'Contract A'
14 | 2026-10-29T10:02:50.922852+00:00 | admin_p012 | 1 | admin | human | create | contract | 2 | Created contract #CON-B-001 'Contract B'
15 | 2026-10-29T10:02:50.951859+00:00 | admin_p012 | 1 | admin | human | create | estimate | 1 | Created estimate #EST-A-001 ($0.00)
16 | 2026-10-29T10:02:50.979149+00:00 | admin_p012 | 1 | admin | human | create | estimate | 2 | Created estimate #EST-B-001 ($0.00)
17 | 2026-10-29T10:03:35.102501+00:00 | custa | 2 | customer | human | auth_login | user | 2 | User custa authenticated
18 | 2026-10-29T10:03:35.154638+00:00 | custb | 3 | customer | human | auth_login | user | 3 | User custb authenticated
19 | 2026-10-29T10:03:35.203898+00:00 | tech_p012 | 4 | technician | human | auth_login | user | 4 | User tech_p012 authenticated
20 | 2026-10-29T10:03:35.248263+00:00 | agent_p012 | 5 | ai_agent | agent | auth_login | user | 5 | User agent_p012 authenticated
21 | 2026-10-29T10:03:35.265191+00:00 | admin_p012 | 1 | admin | human | create | estimate | 3 | Created estimate EST-2026-0001
22 | 2026-10-29T10:03:35.300494+00:00 | admin_p012 | 1 | admin | human | create | estimate | 4 | Created estimate EST-2026-0002
23 | 2026-10-29T10:03:35.353377+00:00 | admin_p012 | 1 | admin | human | create | document | 1 | Added document 'Doc-A-signed-scope' (contract)
24 | 2026-10-29T10:03:35.374781+00:00 | admin_p012 | 1 | admin | human | create | document | 2 | Added document 'Doc-B-signed-scope' (contract)
25 | 2026-10-29T10:03:57.649749+00:00 | admin_p012 | 1 | admin | human | add | estimate_line | 1 | Added line 1 to estimate 3
26 | 2026-10-29T10:03:57.681602+00:00 | admin_p012 | 1 | admin | human | add | estimate_line | 2 | Added line 2 to estimate 4
27 | 2026-10-29T10:03:57.703659+00:00 | admin_p012 | 1 | admin | human | create | milestone | 1 | Created milestone 'MILESTONE-B-ONLY' for project #2
28 | 2026-10-29T10:04:15.138467+00:00 | admin_p012 | 1 | admin | human | update | project | 1 | Project 1 updated (notes)
29 | 2026-10-29T10:04:21.758773+00:00 | agent_p012 | 5 | ai_agent | agent | update | customer | 1 | Customer 1 updated (notes)
30 | 2026-10-29T10:05:21.453283+00:00 | admin_p012 | 1 | admin | human | update | estimate_line | 1 | Updated line 1
31 | 2026-10-29T10:05:21.472273+00:00 | admin_p012 | 1 | admin | human | update | estimate_line | 2 | Updated line 2

$ sqlite3(ro) SELECT DISTINCT actor_type, actor_role FROM audit_log
actor_type | actor_role
human | admin
human | customer
human | technician
agent | ai_agent

$ sqlite3(ro) SELECT c.id, c.timestamp, u.username, c.actor_id, c.actor_role, c.actor_type, c.channel, c.direction, c.customer_id, c.content FROM communication_history c LEFT JOIN users u ON u.id = c.actor_id ORDER BY c.id
id | timestamp | username | actor_id | actor_role | actor_type | channel | direction | customer_id | content
1 | 2026-10-29T10:03:35.401230+00:00 | custb | 3 | customer | human | web_chat | inbound | 2 | B-PRIVATE-MSG-XYZ
2 | 2026-10-29T10:03:35.418762+00:00 | custa | 2 | customer | human | web_chat | inbound | 1 | A-OWN-MSG-123
3 | 2026-10-29T10:03:35.437385+00:00 | agent_p012 | 5 | ai_agent | agent | email | outbound | 1 | AGENT-AUTHORED-COMM-A
4 | 2026-10-29T10:03:35.455000+00:00 | admin_p012 | 1 | admin | human | email | outbound | 1 | HUMAN-AUTHORED-COMM-A
5 | 2026-10-29T10:04:47.043542+00:00 | custa | 2 | customer | human | web_chat | inbound | 1 | A-SECOND-MSG-OK
6 | 2026-10-29T10:05:36.549597+00:00 | custa | 2 | customer | human | web_chat | inbound | 1 | A-SECOND-MSG-OK

$ sqlite3(ro) SELECT action, COUNT(*) AS n FROM audit_log WHERE action LIKE '%denied%' OR action LIKE '%forbid%' OR action LIKE '%access%' GROUP BY action
action | n

$ sqlite3(ro) SELECT id, workflow_status, current_version_id FROM estimates WHERE id IN (1,2)
id | workflow_status | current_version_id
1 | DRAFT | 
2 | DRAFT | 

$ sqlite3(ro) SELECT id, status, customer_signed_at, customer_signature_data FROM contracts WHERE id IN (1,2)
id | status | customer_signed_at | customer_signature_data
1 | draft |  | 
2 | draft |  | 

$ sqlite3(ro) SELECT id, notes FROM projects WHERE id IN (1,2)
id | notes
1 | HUMAN-EDITED-NOTE-A
2 | INTERNAL-NOTE-PROJ-B

$ sqlite3(ro) SELECT id, estimate_version_id, description FROM estimate_line_items WHERE description LIKE 'ATTACK%' OR description LIKE '%INTERNAL-COST%'
id | estimate_version_id | description
1 | 1 | INTERNAL-COST-LINE-A cabinets
2 | 2 | INTERNAL-COST-LINE-B cabinets

$ sqlite3(ro) SELECT id, project_id, name FROM project_milestones
id | project_id | name
1 | 2 | MILESTONE-B-ONLY

## STEP server stop (tracked PID 17251 only)
$ ps -p 17251 -o pid,args
  PID COMMAND
17251 python3 -m restoricon_core.api.server --port 18770
$ server log tail (PRODUCTION count):
2026-10-29 06:02:27,406 [INFO] Restoricon Core API server starting on http://127.0.0.1:18770
2026-10-29 06:02:27,422 [INFO] Estimate expiry sweep thread started (interval=3600s)
PRODUCTION lines: 0
$ kill -INT 17251
t=1s still alive
t=2s still alive
t=3s gone
## STEP post-stop checks
$ ps aux | grep -E 'restoricon|api.server|llama' (excluding this grep)
(end ps)
connect_ex 18770 = 111
$ tools.world list --json (before destroy)
[{"name": "p012", "port": 18770, "created_at": "2026-10-29T10:00:04.593121+00:00", "source": "empty", "state": "ok"}]
$ tools.world destroy p012 (dry run)
would delete /data/data/com.termux/files/home/.codeyOS-worlds/p012 (17 entries, port 18770); re-run with --yes to proceed
exit=2
$ tools.world destroy p012 --yes
destroyed world p012: /data/data/com.termux/files/home/.codeyOS-worlds/p012 (17 entries)
exit=0
$ tools.world list --json (after destroy)
[]
total 24
drwx------.  2 u0_a247 u0_a247  3452 Oct 29 06:06 .
drwx------. 60 u0_a247 u0_a247 20480 Oct 29 05:59 ..
-rw-------.  1 u0_a247 u0_a247    42 Oct 28 18:41 .codey-worlds-root
-rw-------.  1 u0_a247 u0_a247     0 Oct 28 18:41 .lock
## STEP final live-store comparison and free
$ stat live files (after)
/data/data/com.termux/files/home/.codeyOS/restoricon.db size=4018176 mtime=2026-09-30 17:50:45.731747783 -0400 inode=2724812
/data/data/com.termux/files/home/.codeyOS/restoricon.db-wal size=1281352 mtime=2026-10-24 11:53:26.797089718 -0400 inode=2948088
/data/data/com.termux/files/home/.codeyOS/restoricon.db-shm size=32768 mtime=2026-10-28 17:56:33.473673891 -0400 inode=2948380
/data/data/com.termux/files/home/.codeyOS/action_gateway_audit.jsonl size=51219 mtime=2026-10-28 17:57:27.481673871 -0400 inode=3046699
/data/data/com.termux/files/home/.codeyOS/restoricon_documents size=3452 mtime=2026-09-22 08:11:50.997857761 -0400 inode=2491094
$ free -h
               total        used        free      shared  buff/cache   available
Mem:            10Gi       5.8Gi       1.5Gi        54Mi       3.9Gi       5.0Gi
Swap:           15Gi       2.7Gi        13Gi
$ ps aux | grep llama-server
u0_a247  22012 33.3  0.0 12433868 4368 ?       Ss    2022   0:00 /data/data/com.termux/files/usr/bin/bash -c source /data/data/com.termux/files/home/.claude/shell-snapshots/snapshot-bash-1793104499531-8pmodt.sh 2>/dev/null || true && shopt -u extglob 2>/dev/null || true && { \builtin unalias -- 'unsetenv'; \builtin unset -f -- 'unsetenv'; } >/dev/null 2>&1 || true && eval '{ echo "## STEP final live-store comparison and free"; echo "\$ stat live files (after)"; stat -c '"'"'%n size=%s mtime=%y inode=%i'"'"' ~/.codeyOS/restoricon.db ~/.codeyOS/restoricon.db-wal ~/.codeyOS/restoricon.db-shm ~/.codeyOS/action_gateway_audit.jsonl ~/.codeyOS/restoricon_documents; echo "\$ free -h"; free -h; echo "\$ ps aux | grep llama-server"; ps aux | /data/data/com.termux/files/usr/bin/grep llama-server; echo "(end)"; echo "\$ ps aux | grep -E '"'"'restoricon|api.server'"'"'"; ps aux | /data/data/com.termux/files/usr/bin/grep -E '"'"'restoricon|api.server'"'"' | /data/data/com.termux/files/usr/bin/grep -v '"'"'grep -E'"'"'; echo "(end)"; } 2>&1 | tee -a /data/data/com.termux/files/usr/tmp/p0_1_2_transcript.md' < /dev/null && pwd -P >| /data/data/com.termux/files/usr/tmp/claude-8de4-cwd
u0_a247  22013  8.3  0.0 12433868 2228 ?       S     2022   0:00 /data/data/com.termux/files/usr/bin/bash -c source /data/data/com.termux/files/home/.claude/shell-snapshots/snapshot-bash-1793104499531-8pmodt.sh 2>/dev/null || true && shopt -u extglob 2>/dev/null || true && { \builtin unalias -- 'unsetenv'; \builtin unset -f -- 'unsetenv'; } >/dev/null 2>&1 || true && eval '{ echo "## STEP final live-store comparison and free"; echo "\$ stat live files (after)"; stat -c '"'"'%n size=%s mtime=%y inode=%i'"'"' ~/.codeyOS/restoricon.db ~/.codeyOS/restoricon.db-wal ~/.codeyOS/restoricon.db-shm ~/.codeyOS/action_gateway_audit.jsonl ~/.codeyOS/restoricon_documents; echo "\$ free -h"; free -h; echo "\$ ps aux | grep llama-server"; ps aux | /data/data/com.termux/files/usr/bin/grep llama-server; echo "(end)"; echo "\$ ps aux | grep -E '"'"'restoricon|api.server'"'"'"; ps aux | /data/data/com.termux/files/usr/bin/grep -E '"'"'restoricon|api.server'"'"' | /data/data/com.termux/files/usr/bin/grep -v '"'"'grep -E'"'"'; echo "(end)"; } 2>&1 | tee -a /data/data/com.termux/files/usr/tmp/p0_1_2_transcript.md' < /dev/null && pwd -P >| /data/data/com.termux/files/usr/tmp/claude-8de4-cwd
u0_a247  22018 50.0  0.0  21352  1124 ?        R     2022   0:00 /data/data/com.termux/files/usr/bin/grep llama-server
(end)
$ ps aux | grep -E 'restoricon|api.server'
(end)
