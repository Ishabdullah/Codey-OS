"""
Restoricon Core Web Surfaces — Staff/Admin ERP, Customer Portal, & Quote Intake SPAs.
Served directly via the phone's API server over Cloudflare Tunnel or local loopback.
"""

def render_login_surface(portal_type: str = "admin") -> str:
    """Render responsive, accessible, premium login page."""
    is_admin = portal_type == "admin"
    title = "Restoricon Staff & Admin Portal" if is_admin else "Restoricon Customer Portal"
    subtitle = "Enterprise ERP & Disaster Operations Center" if is_admin else "Track your restoration project, contracts, and invoices"
    target_api = "/api/v1/auth/login"
    redirect_target = "/admin" if is_admin else "/portal"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — Restoricon</title>
    <style>
        :root {{
            --primary: #1e3a8a;
            --primary-hover: #172554;
            --accent: #2563eb;
            --bg: #0f172a;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border: #e2e8f0;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
        body {{
            background: linear-gradient(135deg, #0b0f19 0%, #1e293b 100%);
            color: var(--text-main);
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 1.5rem;
        }}
        .login-card {{
            background: var(--card-bg);
            width: 100%;
            max-width: 440px;
            border-radius: 16px;
            box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.3), 0 8px 10px -6px rgb(0 0 0 / 0.3);
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 2.75rem 2.25rem;
        }}
        .brand-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            background: #eff6ff;
            color: #1e40af;
            font-size: 0.8rem;
            font-weight: 700;
            padding: 0.35rem 0.85rem;
            border-radius: 9999px;
            margin-bottom: 1rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .header {{ text-align: center; margin-bottom: 2rem; }}
        .header h1 {{ font-size: 1.6rem; font-weight: 800; color: #0f172a; margin-bottom: 0.5rem; letter-spacing: -0.02em; }}
        .header p {{ color: var(--text-muted); font-size: 0.9rem; line-height: 1.4; }}
        .form-group {{ margin-bottom: 1.25rem; }}
        label {{ display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 0.4rem; color: #334155; }}
        input {{
            width: 100%;
            padding: 0.85rem 1rem;
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 0.95rem;
            transition: border-color 0.15s, box-shadow 0.15s;
        }}
        input:focus {{ outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15); }}
        .btn-submit {{
            width: 100%;
            background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
            color: white;
            padding: 0.9rem;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 1rem;
            cursor: pointer;
            transition: transform 0.1s, box-shadow 0.15s;
            box-shadow: 0 4px 6px -1px rgba(30, 58, 138, 0.2);
            margin-top: 0.5rem;
        }}
        .btn-submit:hover {{ background: #172554; box-shadow: 0 6px 8px -1px rgba(30, 58, 138, 0.3); }}
        .error-msg {{
            background: #fef2f2;
            color: #991b1b;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            font-size: 0.85rem;
            margin-bottom: 1.25rem;
            display: none;
            border: 1px solid #fecaca;
        }}
        .switch-portal {{
            text-align: center;
            margin-top: 1.5rem;
            font-size: 0.85rem;
            color: var(--text-muted);
            border-top: 1px solid #f1f5f9;
            padding-top: 1.25rem;
        }}
        .switch-portal a {{ color: var(--accent); text-decoration: none; font-weight: 600; }}
        .switch-portal a:hover {{ text-decoration: underline; }}
        .demo-bar {{
            margin-top: 1.25rem;
            background: #f8fafc;
            border: 1px dashed #cbd5e1;
            border-radius: 8px;
            padding: 0.75rem;
            font-size: 0.8rem;
            text-align: center;
            color: #475569;
        }}
        .demo-btn {{
            display: inline-block;
            background: #e2e8f0;
            color: #1e293b;
            padding: 0.25rem 0.6rem;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 600;
            margin: 0.2rem;
            border: none;
        }}
        .demo-btn:hover {{ background: #cbd5e1; }}
    </style>
</head>
<body>
    <div class="login-card">
        <div class="header">
            <span class="brand-badge">⚡ Restoricon Core</span>
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>

        <div id="errorBox" class="error-msg"></div>

        <form id="loginForm">
            <div class="form-group">
                <label for="username">Username / Email Address</label>
                <input type="text" id="username" required autocomplete="username" placeholder="Enter username or email">
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" required autocomplete="current-password" placeholder="••••••••">
            </div>
            <button type="submit" id="submitBtn" class="btn-submit">Sign In</button>
        </form>

        <div class="demo-bar">
            <span>Quick Login Fill:</span><br>
            <button type="button" class="demo-btn" onclick="fillDemo('admin', 'admin123')">Admin (Ish)</button>
            <button type="button" class="demo-btn" onclick="fillDemo('tech', 'tech123')">Technician</button>
            <button type="button" class="demo-btn" onclick="fillDemo('customer@example.com', 'client123')">Client</button>
        </div>

        <div class="switch-portal">
            {"Access customer files? <a href='/portal/login'>Go to Customer Portal</a>" if is_admin else "Staff member? <a href='/admin/login'>Go to Staff ERP</a>"}
            <br><span style="margin-top: 0.4rem; display: inline-block;"><a href="/quote" style="color:#64748b;">← Request Restoration Quote</a></span>
        </div>
    </div>

    <script>
        function fillDemo(u, p) {{
            document.getElementById('username').value = u;
            document.getElementById('password').value = p;
        }}

        document.getElementById('loginForm').addEventListener('submit', async (e) => {{
            e.preventDefault();
            const btn = document.getElementById('submitBtn');
            const err = document.getElementById('errorBox');
            err.style.display = 'none';
            btn.disabled = true;
            btn.innerText = 'Authenticating...';

            const u = document.getElementById('username').value.trim();
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
                    err.textContent = data.error || 'Invalid credentials. Please verify your username and password.';
                    err.style.display = 'block';
                    btn.disabled = false;
                    btn.innerText = 'Sign In';
                }}
            }} catch (errExp) {{
                err.textContent = 'Server connection failed. Please ensure the Restoricon backend is running.';
                err.style.display = 'block';
                btn.disabled = false;
                btn.innerText = 'Sign In';
            }}
        }});
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
    <title>Restoricon — 24/7 Rapid Disaster Restoration & Emergency Services</title>
    <style>
        :root {
            --primary: #1e3a8a;
            --primary-hover: #172554;
            --accent: #dc2626;
            --accent-hover: #b91c1c;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --success: #15803d;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        body { background-color: var(--bg); color: var(--text-main); line-height: 1.5; }
        
        .emergency-hotline-bar {
            background: #991b1b;
            color: white;
            text-align: center;
            padding: 0.65rem 1rem;
            font-size: 0.9rem;
            font-weight: 600;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 1rem;
            flex-wrap: wrap;
        }
        .emergency-hotline-bar a { color: #fef08a; text-decoration: none; font-weight: 700; }
        .emergency-hotline-bar a:hover { text-decoration: underline; }

        .nav {
            background: white;
            border-bottom: 1px solid var(--border);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 50;
        }
        .brand { font-size: 1.35rem; font-weight: 800; color: #1e3a8a; display: flex; align-items: center; gap: 0.5rem; text-decoration: none; }
        .brand span { color: var(--accent); }
        .nav-links { display: flex; gap: 1.25rem; align-items: center; }
        .nav-links a { color: #334155; text-decoration: none; font-size: 0.9rem; font-weight: 600; }
        .nav-links a:hover { color: var(--primary); }
        .nav-btn { background: #1e3a8a; color: white !important; padding: 0.5rem 1rem; border-radius: 6px; }

        .hero {
            background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
            color: white;
            padding: 3.5rem 1.5rem;
            text-align: center;
        }
        .hero-badge { display: inline-block; background: rgba(220, 38, 38, 0.25); border: 1px solid rgba(220, 38, 38, 0.5); color: #fca5a5; padding: 0.35rem 0.9rem; border-radius: 9999px; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-bottom: 1rem; }
        .hero h1 { font-size: 2.5rem; font-weight: 800; line-height: 1.2; margin-bottom: 1rem; letter-spacing: -0.02em; }
        .hero p { max-width: 650px; margin: 0 auto 1.75rem auto; color: #cbd5e1; font-size: 1.1rem; }
        .trust-grid { display: flex; justify-content: center; gap: 2rem; flex-wrap: wrap; margin-top: 1.5rem; }
        .trust-item { display: flex; align-items: center; gap: 0.5rem; font-size: 0.9rem; color: #94a3b8; font-weight: 600; }

        .main-container { max-width: 1080px; margin: -2.5rem auto 3rem auto; padding: 0 1rem; display: grid; grid-template-columns: 1fr 380px; gap: 2rem; position: relative; z-index: 10; }
        .form-card { background: white; border-radius: 16px; border: 1px solid var(--border); box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.08); padding: 2.5rem 2rem; }
        .sidebar-card { background: white; border-radius: 16px; border: 1px solid var(--border); box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.08); padding: 2rem; height: fit-content; }

        .form-header { margin-bottom: 2rem; }
        .form-header h2 { font-size: 1.5rem; font-weight: 700; color: #0f172a; margin-bottom: 0.3rem; }
        .form-header p { color: var(--text-muted); font-size: 0.9rem; }

        .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; margin-bottom: 1.5rem; }
        .form-group { margin-bottom: 1.25rem; }
        .form-group.full { grid-column: 1 / -1; }
        label { display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 0.4rem; color: #1e293b; }
        input, select, textarea { width: 100%; padding: 0.8rem 1rem; border: 1px solid var(--border); border-radius: 8px; font-size: 0.95rem; background: #fff; }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15); }
        textarea { resize: vertical; min-height: 95px; }

        .service-picker { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; margin-bottom: 1.25rem; }
        .service-opt {
            border: 2px solid var(--border);
            border-radius: 8px;
            padding: 0.85rem 0.5rem;
            text-align: center;
            cursor: pointer;
            transition: all 0.15s;
            background: #f8fafc;
        }
        .service-opt.selected { border-color: #1e40af; background: #eff6ff; color: #1e40af; font-weight: 700; }
        .service-opt span { display: block; font-size: 1.3rem; margin-bottom: 0.2rem; }
        .service-opt p { font-size: 0.8rem; margin: 0; }

        .btn-submit {
            width: 100%;
            background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%);
            color: white;
            padding: 1.1rem;
            border: none;
            border-radius: 8px;
            font-weight: 700;
            font-size: 1.1rem;
            cursor: pointer;
            transition: transform 0.1s, box-shadow 0.15s;
            box-shadow: 0 4px 6px -1px rgba(220, 38, 38, 0.3);
        }
        .btn-submit:hover { background: #b91c1c; }

        .calculator-widget { background: #f8fafc; border: 1px solid var(--border); border-radius: 12px; padding: 1.25rem; margin-bottom: 1.5rem; }
        .calc-title { font-size: 0.95rem; font-weight: 700; color: #0f172a; margin-bottom: 0.75rem; display: flex; align-items: center; gap: 0.4rem; }
        .slider-wrap { margin-bottom: 1rem; }
        .slider-wrap label { display: flex; justify-content: space-between; font-size: 0.85rem; font-weight: 600; color: #475569; }
        .slider-wrap input[type=range] { width: 100%; margin-top: 0.4rem; }
        .calc-result { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.85rem; text-align: center; }
        .calc-result-val { font-size: 1.35rem; font-weight: 800; color: #1e3a8a; }

        .tracker-widget { background: #f8fafc; border: 1px solid var(--border); border-radius: 12px; padding: 1.25rem; }
        .tracker-input-group { display: flex; gap: 0.5rem; margin-top: 0.5rem; }
        .tracker-input-group input { flex: 1; padding: 0.6rem; font-size: 0.85rem; }
        .tracker-input-group button { background: #1e3a8a; color: white; border: none; padding: 0 0.85rem; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 0.85rem; }

        .alert-box { padding: 1.25rem; border-radius: 8px; margin-bottom: 1.5rem; display: none; font-size: 0.95rem; }
        .alert-success { background: #f0fdf4; color: var(--success); border: 1px solid #bbf7d0; }
        .alert-error { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }

        @media (max-width: 860px) {
            .main-container { grid-template-columns: 1fr; margin-top: -1.5rem; }
            .form-grid { grid-template-columns: 1fr; }
            .service-picker { grid-template-columns: repeat(2, 1fr); }
            .hero h1 { font-size: 2rem; }
        }
    </style>
</head>
<body>
    <div class="emergency-hotline-bar">
        <span>🚨 <strong>24/7 Emergency Dispatch Center Active:</strong> On-Site in Under 60 Minutes</span>
        <span>Call Now: <a href="tel:8005557378">(800) 555-RESTORE</a></span>
    </div>

    <nav class="nav">
        <a href="/" class="brand">⚡ Restoricon<span>.</span></a>
        <div class="nav-links">
            <a href="/portal">Customer Portal</a>
            <a href="/admin">Staff ERP</a>
            <a href="#quoteSection" class="nav-btn">Request Dispatch</a>
        </div>
    </nav>

    <header class="hero">
        <span class="hero-badge">⚡ Immediate Response Team Standing By</span>
        <h1>Disaster Recovery & Property Restoration</h1>
        <p>Licensed, bonded, and certified emergency mitigation. Direct billing with all major homeowner and commercial insurance carriers.</p>
        <div class="trust-grid">
            <div class="trust-item">✓ IICRC Certified Master Technicians</div>
            <div class="trust-item">✓ 100% Direct Insurance Billing</div>
            <div class="trust-item">✓ Psychrometric Moisture Guarantee</div>
        </div>
    </header>

    <main class="main-container" id="quoteSection">
        <div class="form-card">
            <div class="form-header">
                <h2>Request a Restoration Quote & Emergency Mitigation</h2>
                <p>Complete the intake form below for immediate dispatch or an on-site structural damage assessment.</p>
            </div>

            <div id="statusAlert" class="alert-box"></div>

            <form id="quoteForm">
                <label>Select Primary Damage Category *</label>
                <div class="service-picker">
                    <div class="service-opt selected" onclick="selectService('water', this)">
                        <span>💧</span>
                        <p>Water Damage</p>
                    </div>
                    <div class="service-opt" onclick="selectService('fire', this)">
                        <span>🔥</span>
                        <p>Fire & Smoke</p>
                    </div>
                    <div class="service-opt" onclick="selectService('mold', this)">
                        <span>🦠</span>
                        <p>Mold Remediation</p>
                    </div>
                    <div class="service-opt" onclick="selectService('storm', this)">
                        <span>🌪️</span>
                        <p>Storm & Structural</p>
                    </div>
                    <div class="service-opt" onclick="selectService('reconstruction', this)">
                        <span>🔨</span>
                        <p>Reconstruction</p>
                    </div>
                    <div class="service-opt" onclick="selectService('commercial', this)">
                        <span>🏢</span>
                        <p>Commercial</p>
                    </div>
                </div>
                <input type="hidden" id="service_type" value="water">

                <div class="form-grid">
                    <div class="form-group">
                        <label for="full_name">Full Name / Property Owner *</label>
                        <input type="text" id="full_name" required placeholder="Jane Doe">
                    </div>
                    <div class="form-group">
                        <label for="phone">Direct Phone Number *</label>
                        <input type="tel" id="phone" required placeholder="(555) 000-0000">
                    </div>
                    <div class="form-group full">
                        <label for="email">Email Address *</label>
                        <input type="email" id="email" required placeholder="jane@example.com">
                    </div>
                    <div class="form-group full">
                        <label for="property_address">Loss Location / Property Address *</label>
                        <input type="text" id="property_address" required placeholder="123 Ocean Blvd, City, State, ZIP">
                    </div>
                    <div class="form-group">
                        <label for="urgency">Dispatch Urgency *</label>
                        <select id="urgency" required onchange="updateEstimator()">
                            <option value="emergency">🚨 Emergency (Immediate Dispatch Required)</option>
                            <option value="high">⚡ High (Within 24 Hours)</option>
                            <option value="standard" selected>📅 Standard (Schedule On-Site Inspection)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="insurance_carrier">Insurance Carrier (If Applicable)</label>
                        <input type="text" id="insurance_carrier" placeholder="State Farm, Allstate, Travelers...">
                    </div>
                    <div class="form-group full">
                        <label for="description">Scope of Damage & Affected Areas</label>
                        <textarea id="description" placeholder="Describe standing water depth, affected rooms (basement, kitchen, living room), visible soot/smoke, or origin of loss..."></textarea>
                    </div>
                </div>

                <button type="submit" id="submitBtn" class="btn-submit">🚨 Dispatch Emergency Response Team</button>
            </form>
        </div>

        <aside class="sidebar-card">
            <div class="calculator-widget">
                <div class="calc-title">📊 Estimated Mitigation Scope</div>
                <div class="slider-wrap">
                    <label><span>Affected Area Size:</span><span id="sqftDisplay">1,200 sq ft</span></label>
                    <input type="range" id="sqftSlider" min="100" max="10000" step="100" value="1200" oninput="updateEstimator()">
                </div>
                <div class="calc-result">
                    <div style="font-size:0.8rem; color:#64748b; margin-bottom:0.2rem;">Est. Structural Drying Window</div>
                    <div id="calcWindow" class="calc-result-val">3 - 5 Days</div>
                    <div style="font-size:0.75rem; color:#15803d; font-weight:600; margin-top:0.3rem;">✓ Direct Insurance Coverage Eligible</div>
                </div>
            </div>

            <div class="tracker-widget">
                <div class="calc-title">🔍 Track Existing Claim / Ref #</div>
                <p style="font-size:0.8rem; color:#64748b;">Enter your Lead ID or Claim Number to check crew dispatch status in real-time:</p>
                <div class="tracker-input-group">
                    <input type="text" id="trackRef" placeholder="Ref # (e.g. 101)">
                    <button type="button" onclick="lookupClaim()">Track</button>
                </div>
                <div id="trackResult" style="margin-top:0.75rem; font-size:0.85rem; display:none; padding:0.5rem; background:white; border-radius:6px; border:1px solid #cbd5e1;"></div>
            </div>
        </aside>
    </main>

    <script>
        function selectService(val, el) {
            document.querySelectorAll('.service-opt').forEach(x => x.classList.remove('selected'));
            el.classList.add('selected');
            document.getElementById('service_type').value = val;
            updateEstimator();
        }

        function updateEstimator() {
            const sqft = parseInt(document.getElementById('sqftSlider').value);
            document.getElementById('sqftDisplay').innerText = sqft.toLocaleString() + ' sq ft';
            const service = document.getElementById('service_type').value;
            const urgency = document.getElementById('urgency').value;
            
            let days = "3 - 5 Days";
            if (service === 'mold') days = "4 - 7 Days";
            else if (service === 'fire') days = "1 - 3 Weeks";
            else if (service === 'reconstruction') days = "2 - 6 Weeks";
            else if (sqft > 3000) days = "5 - 8 Days";
            
            document.getElementById('calcWindow').innerText = days;
        }

        function lookupClaim() {
            const ref = document.getElementById('trackRef').value.trim();
            const resEl = document.getElementById('trackResult');
            if (!ref) return;
            resEl.style.display = 'block';
            resEl.innerHTML = `<strong>Claim #${ref} Status:</strong><br><span style="color:#1e40af; font-weight:600;">Active / Triage In Progress</span><br><small style="color:#64748b;">Assigned Lead Tech: Emergency Unit #4</small>`;
        }

        document.getElementById('quoteForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const btn = document.getElementById('submitBtn');
            const alertBox = document.getElementById('statusAlert');
            btn.disabled = true;
            btn.innerText = 'Transmitting to Emergency Dispatch...';
            alertBox.style.display = 'none';

            const payload = {
                name: document.getElementById('full_name').value.trim(),
                phone: document.getElementById('phone').value.trim(),
                email: document.getElementById('email').value.trim(),
                address: document.getElementById('property_address').value.trim(),
                service_type: document.getElementById('service_type').value,
                urgency: document.getElementById('urgency').value,
                notes: `[Insurance: ${document.getElementById('insurance_carrier').value || 'None specified'}] ${document.getElementById('description').value.trim()}`,
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
                    alertBox.innerHTML = `
                        <h3 style="font-size:1.1rem; margin-bottom:0.3rem;">⚡ Emergency Request Dispatched!</h3>
                        <p>Your lead reference ID is <strong>#${data.lead_id || 'NEW'}</strong>. An on-call restoration project coordinator has received your incident report and is dispatching an emergency crew.</p>
                    `;
                    alertBox.style.display = 'block';
                    document.getElementById('quoteForm').reset();
                    btn.innerText = '✓ Dispatch Request Transmitted';
                    alertBox.scrollIntoView({ behavior: 'smooth' });
                } else {
                    alertBox.className = 'alert-box alert-error';
                    alertBox.innerHTML = `<strong>Dispatch Error:</strong> ${data.error || 'Please call our 24/7 emergency line directly.'}`;
                    alertBox.style.display = 'block';
                    btn.disabled = false;
                    btn.innerText = '🚨 Dispatch Emergency Response Team';
                }
            } catch (err) {
                alertBox.className = 'alert-box alert-error';
                alertBox.innerHTML = `<strong>Connection Error:</strong> Emergency server offline. Call (800) 555-RESTORE immediately.`;
                alertBox.style.display = 'block';
                btn.disabled = false;
                btn.innerText = '🚨 Dispatch Emergency Response Team';
            }
        });
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
    <title>Restoricon — Customer Restoration Portal</title>
    <style>
        :root {
            --primary: #1e3a8a;
            --primary-hover: #172554;
            --accent: #2563eb;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --success: #15803d;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        body { background: var(--bg); color: var(--text-main); line-height: 1.5; }

        .navbar {
            background: #0f172a;
            color: white;
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .brand { font-size: 1.25rem; font-weight: 800; color: #60a5fa; }
        .btn-logout { background: #334155; color: white; border: none; padding: 0.4rem 0.9rem; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 600; }
        .btn-logout:hover { background: #475569; }

        .container { max-width: 1000px; margin: 2rem auto; padding: 0 1rem; }

        .status-hero {
            background: white;
            border-radius: 16px;
            border: 1px solid var(--border);
            padding: 2rem;
            margin-bottom: 2rem;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05);
        }
        .status-hero-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem; }
        .property-title { font-size: 1.4rem; font-weight: 800; color: #0f172a; }
        .status-pill { background: #dbeafe; color: #1e40af; padding: 0.35rem 0.85rem; border-radius: 9999px; font-weight: 700; font-size: 0.85rem; }

        .stepper { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.5rem; margin-top: 1.5rem; }
        .step-item { text-align: center; }
        .step-bar { height: 6px; background: #e2e8f0; border-radius: 9999px; margin-bottom: 0.5rem; }
        .step-item.active .step-bar { background: #2563eb; }
        .step-item.completed .step-bar { background: #16a34a; }
        .step-label { font-size: 0.75rem; font-weight: 600; color: #64748b; }
        .step-item.active .step-label { color: #1e40af; font-weight: 700; }

        .portal-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
        .card { background: white; border-radius: 16px; border: 1px solid var(--border); padding: 1.75rem; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
        .card-full { grid-column: 1 / -1; }
        .card-header { font-size: 1.15rem; font-weight: 700; margin-bottom: 1.25rem; color: #0f172a; display: flex; justify-content: space-between; align-items: center; }

        .item-row { display: flex; justify-content: space-between; align-items: center; padding: 0.85rem 0; border-bottom: 1px solid #f1f5f9; }
        .item-row:last-child { border-bottom: none; }
        .item-title { font-weight: 600; font-size: 0.95rem; }
        .item-subtitle { font-size: 0.8rem; color: #64748b; margin-top: 0.2rem; }

        .btn-sign { background: #2563eb; color: white; border: none; padding: 0.45rem 0.9rem; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 0.85rem; }
        .btn-sign:hover { background: #1d4ed8; }

        .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: none; align-items: center; justify-content: center; z-index: 100; padding: 1rem; }
        .modal-card { background: white; border-radius: 16px; max-width: 500px; width: 100%; padding: 2rem; box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.3); }
        .sig-canvas { border: 2px dashed #cbd5e1; border-radius: 8px; width: 100%; height: 160px; background: #f8fafc; cursor: crosshair; }
        .modal-actions { display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.25rem; }

        @media (max-width: 768px) {
            .portal-grid { grid-template-columns: 1fr; }
            .stepper { grid-template-columns: 1fr 1fr; gap: 1rem; }
        }
    </style>
</head>
<body>
    <div class="navbar">
        <div class="brand">⚡ Restoricon — Your Restoration Portal</div>
        <button class="btn-logout" onclick="logout()">Sign Out</button>
    </div>

    <div class="container">
        <div class="status-hero">
            <div class="status-hero-top">
                <div>
                    <div class="property-title" id="projTitle">Property Restoration Job #101</div>
                    <div style="font-size:0.9rem; color:#64748b;" id="projAddress">123 Ocean Blvd — Water Extraction & Dehumidification</div>
                </div>
                <span class="status-pill" id="projStatus">Phase 3: Structural Drying</span>
            </div>

            <div class="stepper">
                <div class="step-item completed">
                    <div class="step-bar"></div>
                    <div class="step-label">1. Triage & Dispatch</div>
                </div>
                <div class="step-item completed">
                    <div class="step-bar"></div>
                    <div class="step-label">2. Water Extraction</div>
                </div>
                <div class="step-item active">
                    <div class="step-bar"></div>
                    <div class="step-label">3. Structural Drying</div>
                </div>
                <div class="step-item">
                    <div class="step-bar"></div>
                    <div class="step-label">4. Antimicrobial</div>
                </div>
                <div class="step-item">
                    <div class="step-bar"></div>
                    <div class="step-label">5. Reconstruction</div>
                </div>
            </div>
        </div>

        <div class="portal-grid">
            <div class="card">
                <div class="card-header">
                    <span>Contracts Requiring Signature</span>
                </div>
                <div id="contractsList">Loading service agreements...</div>
            </div>

            <div class="card">
                <div class="card-header">
                    <span>Invoices & Direct Billing</span>
                </div>
                <div id="invoicesList">Loading invoice details...</div>
            </div>

            <div class="card card-full">
                <div class="card-header">
                    <span>Direct Message with Project Manager</span>
                </div>
                <div id="msgThread" style="height: 140px; overflow-y: auto; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:0.75rem; font-size:0.85rem; margin-bottom:0.75rem;">
                    <div style="margin-bottom:0.4rem;"><strong>Dispatch Team:</strong> Moisture sensors deployed in basement. Target relative humidity 35%.</div>
                </div>
                <div style="display:flex; gap:0.5rem;">
                    <input type="text" id="chatMsg" placeholder="Send a message to your assigned restoration lead..." style="flex:1; padding:0.6rem 0.8rem; border:1px solid #cbd5e1; border-radius:6px; font-size:0.9rem;">
                    <button type="button" class="btn-sign" onclick="sendMessage()">Send</button>
                </div>
            </div>
        </div>
    </div>

    <!-- E-Sign Modal -->
    <div id="signModal" class="modal-overlay">
        <div class="modal-card">
            <h3 style="font-size:1.2rem; font-weight:700; margin-bottom:0.5rem;" id="signModalTitle">Authorize Work Agreement</h3>
            <p style="font-size:0.85rem; color:#64748b; margin-bottom:1rem;">Draw your digital signature below to authorize structural mitigation and direct insurance billing.</p>
            <canvas id="sigCanvas" class="sig-canvas"></canvas>
            <div class="modal-actions">
                <button type="button" style="background:#e2e8f0; border:none; padding:0.5rem 1rem; border-radius:6px; cursor:pointer;" onclick="clearCanvas()">Clear</button>
                <button type="button" style="background:#e2e8f0; border:none; padding:0.5rem 1rem; border-radius:6px; cursor:pointer;" onclick="closeModal()">Cancel</button>
                <button type="button" class="btn-sign" onclick="submitSignature()">Submit E-Signature</button>
            </div>
        </div>
    </div>

    <script>
        const token = localStorage.getItem('restoricon_token');
        if (!token) { window.location.href = '/portal/login'; }

        let activeContractId = null;
        let isDrawing = false;
        const canvas = document.getElementById('sigCanvas');
        const ctx = canvas.getContext('2d');

        function setupCanvas() {
            canvas.width = canvas.parentElement.clientWidth - 64;
            canvas.height = 160;
            ctx.strokeStyle = '#0f172a';
            ctx.lineWidth = 2.5;
            ctx.lineCap = 'round';

            canvas.addEventListener('mousedown', (e) => { isDrawing = true; ctx.beginPath(); ctx.moveTo(e.offsetX, e.offsetY); });
            canvas.addEventListener('mousemove', (e) => { if (isDrawing) { ctx.lineTo(e.offsetX, e.offsetY); ctx.stroke(); } });
            canvas.addEventListener('mouseup', () => { isDrawing = false; });
            canvas.addEventListener('touchstart', (e) => {
                const r = canvas.getBoundingClientRect();
                isDrawing = true; ctx.beginPath(); ctx.moveTo(e.touches[0].clientX - r.left, e.touches[0].clientY - r.top);
            });
            canvas.addEventListener('touchmove', (e) => {
                if (isDrawing) {
                    const r = canvas.getBoundingClientRect();
                    ctx.lineTo(e.touches[0].clientX - r.left, e.touches[0].clientY - r.top); ctx.stroke();
                }
            });
            canvas.addEventListener('touchend', () => { isDrawing = false; });
        }

        function clearCanvas() { ctx.clearRect(0, 0, canvas.width, canvas.height); }
        function closeModal() { document.getElementById('signModal').style.display = 'none'; }
        function openSignModal(id, title) {
            activeContractId = id;
            document.getElementById('signModalTitle').innerText = 'Sign ' + title;
            document.getElementById('signModal').style.display = 'flex';
            setTimeout(setupCanvas, 50);
        }

        async function submitSignature() {
            try {
                const h = { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' };
                const res = await fetch(`/api/v1/contracts/${activeContractId}/sign`, {
                    method: 'POST',
                    headers: h,
                    body: JSON.stringify({ signature_data: canvas.toDataURL() })
                });
                alert('Agreement digitally signed and recorded in the audit ledger.');
                closeModal();
                loadPortalData();
            } catch (err) {
                alert('Failed to submit signature.');
            }
        }

        async function loadPortalData() {
            try {
                const h = { 'Authorization': 'Bearer ' + token };
                const resProj = await fetch('/api/v1/portal/projects', { headers: h });
                if (resProj.status === 401) { logout(); return; }
                const dataProj = await resProj.json();

                if (dataProj.projects && dataProj.projects.length > 0) {
                    const p = dataProj.projects[0];
                    document.getElementById('projTitle').innerText = p.title || p.name || 'Restoration Site';
                    document.getElementById('projAddress').innerText = p.address || 'Location on file';
                    document.getElementById('projStatus').innerText = p.status || 'Active';
                }

                const resContr = await fetch('/api/v1/portal/contracts', { headers: h });
                const dataContr = await resContr.json();
                const contrEl = document.getElementById('contractsList');
                if (dataContr.contracts && dataContr.contracts.length > 0) {
                    contrEl.innerHTML = dataContr.contracts.map(c => `
                        <div class="item-row">
                            <div>
                                <div class="item-title">${c.title || 'Work Authorization'}</div>
                                <div class="item-subtitle">Status: <strong>${c.status}</strong></div>
                            </div>
                            ${c.status === 'signed' ? '<span style="color:#15803d; font-weight:700; font-size:0.85rem;">✓ Signed</span>' : `<button class="btn-sign" onclick="openSignModal(${c.id}, '${c.title || 'Agreement'}')">E-Sign</button>`}
                        </div>
                    `).join('');
                } else {
                    contrEl.innerHTML = '<p style="color:#64748b; font-size:0.85rem;">All contracts are executed and on file.</p>';
                }

                const resInv = await fetch('/api/v1/portal/invoices', { headers: h });
                const dataInv = await resInv.json();
                const invEl = document.getElementById('invoicesList');
                if (dataInv.invoices && dataInv.invoices.length > 0) {
                    invEl.innerHTML = dataInv.invoices.map(i => `
                        <div class="item-row">
                            <div>
                                <div class="item-title">Invoice #${i.id} — $${(i.total_amount || 0).toLocaleString()}</div>
                                <div class="item-subtitle">Due: ${i.due_date || 'Net 30'} | Status: ${i.status}</div>
                            </div>
                            <span style="font-size:0.85rem; font-weight:700; color:#1e40af;">Direct Billed</span>
                        </div>
                    `).join('');
                } else {
                    invEl.innerHTML = '<p style="color:#64748b; font-size:0.85rem;">No open customer balances.</p>';
                }
            } catch (err) {
                console.error(err);
            }
        }

        function sendMessage() {
            const input = document.getElementById('chatMsg');
            const thread = document.getElementById('msgThread');
            if (!input.value.trim()) return;
            thread.innerHTML += `<div style="margin-bottom:0.4rem; color:#1e40af;"><strong>You:</strong> ${input.value}</div>`;
            input.value = '';
            thread.scrollTop = thread.scrollHeight;
        }

        function logout() {
            localStorage.removeItem('restoricon_token');
            window.location.href = '/portal/login';
        }

        loadPortalData();
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
    <title>Restoricon ERP — Operations & Dispatch Center</title>
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
            --accent: #2563eb;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        body { background: var(--bg); color: var(--text); display: flex; height: 100vh; overflow: hidden; }

        .sidebar { width: 260px; background: #0b0f19; color: white; display: flex; flex-direction: column; padding: 1.5rem 1rem; border-right: 1px solid #1e293b; }
        .brand { font-size: 1.3rem; font-weight: 800; color: #60a5fa; margin-bottom: 2rem; display: flex; align-items: center; gap: 0.5rem; letter-spacing: -0.02em; }
        .nav-item { padding: 0.75rem 1rem; border-radius: 8px; color: #94a3b8; font-size: 0.9rem; cursor: pointer; margin-bottom: 0.25rem; display: flex; align-items: center; gap: 0.6rem; transition: all 0.15s; }
        .nav-item.active, .nav-item:hover { background: #1e293b; color: white; font-weight: 600; }
        
        .main-content { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        .topbar { height: 64px; background: white; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; padding: 0 2rem; }
        .search-bar input { padding: 0.55rem 1rem; border: 1px solid var(--border); border-radius: 8px; width: 340px; font-size: 0.9rem; }
        .top-actions { display: flex; align-items: center; gap: 1rem; }
        .btn-action-top { background: var(--primary); color: white; border: none; padding: 0.5rem 1rem; border-radius: 6px; font-weight: 600; font-size: 0.85rem; cursor: pointer; }

        .dashboard-body { flex: 1; padding: 2rem; overflow-y: auto; }
        .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 1.25rem; margin-bottom: 2rem; }
        .kpi-card { background: white; padding: 1.5rem; border-radius: 12px; border: 1px solid var(--border); box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
        .kpi-title { font-size: 0.8rem; color: var(--muted); font-weight: 600; text-transform: uppercase; margin-bottom: 0.5rem; }
        .kpi-value { font-size: 1.75rem; font-weight: 800; color: #0f172a; }

        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .section-card { background: white; border-radius: 12px; border: 1px solid var(--border); padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
        .section-header { font-size: 1.15rem; font-weight: 700; margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center; }

        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 0.85rem 1rem; border-bottom: 1px solid var(--border); font-size: 0.9rem; }
        th { color: var(--muted); font-weight: 600; background: #f8fafc; font-size: 0.8rem; text-transform: uppercase; }
        .badge { padding: 0.25rem 0.55rem; border-radius: 4px; font-size: 0.75rem; font-weight: 700; }
        .badge-active { background: #dcfce7; color: #15803d; }
        .badge-new { background: #dbeafe; color: #1e40af; }
        .badge-danger { background: #fee2e2; color: #dc2626; }

        .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: none; align-items: center; justify-content: center; z-index: 100; }
        .modal-box { background: white; border-radius: 12px; max-width: 500px; width: 100%; padding: 2rem; }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="brand">⚡ Restoricon ERP</div>
        <div class="nav-item active" onclick="switchTab('overview', this)">📊 Overview</div>
        <div class="nav-item" onclick="switchTab('leads', this)">🎯 Leads & Pipeline</div>
        <div class="nav-item" onclick="switchTab('projects', this)">🏗️ Projects & Sites</div>
        <div class="nav-item" onclick="switchTab('finance', this)">💳 Invoices & Finance</div>
        <div class="nav-item" onclick="switchTab('equipment', this)">⚙️ Equipment Assets</div>
        <div class="nav-item" style="margin-top: auto;" onclick="logout()">🚪 Sign Out</div>
    </div>

    <div class="main-content">
        <div class="topbar">
            <div class="search-bar">
                <input type="text" placeholder="Search projects, claims, clients, equipment..." onkeyup="handleSearch(event)">
            </div>
            <div class="top-actions">
                <button class="btn-action-top" onclick="openNewLeadModal()">+ New Lead</button>
                <div style="font-weight:700; font-size:0.85rem; color:#1e3a8a;">Ish (Admin)</div>
            </div>
        </div>

        <div class="dashboard-body">
            <div class="kpi-grid">
                <div class="kpi-card"><div class="kpi-title">Gross Revenue (MTD)</div><div id="kpiRev" class="kpi-value">$142,850</div></div>
                <div class="kpi-card"><div class="kpi-title">Active Job Sites</div><div id="kpiProjects" class="kpi-value">12</div></div>
                <div class="kpi-card"><div class="kpi-title">Emergency Leads</div><div id="kpiLeads" class="kpi-value">5</div></div>
                <div class="kpi-card"><div class="kpi-title">Equipment Deployed</div><div id="kpiEquip" class="kpi-value">38 Units</div></div>
            </div>

            <!-- TAB 1: OVERVIEW -->
            <div id="tab-overview" class="tab-content active">
                <div class="section-card">
                    <div class="section-header">
                        <span>Active Restoration Job Sites</span>
                        <button class="btn-action-top" style="padding:0.35rem 0.75rem; font-size:0.8rem;" onclick="loadProjects()">Refresh</button>
                    </div>
                    <table>
                        <thead>
                            <tr><th>Site #</th><th>Job Name / Property</th><th>Service Type</th><th>Status</th><th>Contract Value</th></tr>
                        </thead>
                        <tbody id="overviewTable">
                            <tr><td colspan="5" style="text-align:center;">Loading operations data...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- TAB 2: LEADS -->
            <div id="tab-leads" class="tab-content">
                <div class="section-card">
                    <div class="section-header">
                        <span>Incoming Claims & Emergency Leads</span>
                        <button class="btn-action-top" onclick="openNewLeadModal()">+ Add Lead</button>
                    </div>
                    <table>
                        <thead>
                            <tr><th>ID</th><th>Client Name</th><th>Service</th><th>Urgency</th><th>Status</th><th>Action</th></tr>
                        </thead>
                        <tbody id="leadsTable">
                            <tr><td colspan="6" style="text-align:center;">Loading leads...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- TAB 3: PROJECTS -->
            <div id="tab-projects" class="tab-content">
                <div class="section-card">
                    <div class="section-header">
                        <span>All Restoration Projects</span>
                    </div>
                    <table>
                        <thead>
                            <tr><th>ID</th><th>Project Name</th><th>Status</th><th>Contract Total</th><th>Invoiced</th></tr>
                        </thead>
                        <tbody id="allProjectsTable">
                            <tr><td colspan="5" style="text-align:center;">Loading project list...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- TAB 4: FINANCE -->
            <div id="tab-finance" class="tab-content">
                <div class="section-card">
                    <div class="section-header">
                        <span>Accounts Receivable & Invoicing</span>
                    </div>
                    <table>
                        <thead>
                            <tr><th>Invoice #</th><th>Customer</th><th>Amount</th><th>Status</th><th>Due Date</th></tr>
                        </thead>
                        <tbody id="financeTable">
                            <tr><td colspan="5" style="text-align:center;">Loading financial transactions...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- TAB 5: EQUIPMENT -->
            <div id="tab-equipment" class="tab-content">
                <div class="section-card">
                    <div class="section-header">
                        <span>Mitigation Asset Inventory & Fleet</span>
                    </div>
                    <table>
                        <thead>
                            <tr><th>Asset Tag</th><th>Equipment Name</th><th>Category</th><th>Deployment Status</th></tr>
                        </thead>
                        <tbody id="equipTable">
                            <tr><td>EQ-401</td><td>LGR 7000XLi Dehumidifier</td><td>Dehumidifier</td><td><span class="badge badge-active">On-Site (Site #101)</span></td></tr>
                            <tr><td>EQ-402</td><td>AirPath 360 Radial Air Mover</td><td>Air Mover</td><td><span class="badge badge-active">On-Site (Site #101)</span></td></tr>
                            <tr><td>EQ-403</td><td>HEPA 500 Air Scrubber</td><td>Air Scrubber</td><td><span class="badge badge-new">Available in Shop</span></td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- New Lead Modal -->
    <div id="leadModal" class="modal-overlay">
        <div class="modal-box">
            <h3 style="margin-bottom:1rem; font-size:1.2rem;">Add New Emergency Lead</h3>
            <form id="newLeadForm">
                <div style="margin-bottom:1rem;">
                    <label style="display:block; font-size:0.85rem; font-weight:600; margin-bottom:0.3rem;">Client Name</label>
                    <input type="text" id="modalLeadName" required style="width:100%; padding:0.6rem; border:1px solid #cbd5e1; border-radius:6px;">
                </div>
                <div style="margin-bottom:1rem;">
                    <label style="display:block; font-size:0.85rem; font-weight:600; margin-bottom:0.3rem;">Phone</label>
                    <input type="tel" id="modalLeadPhone" required style="width:100%; padding:0.6rem; border:1px solid #cbd5e1; border-radius:6px;">
                </div>
                <div style="margin-bottom:1rem;">
                    <label style="display:block; font-size:0.85rem; font-weight:600; margin-bottom:0.3rem;">Service Type</label>
                    <select id="modalLeadService" style="width:100%; padding:0.6rem; border:1px solid #cbd5e1; border-radius:6px;">
                        <option value="water">Water Damage</option>
                        <option value="fire">Fire Damage</option>
                        <option value="mold">Mold Remediation</option>
                    </select>
                </div>
                <div style="display:flex; justify-content:flex-end; gap:0.5rem; margin-top:1.5rem;">
                    <button type="button" onclick="document.getElementById('leadModal').style.display='none'" style="background:#e2e8f0; border:none; padding:0.5rem 1rem; border-radius:6px; cursor:pointer;">Cancel</button>
                    <button type="submit" class="btn-action-top">Create Lead</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        const token = localStorage.getItem('restoricon_token');
        if (!token) { window.location.href = '/admin/login'; }
        const h = { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' };

        function switchTab(tabId, el) {
            document.querySelectorAll('.nav-item').forEach(x => x.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(x => x.classList.remove('active'));
            el.classList.add('active');
            document.getElementById('tab-' + tabId).classList.add('active');
            if (tabId === 'leads') loadLeads();
            if (tabId === 'projects') loadProjects();
            if (tabId === 'finance') loadFinance();
        }

        async function loadOverview() {
            try {
                const res = await fetch('/api/v1/projects?limit=5', { headers: h });
                if (res.status === 401) { logout(); return; }
                const data = await res.json();
                const tbody = document.getElementById('overviewTable');
                if (data.projects && data.projects.length > 0) {
                    tbody.innerHTML = data.projects.map(p => `
                        <tr>
                            <td>#${p.id}</td>
                            <td><strong>${p.title || p.name || 'Restoration Site'}</strong></td>
                            <td>Water Extraction</td>
                            <td><span class="badge badge-active">${p.status}</span></td>
                            <td>$${(p.contract_amount || 0).toLocaleString()}</td>
                        </tr>
                    `).join('');
                } else {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;">No active projects recorded.</td></tr>';
                }
            } catch (err) { console.error(err); }
        }

        async function loadLeads() {
            try {
                const res = await fetch('/api/v1/leads', { headers: h });
                const data = await res.json();
                const tbody = document.getElementById('leadsTable');
                if (data.leads && data.leads.length > 0) {
                    tbody.innerHTML = data.leads.map(l => `
                        <tr>
                            <td>#${l.id}</td>
                            <td><strong>${l.name || l.contact_name || 'Prospect'}</strong></td>
                            <td>${l.service_type || 'General'}</td>
                            <td><span class="badge badge-danger">${l.urgency || 'High'}</span></td>
                            <td><span class="badge badge-new">${l.status}</span></td>
                            <td><button class="btn-action-top" style="padding:0.25rem 0.6rem; font-size:0.75rem;">Convert to Job</button></td>
                        </tr>
                    `).join('');
                } else {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">No leads found.</td></tr>';
                }
            } catch (err) { console.error(err); }
        }

        async function loadProjects() {
            try {
                const res = await fetch('/api/v1/projects', { headers: h });
                const data = await res.json();
                const tbody = document.getElementById('allProjectsTable');
                if (data.projects && data.projects.length > 0) {
                    tbody.innerHTML = data.projects.map(p => `
                        <tr>
                            <td>#${p.id}</td>
                            <td><strong>${p.title || p.name}</strong></td>
                            <td><span class="badge badge-active">${p.status}</span></td>
                            <td>$${(p.contract_amount || 0).toLocaleString()}</td>
                            <td>$${(p.invoiced_amount || 0).toLocaleString()}</td>
                        </tr>
                    `).join('');
                } else {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;">No projects found.</td></tr>';
                }
            } catch (err) { console.error(err); }
        }

        async function loadFinance() {
            try {
                const res = await fetch('/api/v1/invoices', { headers: h });
                const data = await res.json();
                const tbody = document.getElementById('financeTable');
                if (data.invoices && data.invoices.length > 0) {
                    tbody.innerHTML = data.invoices.map(i => `
                        <tr>
                            <td>#${i.id}</td>
                            <td>Customer #${i.customer_id}</td>
                            <td><strong>$${(i.total_amount || 0).toLocaleString()}</strong></td>
                            <td><span class="badge badge-new">${i.status}</span></td>
                            <td>${i.due_date || 'Net 30'}</td>
                        </tr>
                    `).join('');
                } else {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;">No invoices found.</td></tr>';
                }
            } catch (err) { console.error(err); }
        }

        function openNewLeadModal() {
            document.getElementById('leadModal').style.display = 'flex';
        }

        document.getElementById('newLeadForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const payload = {
                name: document.getElementById('modalLeadName').value,
                phone: document.getElementById('modalLeadPhone').value,
                service_type: document.getElementById('modalLeadService').value,
                status: 'new'
            };
            try {
                await fetch('/api/v1/leads', { method: 'POST', headers: h, body: JSON.stringify(payload) });
                document.getElementById('leadModal').style.display = 'none';
                loadLeads();
            } catch (err) { alert('Failed to create lead'); }
        });

        function logout() {
            localStorage.removeItem('restoricon_token');
            window.location.href = '/admin/login';
        }

        loadOverview();
    </script>
</body>
</html>"""
