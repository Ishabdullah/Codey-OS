"""
Restoricon Core Web Surfaces — Staff/Admin ERP & Customer Portal SPAs.
Served directly via the phone's API server over Cloudflare Tunnel or local loopback.
"""

def render_login_surface(portal_type: str = "admin") -> str:
    """Render responsive, accessible login page."""
    title = "Restoricon Staff & Admin Portal" if portal_type == "admin" else "Restoricon Customer Portal"
    subtitle = "Secure ERP & Operations Hub" if portal_type == "admin" else "Track your project, invoices, and contracts"
    target_api = "/api/v1/auth/login"
    redirect_target = "/admin" if portal_type == "admin" else "/portal"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        :root {{
            --primary: #1e3a8a;
            --primary-hover: #172554;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border: #e2e8f0;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
        body {{ background-color: var(--bg); color: var(--text-main); display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 1.5rem; }}
        .login-card {{ background: var(--card-bg); width: 100%; max-width: 420px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1); border: 1px solid var(--border); padding: 2.5rem 2rem; }}
        .header {{ text-align: center; margin-bottom: 2rem; }}
        .header h1 {{ font-size: 1.5rem; font-weight: 700; color: var(--primary); margin-bottom: 0.5rem; }}
        .header p {{ color: var(--text-muted); font-size: 0.9rem; }}
        .form-group {{ margin-bottom: 1.25rem; }}
        label {{ display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 0.4rem; }}
        input {{ width: 100%; padding: 0.75rem 1rem; border: 1px solid var(--border); border-radius: 6px; font-size: 0.95rem; }}
        input:focus {{ outline: 2px solid var(--primary); outline-offset: 1px; }}
        .btn-submit {{ width: 100%; background: var(--primary); color: white; padding: 0.85rem; border: none; border-radius: 6px; font-weight: 600; font-size: 1rem; cursor: pointer; transition: background 0.15s ease; }}
        .btn-submit:hover {{ background: var(--primary-hover); }}
        .error-msg {{ background: #fef2f2; color: #991b1b; padding: 0.75rem; border-radius: 6px; font-size: 0.85rem; margin-bottom: 1rem; display: none; border: 1px solid #fecaca; }}
    </style>
</head>
<body>
    <div class="login-card">
        <div class="header">
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        <div id="errorBox" class="error-msg"></div>
        <form id="loginForm">
            <div class="form-group">
                <label for="username">Username / Email</label>
                <input type="text" id="username" required autocomplete="username">
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" required autocomplete="current-password">
            </div>
            <button type="submit" class="btn-submit">Sign In</button>
        </form>
    </div>
    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {{
            e.preventDefault();
            const err = document.getElementById('errorBox');
            err.style.display = 'none';
            const u = document.getElementById('username').value;
            const p = document.getElementById('password').value;
            try {{
                const res = await fetch('{target_api}', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ username: u, password: p }})
                }});
                const data = await res.json();
                if (res.ok && data.token) {{
                    localStorage.setItem('restoricon_token', data.token);
                    localStorage.setItem('restoricon_user', JSON.stringify(data.user || {{}}));
                    window.location.href = '{redirect_target}';
                }} else {{
                    err.textContent = data.error || 'Invalid credentials. Please try again.';
                    err.style.display = 'block';
                }}
            }} catch (errExp) {{
                err.textContent = 'Connection error. Please check server connection.';
                err.style.display = 'block';
            }}
        }});
    </script>
</body>
</html>"""


def render_admin_surface() -> str:
    """Render Staff/Admin Operations Dashboard SPA."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Restoricon ERP — Staff & Operations Dashboard</title>
    <style>
        :root {
            --primary: #1e3a8a;
            --primary-light: #eff6ff;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text: #0f172a;
            --muted: #64748b;
            --border: #e2e8f0;
            --success: #16a34a;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        body { background: var(--bg); color: var(--text); display: flex; height: 100vh; overflow: hidden; }
        .sidebar { width: 260px; background: #0f172a; color: white; display: flex; flex-direction: column; padding: 1.5rem 1rem; }
        .brand { font-size: 1.25rem; font-weight: 700; color: #60a5fa; margin-bottom: 2rem; display: flex; align-items: center; gap: 0.5rem; }
        .nav-item { padding: 0.75rem 1rem; border-radius: 6px; color: #94a3b8; font-size: 0.95rem; cursor: pointer; margin-bottom: 0.25rem; text-decoration: none; display: flex; align-items: center; }
        .nav-item.active, .nav-item:hover { background: #1e293b; color: white; font-weight: 600; }
        .main-content { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        .topbar { height: 64px; background: white; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; padding: 0 2rem; }
        .search-bar input { padding: 0.5rem 1rem; border: 1px solid var(--border); border-radius: 6px; width: 320px; }
        .dashboard-body { flex: 1; padding: 2rem; overflow-y: auto; }
        .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }
        .kpi-card { background: white; padding: 1.5rem; border-radius: 10px; border: 1px solid var(--border); box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
        .kpi-title { font-size: 0.85rem; color: var(--muted); margin-bottom: 0.5rem; }
        .kpi-value { font-size: 1.75rem; font-weight: 700; }
        .section-card { background: white; border-radius: 10px; border: 1px solid var(--border); padding: 1.5rem; margin-bottom: 1.5rem; }
        .section-header { font-size: 1.1rem; font-weight: 700; margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center; }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); font-size: 0.9rem; }
        th { color: var(--muted); font-weight: 600; background: var(--bg); }
        .badge { padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }
        .badge-active { background: #dcfce7; color: #15803d; }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="brand">Restoricon ERP</div>
        <div class="nav-item active" onclick="showTab('overview')">Overview</div>
        <div class="nav-item" onclick="showTab('projects')">Projects & Sites</div>
        <div class="nav-item" onclick="showTab('finance')">Financial Ledger</div>
        <div class="nav-item" onclick="showTab('schedule')">Appointments</div>
        <div class="nav-item" onclick="showTab('compliance')">Compliance Scanner</div>
        <div class="nav-item" style="margin-top: auto;" onclick="logout()">Sign Out</div>
    </div>
    <div class="main-content">
        <div class="topbar">
            <div class="search-bar">
                <input type="text" id="globalSearchInput" placeholder="Search customers, projects, leads..." onkeyup="handleSearch(event)">
            </div>
            <div id="userBadge" style="font-weight: 600;">Staff Admin</div>
        </div>
        <div class="dashboard-body">
            <div class="kpi-grid">
                <div class="kpi-card"><div class="kpi-title">Total Revenue</div><div id="kpiRev" class="kpi-value">$0.00</div></div>
                <div class="kpi-card"><div class="kpi-title">Active Projects</div><div id="kpiProjects" class="kpi-value">0</div></div>
                <div class="kpi-card"><div class="kpi-title">Gross Margin</div><div id="kpiMargin" class="kpi-value">0.0%</div></div>
                <div class="kpi-card"><div class="kpi-title">Open Leads</div><div id="kpiLeads" class="kpi-value">0</div></div>
            </div>
            <div class="section-card">
                <div class="section-header">
                    <span>Active Restoration Job Sites</span>
                </div>
                <table>
                    <thead>
                        <tr><th>ID</th><th>Project Name</th><th>Customer</th><th>Status</th><th>Contract Total</th></tr>
                    </thead>
                    <tbody id="projectsTable">
                        <tr><td colspan="5" style="text-align:center;">Loading project data...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    <script>
        const token = localStorage.getItem('restoricon_token');
        if (!token) { window.location.href = '/admin/login'; }
        
        async function fetchDashboard() {
            try {
                const h = { 'Authorization': 'Bearer ' + token };
                const resRep = await fetch('/api/v1/reports/executive', { headers: h });
                if (resRep.status === 401) { logout(); return; }
                const dataRep = await resRep.json();
                
                document.getElementById('kpiRev').textContent = '$' + (dataRep.financial?.total_revenue || 0).toLocaleString();
                document.getElementById('kpiProjects').textContent = dataRep.operations?.active_projects_count || 0;
                document.getElementById('kpiMargin').textContent = (dataRep.financial?.gross_margin_percent || 0) + '%';
                document.getElementById('kpiLeads').textContent = dataRep.sales?.leads_count || 0;

                const resProj = await fetch('/api/v1/projects?limit=10', { headers: h });
                const dataProj = await resProj.json();
                const tbody = document.getElementById('projectsTable');
                if (dataProj.projects && dataProj.projects.length > 0) {
                    tbody.innerHTML = dataProj.projects.map(p => `
                        <tr>
                            <td>#${p.id}</td>
                            <td><strong>${p.title || p.name || 'Site'}</strong></td>
                            <td>Customer #${p.customer_id}</td>
                            <td><span class="badge badge-active">${p.status}</span></td>
                            <td>$${(p.contract_amount || 0).toLocaleString()}</td>
                        </tr>
                    `).join('');
                } else {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;">No projects found.</td></tr>';
                }
            } catch (err) {
                console.error('Failed to load dashboard:', err);
            }
        }
        function logout() {
            localStorage.removeItem('restoricon_token');
            window.location.href = '/admin/login';
        }
        function showTab(tab) { console.log('Tab selected:', tab); }
        function handleSearch(e) { if (e.key === 'Enter') { window.location.href = `/api/v1/search?q=${encodeURIComponent(e.target.value)}`; } }
        fetchDashboard();
    </script>
</body>
</html>"""


def render_portal_surface() -> str:
    """Render Customer Portal SPA with project status, contract e-signatures, and invoices."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Restoricon Customer Portal</title>
    <style>
        :root {
            --primary: #0284c7;
            --primary-hover: #0369a1;
            --bg: #f0f9ff;
            --card-bg: #ffffff;
            --text: #0f172a;
            --muted: #64748b;
            --border: #e0f2fe;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        body { background: #f8fafc; color: var(--text); padding: 2rem 1rem; display: flex; justify-content: center; }
        .portal-container { max-width: 900px; width: 100%; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; }
        .header h1 { font-size: 1.5rem; color: #0369a1; }
        .btn-logout { background: white; border: 1px solid #cbd5e1; padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 600; }
        .card { background: white; border-radius: 12px; border: 1px solid #e2e8f0; padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
        .card-header { font-size: 1.2rem; font-weight: 700; margin-bottom: 1rem; color: #0f172a; }
        .project-item { border-bottom: 1px solid #f1f5f9; padding: 1rem 0; }
        .project-item:last-child { border-bottom: none; }
        .project-title { font-weight: 600; font-size: 1.05rem; }
        .status-pill { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600; background: #e0f2fe; color: #0369a1; }
        .btn-action { background: var(--primary); color: white; border: none; padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 600; }
    </style>
</head>
<body>
    <div class="portal-container">
        <div class="header">
            <div>
                <h1>Your Restoration Portal</h1>
                <p style="color: var(--muted); font-size: 0.9rem;">Track your project progress, signed contracts, and invoices</p>
            </div>
            <button class="btn-logout" onclick="logout()">Sign Out</button>
        </div>

        <div class="card">
            <div class="card-header">Your Active Projects</div>
            <div id="projectsList">Loading your project information...</div>
        </div>

        <div class="card">
            <div class="card-header">Contracts & Estimates Requiring Review</div>
            <div id="contractsList">Checking outstanding contracts...</div>
        </div>
    </div>
    <script>
        const token = localStorage.getItem('restoricon_token');
        if (!token) { window.location.href = '/portal/login'; }

        async function loadPortalData() {
            try {
                const h = { 'Authorization': 'Bearer ' + token };
                const resProj = await fetch('/api/v1/portal/projects', { headers: h });
                if (resProj.status === 401) { logout(); return; }
                const dataProj = await resProj.json();
                
                const projEl = document.getElementById('projectsList');
                if (dataProj.projects && dataProj.projects.length > 0) {
                    projEl.innerHTML = dataProj.projects.map(p => `
                        <div class="project-item">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <div class="project-title">${p.title || p.name || 'Restoration Service'}</div>
                                <span class="status-pill">${p.status}</span>
                            </div>
                            <p style="color:var(--muted); font-size:0.85rem; margin-top:0.3rem;">Contract Amount: $${(p.contract_amount || 0).toLocaleString()}</p>
                        </div>
                    `).join('');
                } else {
                    projEl.innerHTML = '<p style="color:var(--muted);">No active restoration projects found.</p>';
                }

                const resContr = await fetch('/api/v1/portal/contracts', { headers: h });
                const dataContr = await resContr.json();
                const contrEl = document.getElementById('contractsList');
                if (dataContr.contracts && dataContr.contracts.length > 0) {
                    contrEl.innerHTML = dataContr.contracts.map(c => `
                        <div class="project-item" style="display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <div class="project-title">Contract #${c.id} - ${c.title || 'Service Agreement'}</div>
                                <p style="color:var(--muted); font-size:0.85rem;">Status: ${c.status || 'Pending Review'}</p>
                            </div>
                            <button class="btn-action" onclick="signContract(${c.id})">Review & Sign</button>
                        </div>
                    `).join('');
                } else {
                    contrEl.innerHTML = '<p style="color:var(--muted);">All contracts and estimates are up to date.</p>';
                }
            } catch (err) {
                console.error('Portal load error:', err);
            }
        }
        function logout() {
            localStorage.removeItem('restoricon_token');
            window.location.href = '/portal/login';
        }
        function signContract(id) {
            alert('Opening digital contract #' + id + ' for e-signature...');
        }
        loadPortalData();
    </script>
</body>
</html>"""


def render_quote_surface() -> str:
    """Render public quote & emergency dispatch intake form."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Restoricon — Request Restoration Quote & Emergency Service</title>
    <style>
        :root {
            --primary: #1e3a8a;
            --primary-hover: #172554;
            --accent: #dc2626;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --success: #15803d;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        body { background-color: var(--bg); color: var(--text-main); line-height: 1.5; padding: 2rem 1rem; }
        .container { max-width: 680px; margin: 0 auto; background: var(--card-bg); border-radius: 12px; border: 1px solid var(--border); box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); padding: 2.5rem 2rem; }
        .header { text-align: center; margin-bottom: 2rem; }
        .header h1 { font-size: 1.75rem; color: var(--primary); margin-bottom: 0.5rem; font-weight: 700; }
        .header p { color: var(--text-muted); font-size: 0.95rem; }
        .badge-emergency { display: inline-block; background: #fee2e2; color: var(--accent); padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; margin-bottom: 0.75rem; }
        .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1.25rem; }
        .form-group { margin-bottom: 1.25rem; }
        .form-group.full { grid-column: 1 / -1; }
        label { display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 0.4rem; color: var(--text-main); }
        input, select, textarea { width: 100%; padding: 0.75rem 1rem; border: 1px solid var(--border); border-radius: 6px; font-size: 0.95rem; background: #fff; }
        input:focus, select:focus, textarea:focus { outline: 2px solid var(--primary); outline-offset: 1px; }
        textarea { resize: vertical; min-height: 100px; }
        .btn-submit { width: 100%; background: var(--primary); color: white; padding: 0.9rem; border: none; border-radius: 6px; font-weight: 600; font-size: 1.05rem; cursor: pointer; transition: background 0.15s ease; }
        .btn-submit:hover { background: var(--primary-hover); }
        .alert-box { padding: 1rem; border-radius: 6px; margin-bottom: 1.5rem; display: none; font-size: 0.95rem; }
        .alert-success { background: #f0fdf4; color: var(--success); border: 1px solid #bbf7d0; }
        .alert-error { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
        @media (max-width: 600px) {
            .form-grid { grid-template-columns: 1fr; }
            .container { padding: 1.5rem 1rem; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span class="badge-emergency">24/7 Rapid Response</span>
            <h1>Request a Restoration Quote</h1>
            <p>Immediate mitigation, water damage, fire & smoke repair, mold remediation, and reconstruction services.</p>
        </div>

        <div id="statusAlert" class="alert-box"></div>

        <form id="quoteForm">
            <div class="form-grid">
                <div class="form-group">
                    <label for="full_name">Your Full Name *</label>
                    <input type="text" id="full_name" required placeholder="Jane Doe">
                </div>
                <div class="form-group">
                    <label for="phone">Phone Number *</label>
                    <input type="tel" id="phone" required placeholder="(555) 000-0000">
                </div>
                <div class="form-group full">
                    <label for="email">Email Address *</label>
                    <input type="email" id="email" required placeholder="jane@example.com">
                </div>
                <div class="form-group full">
                    <label for="property_address">Property Address / Location *</label>
                    <input type="text" id="property_address" required placeholder="123 Main St, City, State, ZIP">
                </div>
                <div class="form-group">
                    <label for="service_type">Damage / Service Type *</label>
                    <select id="service_type" required>
                        <option value="water">Water Damage & Extraction</option>
                        <option value="fire">Fire & Smoke Damage</option>
                        <option value="mold">Mold Remediation</option>
                        <option value="storm">Storm & Structural Damage</option>
                        <option value="reconstruction">Full Reconstruction</option>
                        <option value="commercial">Commercial Restoration</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="urgency">Urgency Level *</label>
                    <select id="urgency" required>
                        <option value="emergency">Emergency (Immediate Dispatch Needed)</option>
                        <option value="high">High (Within 24 Hours)</option>
                        <option value="standard" selected>Standard (Schedule an Inspection)</option>
                    </select>
                </div>
                <div class="form-group full">
                    <label for="description">Describe the Damage / Scope of Work</label>
                    <textarea id="description" placeholder="Briefly describe the affected areas, visible damage, source of water/fire, or insurance claims in progress..."></textarea>
                </div>
            </div>
            <button type="submit" id="submitBtn" class="btn-submit">Submit Quote Request</button>
        </form>
    </div>

    <script>
        document.getElementById('quoteForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const btn = document.getElementById('submitBtn');
            const alertBox = document.getElementById('statusAlert');
            btn.disabled = true;
            btn.innerText = 'Submitting Request...';
            alertBox.style.display = 'none';

            const payload = {
                name: document.getElementById('full_name').value.trim(),
                phone: document.getElementById('phone').value.trim(),
                email: document.getElementById('email').value.trim(),
                address: document.getElementById('property_address').value.trim(),
                service_type: document.getElementById('service_type').value,
                urgency: document.getElementById('urgency').value,
                notes: document.getElementById('description').value.trim(),
                source: 'quote_subdomain'
            };

            try {
                const res = await fetch('/api/v1/public/leads', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (res.ok) {
                    alertBox.className = 'alert-box alert-success';
                    alertBox.innerHTML = '<strong>Request Received!</strong> Your quote request has been logged (Ref #' + (data.lead_id || 'NEW') + '). Our emergency dispatch team is reviewing your details and will contact you immediately.';
                    alertBox.style.display = 'block';
                    document.getElementById('quoteForm').reset();
                    btn.innerText = 'Request Submitted Successfully';
                } else {
                    alertBox.className = 'alert-box alert-error';
                    alertBox.innerHTML = '<strong>Submission Error:</strong> ' + (data.error || 'Failed to process your request. Please call our emergency dispatch directly.');
                    alertBox.style.display = 'block';
                    btn.disabled = false;
                    btn.innerText = 'Submit Quote Request';
                }
            } catch (err) {
                alertBox.className = 'alert-box alert-error';
                alertBox.innerHTML = '<strong>Network Error:</strong> Unable to reach dispatch server. Please try again or call support.';
                alertBox.style.display = 'block';
                btn.disabled = false;
                btn.innerText = 'Submit Quote Request';
            }
        });
    </script>
</body>
</html>"""

