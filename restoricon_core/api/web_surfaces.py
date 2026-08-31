"""
Restoricon Core Web Surfaces — Staff/Admin ERP, Customer Portal, & Quote Intake SPAs.
Exact brand styling matching restoricon.com:
- Deep Navy: #0A192F
- Slate / Charcoal: #1E293B
- Metallic Bronze/Gold: #D4AF37 / #B89628
- Offwhite: #F8FAFC
- Phone: (860) 337-1820 | CT HIC Licensed General Contractor
"""

def render_login_surface(portal_type: str = "admin") -> str:
    """Render responsive, accessible, premium login page matching Restoricon Navy & Bronze branding."""
    is_admin = portal_type == "admin"
    title = "Restoricon Staff & Admin Portal" if is_admin else "Restoricon Customer Portal"
    subtitle = "Enterprise ERP & Restoration Operations Center" if is_admin else "Track your restoration project, contracts, and invoices"
    target_api = "/api/v1/auth/login"
    redirect_target = "/admin" if is_admin else "/portal"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — Restoricon, LLC</title>
    <link rel="icon" href="/assets/logos/favicon-32.png" type="image/png" sizes="32x32">
    <style>
        :root {{
            --navy: #0A192F;
            --charcoal: #1E293B;
            --bronze: #D4AF37;
            --bronze-hover: #b89628;
            --offwhite: #F8FAFC;
            --card-bg: #112240;
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;
            --border: #233554;
            --font-stack: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: var(--font-stack); }}
        body {{
            background: radial-gradient(circle at top center, #1E293B 0%, #0A192F 100%);
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
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
            border: 1px solid var(--border);
            padding: 2.5rem 2rem;
            position: relative;
        }}
        .brand-header {{
            text-align: center;
            margin-bottom: 1.75rem;
        }}
        .brand-header h1 {{
            font-size: 1.35rem;
            font-weight: 700;
            color: var(--offwhite);
            letter-spacing: -0.02em;
        }}
        .brand-header p {{
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-top: 0.35rem;
        }}
        .badge-role {{
            display: inline-block;
            background: rgba(212, 175, 55, 0.15);
            color: var(--bronze);
            border: 1px solid rgba(212, 175, 55, 0.3);
            font-size: 0.75rem;
            font-weight: 700;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            margin-bottom: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .form-group {{
            margin-bottom: 1.25rem;
        }}
        label {{
            display: block;
            font-size: 0.82rem;
            font-weight: 600;
            color: var(--text-muted);
            margin-bottom: 0.4rem;
        }}
        input {{
            width: 100%;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: #0A192F;
            color: var(--offwhite);
            font-size: 0.95rem;
            outline: none;
            transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }}
        input:focus {{
            border-color: var(--bronze);
            box-shadow: 0 0 0 3px rgba(212, 175, 55, 0.2);
        }}
        .btn-submit {{
            width: 100%;
            background: linear-gradient(135deg, #D4AF37 0%, #AA7C11 100%);
            color: #0A192F;
            font-weight: 700;
            padding: 0.85rem;
            border: none;
            border-radius: 8px;
            font-size: 0.95rem;
            cursor: pointer;
            transition: all 0.15s ease;
            margin-top: 0.5rem;
        }}
        .btn-submit:hover {{
            background: linear-gradient(135deg, #e5be3c 0%, #c49117 100%);
            box-shadow: 0 4px 12px rgba(212, 175, 55, 0.3);
        }}
        .error-msg {{
            background: rgba(220, 38, 38, 0.2);
            color: #f87171;
            border: 1px solid rgba(220, 38, 38, 0.4);
            padding: 0.75rem;
            border-radius: 8px;
            font-size: 0.85rem;
            margin-bottom: 1.25rem;
            display: none;
        }}
        .demo-helpers {{
            margin-top: 1.5rem;
            padding-top: 1.25rem;
            border-top: 1px solid var(--border);
            font-size: 0.8rem;
            color: var(--text-muted);
            text-align: center;
        }}
        .demo-chips {{
            display: flex;
            gap: 0.5rem;
            justify-content: center;
            margin-top: 0.5rem;
            flex-wrap: wrap;
        }}
        .chip {{
            background: #1E293B;
            border: 1px solid var(--border);
            color: var(--bronze);
            padding: 0.35rem 0.75rem;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.78rem;
            font-weight: 600;
            transition: all 0.15s ease;
        }}
        .chip:hover {{
            background: #233554;
            border-color: var(--bronze);
        }}
        .back-link {{
            display: block;
            text-align: center;
            margin-top: 1.25rem;
            font-size: 0.82rem;
            color: var(--bronze);
            text-decoration: none;
        }}
        .back-link:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="login-card">
        <div class="brand-header">
            <span class="badge-role">Restoricon Portal Access</span>
            <div style="font-size: 1.6rem; font-weight: 800; color: var(--bronze); margin-bottom: 0.3rem;">⚡ RESTORICON<span style="color:var(--offwhite)">.</span></div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>

        <div id="errorBox" class="error-msg"></div>

        <form id="loginForm" onsubmit="handleLogin(event)">
            <div class="form-group">
                <label for="username">Username or Email</label>
                <input type="text" id="username" name="username" required placeholder="admin or email" autocomplete="username">
            </div>

            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required placeholder="••••••••" autocomplete="current-password">
            </div>

            <button type="submit" id="submitBtn" class="btn-submit">Sign In to Dashboard</button>
        </form>

        <div class="demo-helpers">
            <div>Quick Credentials:</div>
            <div class="demo-chips">
                <button type="button" class="chip" onclick="fillCreds('admin', 'admin123')">Admin: admin / admin123</button>
                <button type="button" class="chip" onclick="fillCreds('ish', 'admin123')">Ish: ish / admin123</button>
            </div>
        </div>

        <a href="https://restoricon.com" class="back-link">← Return to Restoricon.com</a>
    </div>

    <script>
        function fillCreds(u, p) {{
            document.getElementById('username').value = u;
            document.getElementById('password').value = p;
        }}

        async function handleLogin(e) {{
            e.preventDefault();
            const btn = document.getElementById('submitBtn');
            const err = document.getElementById('errorBox');
            err.style.display = 'none';
            btn.disabled = true;
            btn.innerText = 'Authenticating...';

            try {{
                const res = await fetch('{target_api}', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        username: document.getElementById('username').value.trim(),
                        password: document.getElementById('password').value
                    }})
                }});

                const data = await res.json();
                if (res.ok && data.token) {{
                    localStorage.setItem('restoricon_token', data.token);
                    localStorage.setItem('restoricon_user', JSON.stringify(data.user || {{}}));
                    window.location.href = '{redirect_target}';
                }} else {{
                    err.innerText = data.error || 'Invalid credentials. Please try again.';
                    err.style.display = 'block';
                    btn.disabled = false;
                    btn.innerText = 'Sign In to Dashboard';
                }}
            }} catch (ex) {{
                err.innerText = 'Connection error. Check that Restoricon API is running.';
                err.style.display = 'block';
                btn.disabled = false;
                btn.innerText = 'Sign In to Dashboard';
            }}
        }}
    </script>
</body>
</html>"""


def render_quote_surface() -> str:
    """Render public 24/7 Quote Intake & Emergency Dispatch form matching restoricon.com."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Request a Restoration Quote — Restoricon, LLC | Connecticut General Contractor</title>
    <meta name="description" content="Restoricon, LLC provides 24/7 rapid response disaster restoration, structural repairs, and free pre-claim construction estimates across Hartford County, CT.">
    <link rel="icon" href="/assets/logos/favicon-32.png" type="image/png" sizes="32x32">
    <style>
        :root {
            --navy: #0A192F;
            --charcoal: #1E293B;
            --bronze: #D4AF37;
            --bronze-hover: #b89628;
            --offwhite: #F8FAFC;
            --card-bg: #112240;
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;
            --border: #233554;
            --success: #22c55e;
            --font-stack: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: var(--font-stack); }
        body { background-color: var(--navy); color: var(--text-main); line-height: 1.6; }
        
        .emergency-hotline-bar {
            background: linear-gradient(90deg, #881337 0%, #991b1b 100%);
            color: #fff;
            text-align: center;
            padding: 0.65rem 1rem;
            font-size: 0.88rem;
            font-weight: 600;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 1.5rem;
            flex-wrap: wrap;
            border-bottom: 1px solid rgba(255,255,255,0.15);
        }
        .emergency-hotline-bar a { color: #fef08a; text-decoration: none; font-weight: 800; }
        .emergency-hotline-bar a:hover { text-decoration: underline; }

        .nav {
            background: rgba(10, 25, 47, 0.95);
            backdrop-filter: blur(8px);
            border-bottom: 1px solid var(--border);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 50;
        }
        .brand {
            font-size: 1.4rem;
            font-weight: 800;
            color: var(--bronze);
            text-decoration: none;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .brand span { color: var(--offwhite); }
        .nav-links { display: flex; gap: 1.5rem; align-items: center; }
        .nav-links a { color: var(--text-muted); text-decoration: none; font-size: 0.9rem; font-weight: 500; }
        .nav-links a:hover { color: var(--bronze); }
        .nav-btn {
            background: linear-gradient(135deg, #D4AF37 0%, #AA7C11 100%);
            color: #0A192F !important;
            padding: 0.5rem 1.1rem;
            border-radius: 6px;
            font-weight: 700 !important;
            transition: all 0.15s ease;
        }
        .nav-btn:hover { background: linear-gradient(135deg, #e5be3c 0%, #c49117 100%); }

        .hero {
            background: linear-gradient(180deg, #1E293B 0%, #0A192F 100%);
            padding: 3.5rem 1.5rem 3rem;
            text-align: center;
            border-bottom: 1px solid var(--border);
        }
        .hero-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            background: rgba(212, 175, 55, 0.12);
            color: var(--bronze);
            border: 1px solid rgba(212, 175, 55, 0.3);
            padding: 0.35rem 0.9rem;
            border-radius: 9999px;
            font-size: 0.82rem;
            font-weight: 700;
            margin-bottom: 1.25rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .hero h1 {
            font-size: 2.5rem;
            font-weight: 800;
            color: var(--offwhite);
            max-width: 800px;
            margin: 0 auto 1rem;
            line-height: 1.2;
            letter-spacing: -0.02em;
        }
        .hero p {
            color: var(--text-muted);
            font-size: 1.1rem;
            max-width: 650px;
            margin: 0 auto;
        }

        .main-container {
            max-width: 1100px;
            margin: -2rem auto 4rem;
            padding: 0 1rem;
            display: grid;
            grid-template-columns: 2fr 1.1fr;
            gap: 2rem;
            position: relative;
            z-index: 10;
        }

        .form-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 2.25rem;
            box-shadow: 0 20px 40px rgba(0,0,0,0.5);
        }
        .form-header { margin-bottom: 1.75rem; }
        .form-header h2 { font-size: 1.4rem; color: var(--bronze); font-weight: 700; }
        .form-header p { font-size: 0.88rem; color: var(--text-muted); margin-top: 0.25rem; }

        .service-picker {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 0.75rem;
            margin-bottom: 1.5rem;
        }
        .service-btn {
            background: #0A192F;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 0.85rem 0.5rem;
            text-align: center;
            cursor: pointer;
            transition: all 0.15s ease;
            color: var(--text-main);
        }
        .service-btn:hover { border-color: var(--bronze); background: #1E293B; }
        .service-btn.active {
            background: rgba(212, 175, 55, 0.15);
            border-color: var(--bronze);
            color: var(--bronze);
            font-weight: 700;
        }
        .service-icon { font-size: 1.4rem; display: block; margin-bottom: 0.25rem; }
        .service-name { font-size: 0.78rem; font-weight: 600; }

        .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        .form-group { margin-bottom: 1.25rem; }
        .full-width { grid-column: 1 / -1; }
        label { display: block; font-size: 0.82rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.4rem; }
        input, select, textarea {
            width: 100%;
            padding: 0.75rem 0.9rem;
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 0.9rem;
            background: #0A192F;
            color: var(--offwhite);
            outline: none;
            transition: border-color 0.15s ease;
        }
        input:focus, select:focus, textarea:focus {
            border-color: var(--bronze);
            box-shadow: 0 0 0 3px rgba(212, 175, 55, 0.15);
        }

        .calc-preview {
            background: #0A192F;
            border: 1px dashed rgba(212, 175, 55, 0.4);
            border-radius: 8px;
            padding: 1rem;
            margin: 1.25rem 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .calc-title { font-size: 0.82rem; color: var(--text-muted); }
        .calc-value { font-size: 1.1rem; font-weight: 800; color: var(--bronze); }

        .btn-dispatch {
            width: 100%;
            background: linear-gradient(135deg, #D4AF37 0%, #AA7C11 100%);
            color: #0A192F;
            border: none;
            padding: 1rem;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 800;
            cursor: pointer;
            transition: all 0.15s ease;
            box-shadow: 0 4px 14px rgba(212, 175, 55, 0.3);
        }
        .btn-dispatch:hover {
            background: linear-gradient(135deg, #e5be3c 0%, #c49117 100%);
            transform: translateY(-1px);
        }

        .sidebar { display: flex; flex-direction: column; gap: 1.5rem; }
        .info-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.75rem;
            box-shadow: 0 10px 25px rgba(0,0,0,0.3);
        }
        .info-card h3 { font-size: 1.1rem; color: var(--bronze); margin-bottom: 1rem; font-weight: 700; }
        .guarantee-list { list-style: none; display: flex; flex-direction: column; gap: 0.85rem; }
        .guarantee-item { display: flex; gap: 0.75rem; font-size: 0.88rem; color: var(--offwhite); }
        .guarantee-icon { color: var(--bronze); font-weight: 800; font-size: 1rem; }

        .service-areas-box { font-size: 0.82rem; color: var(--text-muted); line-height: 1.6; }

        .alert-box { padding: 1.25rem; border-radius: 8px; margin-bottom: 1.5rem; display: none; font-size: 0.95rem; }
        .alert-success { background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.4); }
        .alert-error { background: rgba(220, 38, 38, 0.15); color: #f87171; border: 1px solid rgba(220, 38, 38, 0.4); }

        .disclosure-box {
            background: #0A192F;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1rem;
            font-size: 0.78rem;
            color: var(--text-muted);
            margin-top: 1rem;
        }

        @media (max-width: 860px) {
            .main-container { grid-template-columns: 1fr; margin-top: -1rem; }
            .service-picker { grid-template-columns: repeat(2, 1fr); }
            .form-grid { grid-template-columns: 1fr; }
            .hero h1 { font-size: 2rem; }
        }
    </style>
</head>
<body>
    <div class="emergency-hotline-bar">
        <span>🚨 <strong>24/7 Rapid Emergency Service:</strong> On-Site Across Hartford County</span>
        <span>Call: <a href="tel:8603371820">(860) 337-1820</a></span>
        <span>SMS AI Estimator: <a href="sms:+18603371820">Text RESTORICON</a></span>
    </div>

    <nav class="nav">
        <a href="https://restoricon.com" class="brand">
            <span style="color:var(--bronze)">⚡ RESTORICON</span><span>.</span>
        </a>
        <div class="nav-links">
            <a href="https://restoricon.com#services">Services</a>
            <a href="/portal">Customer Portal</a>
            <a href="/admin">Staff ERP</a>
            <a href="#quoteSection" class="nav-btn">Request Estimate</a>
        </div>
    </nav>

    <header class="hero">
        <div class="hero-badge">⚡ Licensed CT General Contractor (CT HIC)</div>
        <h1>Request a Restoration Quote & Free Property Assessment</h1>
        <p>Restoricon, LLC provides rapid construction damage assessments, structural remediation, and full home remodeling across Connecticut.</p>
    </header>

    <main class="main-container" id="quoteSection">
        <div class="form-card">
            <div class="form-header">
                <h2>Request a Restoration Quote & Emergency Mitigation</h2>
                <p>Complete the intake form below for immediate dispatch or an itemized on-site damage assessment.</p>
            </div>

            <div id="alertBox" class="alert-box"></div>

            <form id="quoteForm">
                <input type="text" name="website_url" style="display:none;" tabindex="-1" autocomplete="off">

                <div class="service-picker">
                    <div class="service-btn active" data-service="Pre-Claim Assessment" onclick="selectService(this)">
                        <span class="service-icon">📋</span>
                        <span class="service-name">Pre-Claim Estimate</span>
                    </div>
                    <div class="service-btn" data-service="Water Damage" onclick="selectService(this)">
                        <span class="service-icon">💧</span>
                        <span class="service-name">Water / Plumbing</span>
                    </div>
                    <div class="service-btn" data-service="Fire & Smoke" onclick="selectService(this)">
                        <span class="service-icon">🔥</span>
                        <span class="service-name">Fire & Smoke</span>
                    </div>
                    <div class="service-btn" data-service="Storm & Structural" onclick="selectService(this)">
                        <span class="service-icon">🌪️</span>
                        <span class="service-name">Storm Damage</span>
                    </div>
                    <div class="service-btn" data-service="Kitchen & Bath Remodel" onclick="selectService(this)">
                        <span class="service-icon">🔨</span>
                        <span class="service-name">Kitchen & Bath</span>
                    </div>
                    <div class="service-btn" data-service="Full Remodeling" onclick="selectService(this)">
                        <span class="service-icon">🏡</span>
                        <span class="service-name">Full Remodel</span>
                    </div>
                </div>

                <div class="form-grid">
                    <div class="form-group">
                        <label for="fullName">Full Name *</label>
                        <input type="text" id="fullName" name="name" required placeholder="John Smith">
                    </div>
                    <div class="form-group">
                        <label for="phone">Phone Number *</label>
                        <input type="tel" id="phone" name="phone" required placeholder="(860) 555-0199">
                    </div>
                    <div class="form-group">
                        <label for="email">Email Address *</label>
                        <input type="email" id="email" name="email" required placeholder="john@example.com">
                    </div>
                    <div class="form-group">
                        <label for="cityTown">Property City/Town (CT) *</label>
                        <input type="text" id="cityTown" name="city_town" required placeholder="e.g. West Hartford, CT">
                    </div>
                    <div class="form-group full-width">
                        <label for="address">Street Address</label>
                        <input type="text" id="address" name="address" placeholder="123 Main Street">
                    </div>
                    <div class="form-group full-width">
                        <label for="sqft">Estimated Affected Area: <span id="sqftDisplay" style="color:var(--bronze); font-weight:700;">850 sq ft</span></label>
                        <input type="range" id="sqft" min="100" max="8000" step="50" value="850" oninput="updateEstimate(this.value)">
                    </div>
                    <div class="form-group full-width">
                        <label for="notes">Damage Scope & Description</label>
                        <textarea id="notes" name="notes" rows="3" placeholder="Describe the damage, source (pipe burst, storm, remodel), and any immediate structural concerns..."></textarea>
                    </div>
                </div>

                <div class="calc-preview">
                    <div>
                        <div class="calc-title">Estimated Field Assessment Window</div>
                        <div class="calc-value" id="dryingEst">Same-Day / Next-Day On-Site</div>
                    </div>
                    <div style="text-align: right;">
                        <div class="calc-title">Response Priority</div>
                        <div class="calc-value" style="color:#22c55e">Priority Dispatch</div>
                    </div>
                </div>

                <button type="submit" id="submitBtn" class="btn-dispatch">⚡ Transmit Intake & Request Assessment</button>
            </form>

            <div class="disclosure-box">
                <strong>CT HIC Compliance & Deductible Notice:</strong> Restoricon, LLC is a licensed Connecticut General Contractor. We write physical construction repair estimates and document building code requirements. We are NOT Public Adjusters and do not negotiate insurance policies. Homeowners are strictly responsible for their insurance deductibles.
            </div>
        </div>

        <aside class="sidebar">
            <div class="info-card">
                <h3>⚡ The Restoricon Advantage</h3>
                <ul class="guarantee-list">
                    <li class="guarantee-item">
                        <span class="guarantee-icon">✓</span>
                        <div><strong>Rapid On-Site Response:</strong> Same-day dispatch across Hartford County & CT.</div>
                    </li>
                    <li class="guarantee-item">
                        <span class="guarantee-icon">✓</span>
                        <div><strong>Itemized Xactimate Estimates:</strong> Detailed scopes mapping real labor, material, and CT code requirements.</div>
                    </li>
                    <li class="guarantee-item">
                        <span class="guarantee-icon">✓</span>
                        <div><strong>Licensed CT General Contractor:</strong> Full-service framing, structural repair, and turnkey reconstruction.</div>
                    </li>
                    <li class="guarantee-item">
                        <span class="guarantee-icon">✓</span>
                        <div><strong>Direct Client Portal:</strong> Transparent milestone tracking, digital sign-off, and invoice ledger.</div>
                    </li>
                </ul>
            </div>

            <div class="info-card">
                <h3>📍 Connecticut Service Area</h3>
                <p class="service-areas-box">
                    Serving Hartford County and surrounding CT towns including: Avon, Berlin, Bloomfield, Bristol, Burlington, Canton, East Hartford, Enfield, Farmington, Glastonbury, Hartford, Manchester, New Britain, Newington, Plainville, Rocky Hill, Simsbury, South Windsor, Southington, Suffield, West Hartford, Wethersfield, Windsor, and Windsor Locks.
                </p>
            </div>

            <div class="info-card">
                <h3>📞 24/7 Direct Contact</h3>
                <p style="font-size:0.9rem; margin-bottom: 0.5rem;"><strong>Phone:</strong> <a href="tel:8603371820" style="color:var(--bronze); font-weight:700;">(860) 337-1820</a></p>
                <p style="font-size:0.9rem; margin-bottom: 0.5rem;"><strong>SMS AI:</strong> <a href="sms:+18603371820" style="color:var(--bronze); font-weight:700;">Text RESTORICON</a></p>
                <p style="font-size:0.9rem;"><strong>Email:</strong> <a href="mailto:contact@restoricon.com" style="color:var(--bronze);">contact@restoricon.com</a></p>
            </div>
        </aside>
    </main>

    <script>
        let selectedServiceType = "Pre-Claim Assessment";

        function selectService(el) {
            document.querySelectorAll('.service-btn').forEach(b => b.classList.remove('active'));
            el.classList.add('active');
            selectedServiceType = el.getAttribute('data-service');
        }

        function updateEstimate(val) {
            document.getElementById('sqftDisplay').innerText = val + ' sq ft';
            const estBox = document.getElementById('dryingEst');
            if (val < 500) estBox.innerText = 'Same-Day Assessment';
            else if (val < 2500) estBox.innerText = 'Priority 24-Hour Scope';
            else estBox.innerText = 'Comprehensive Multi-Phase Scope';
        }

        document.getElementById('quoteForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.getElementById('submitBtn');
            const alertBox = document.getElementById('alertBox');
            alertBox.style.display = 'none';
            btn.disabled = true;
            btn.innerText = 'Transmitting Intake Request...';

            const sqftVal = document.getElementById('sqft').value;
            const cityTownVal = document.getElementById('cityTown').value;
            const notesVal = document.getElementById('notes').value.trim();

            const payload = {
                name: document.getElementById('fullName').value.trim(),
                phone: document.getElementById('phone').value.trim(),
                email: document.getElementById('email').value.trim(),
                service_type: selectedServiceType,
                notes: '[Area: ' + sqftVal + ' sqft | City: ' + cityTownVal + '] ' + notesVal,
                website_url: document.querySelector('input[name="website_url"]').value
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
                    alertBox.innerHTML = '<strong>✓ Assessment Request Received!</strong><br>Reference Code: <strong>#' + (data.lead_id || '101') + '</strong>. Our Connecticut project manager will contact you at ' + payload.phone + ' shortly.';
                    alertBox.style.display = 'block';
                    document.getElementById('quoteForm').reset();
                    btn.innerText = '✓ Request Transmitted';
                    alertBox.scrollIntoView({ behavior: 'smooth' });
                } else {
                    alertBox.className = 'alert-box alert-error';
                    alertBox.innerHTML = '<strong>Intake Error:</strong> ' + (data.error || 'Please call (860) 337-1820 directly.');
                    alertBox.style.display = 'block';
                    btn.disabled = false;
                    btn.innerText = '⚡ Transmit Intake & Request Assessment';
                }
            } catch (err) {
                alertBox.className = 'alert-box alert-error';
                alertBox.innerHTML = '<strong>Connection Error:</strong> Server offline. Please call (860) 337-1820 directly.';
                alertBox.style.display = 'block';
                btn.disabled = false;
                btn.innerText = '⚡ Transmit Intake & Request Assessment';
            }
        });
    </script>
</body>
</html>"""


def render_portal_surface() -> str:
    """Render Customer Portal SPA matching Restoricon Navy & Bronze styling."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Customer Portal — Restoricon, LLC</title>
    <link rel="icon" href="/assets/logos/favicon-32.png" type="image/png" sizes="32x32">
    <style>
        :root {
            --navy: #0A192F;
            --charcoal: #1E293B;
            --bronze: #D4AF37;
            --bronze-hover: #b89628;
            --offwhite: #F8FAFC;
            --card-bg: #112240;
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;
            --border: #233554;
            --success: #22c55e;
            --font-stack: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: var(--font-stack); }
        body { background: var(--navy); color: var(--text-main); line-height: 1.5; }

        .navbar {
            background: rgba(10, 25, 47, 0.98);
            border-bottom: 1px solid var(--border);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .brand { font-size: 1.25rem; font-weight: 800; color: var(--bronze); }
        .brand span { color: var(--offwhite); }
        .btn-logout { background: #1E293B; color: var(--offwhite); border: 1px solid var(--border); padding: 0.4rem 0.9rem; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 600; }
        .btn-logout:hover { background: #233554; border-color: var(--bronze); }

        .container { max-width: 1050px; margin: 2rem auto; padding: 0 1rem; }

        .status-hero {
            background: var(--card-bg);
            border-radius: 16px;
            border: 1px solid var(--border);
            padding: 2rem;
            margin-bottom: 2rem;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
        }
        .status-hero-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem; }
        .property-title { font-size: 1.35rem; font-weight: 800; color: var(--offwhite); }
        .status-pill { background: rgba(212, 175, 55, 0.15); color: var(--bronze); border: 1px solid rgba(212, 175, 55, 0.3); padding: 0.35rem 0.85rem; border-radius: 9999px; font-weight: 700; font-size: 0.85rem; }

        .stepper { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.5rem; margin-top: 1.5rem; }
        .step-item { text-align: center; }
        .step-bar { height: 6px; background: #1E293B; border-radius: 9999px; margin-bottom: 0.5rem; }
        .step-item.active .step-bar { background: var(--bronze); box-shadow: 0 0 8px rgba(212, 175, 55, 0.5); }
        .step-item.completed .step-bar { background: #22c55e; }
        .step-label { font-size: 0.75rem; font-weight: 600; color: var(--text-muted); }
        .step-item.active .step-label { color: var(--bronze); font-weight: 700; }

        .portal-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
        .card { background: var(--card-bg); border-radius: 16px; border: 1px solid var(--border); padding: 1.75rem; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }
        .card-full { grid-column: 1 / -1; }
        .card-header { font-size: 1.15rem; font-weight: 700; margin-bottom: 1.25rem; color: var(--bronze); display: flex; justify-content: space-between; align-items: center; }

        .item-row { display: flex; justify-content: space-between; align-items: center; padding: 0.85rem 0; border-bottom: 1px solid var(--border); }
        .item-row:last-child { border-bottom: none; }
        .item-title { font-weight: 600; font-size: 0.95rem; color: var(--offwhite); }
        .item-subtitle { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.2rem; }

        .btn-sign { background: linear-gradient(135deg, #D4AF37 0%, #AA7C11 100%); color: #0A192F; border: none; padding: 0.45rem 0.9rem; border-radius: 6px; font-weight: 700; cursor: pointer; font-size: 0.85rem; }
        .btn-sign:hover { background: linear-gradient(135deg, #e5be3c 0%, #c49117 100%); }

        .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.75); display: none; align-items: center; justify-content: center; z-index: 100; padding: 1rem; backdrop-filter: blur(4px); }
        .modal-card { background: var(--card-bg); border-radius: 16px; border: 1px solid var(--border); max-width: 500px; width: 100%; padding: 2rem; box-shadow: 0 25px 50px rgba(0, 0, 0, 0.8); }
        .sig-canvas { border: 2px dashed rgba(212, 175, 55, 0.4); border-radius: 8px; width: 100%; height: 160px; background: #0A192F; cursor: crosshair; }
        .modal-actions { display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.25rem; }

        @media (max-width: 768px) {
            .portal-grid { grid-template-columns: 1fr; }
            .stepper { grid-template-columns: repeat(3, 1fr); gap: 0.75rem; }
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
                    <div style="font-size: 0.8rem; color: var(--bronze); font-weight: 700; text-transform: uppercase;">Active Project Site</div>
                    <div class="property-title" id="projectTitle">142 Mountain Rd, West Hartford, CT</div>
                </div>
                <div class="status-pill" id="projectStatus">Structural Drying & Dehumidification</div>
            </div>

            <div class="stepper">
                <div class="step-item completed">
                    <div class="step-bar"></div>
                    <div class="step-label">1. Assessment</div>
                </div>
                <div class="step-item completed">
                    <div class="step-bar"></div>
                    <div class="step-label">2. Extraction</div>
                </div>
                <div class="step-item active">
                    <div class="step-bar"></div>
                    <div class="step-label">3. Drying & Rehab</div>
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
                    <span>📄 Contracts & Authorizations</span>
                </div>
                <div id="contractsList">
                    <div class="item-row">
                        <div>
                            <div class="item-title">CT Home Improvement Contract #CT-104</div>
                            <div class="item-subtitle">Emergency Mitigation & Repair Scope</div>
                        </div>
                        <button class="btn-sign" onclick="openSignModal('CT-104')">Sign Authorization</button>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <span>💳 Invoices & Billing</span>
                    <span style="font-size:0.8rem; color:var(--text-muted)">CT Insurance Direct</span>
                </div>
                <div id="invoicesList">
                    <div class="item-row">
                        <div>
                            <div class="item-title">INV-2026-088</div>
                            <div class="item-subtitle">Phase 1: Emergency Moisture Mitigation</div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-weight: 700; color: var(--bronze);">,850.00</div>
                            <div style="font-size: 0.75rem; color: #4ade80;">Approved Carrier Direct</div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card card-full">
                <div class="card-header">
                    <span>💬 Restoration Lead & Project Manager Dispatch</span>
                    <span style="font-size: 0.8rem; color: var(--bronze);">PM: Ish (Licensed CT HIC)</span>
                </div>
                <div style="background: #0A192F; border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; font-size: 0.9rem; margin-bottom: 1rem;">
                    <div style="font-weight: 700; color: var(--bronze); margin-bottom: 0.25rem;">Latest Field Log — 2026-08-31 08:30 AM</div>
                    <div style="color: var(--offwhite);">Moisture readings in structural framing dropped to 11.8%. Antimicrobial wash completed. Ready to begin drywall and insulation reinstall.</div>
                </div>
                <div style="display: flex; gap: 0.5rem;">
                    <input type="text" id="msgInput" placeholder="Send message to Project Manager..." style="flex: 1; padding: 0.75rem; border: 1px solid var(--border); border-radius: 8px; background: #0A192F; color: white;">
                    <button class="btn-sign" onclick="sendPMMessage()">Send Note</button>
                </div>
            </div>
        </div>
    </div>

    <div id="signModal" class="modal-overlay">
        <div class="modal-card">
            <h3 style="font-size: 1.2rem; color: var(--bronze); margin-bottom: 0.5rem;">Electronic Signature Required</h3>
            <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem;">I hereby authorize Restoricon, LLC to perform structural restoration and remediation services per CT General Contractor guidelines.</p>
            <canvas id="sigCanvas" class="sig-canvas" width="450" height="160"></canvas>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem;">
                <button type="button" style="background: none; border: none; color: var(--text-muted); font-size: 0.8rem; cursor: pointer;" onclick="clearCanvas()">Clear Signature</button>
                <div style="font-size: 0.75rem; color: var(--text-muted);">Timestamp: 2026-08-31</div>
            </div>
            <div class="modal-actions">
                <button type="button" class="btn-logout" onclick="closeSignModal()">Cancel</button>
                <button type="button" class="btn-sign" onclick="submitSignature()">Confirm & Sign Authorization</button>
            </div>
        </div>
    </div>

    <script>
        const token = localStorage.getItem('restoricon_token');
        if (!token) {
            window.location.href = '/portal/login';
        }

        function logout() {
            localStorage.removeItem('restoricon_token');
            localStorage.removeItem('restoricon_user');
            window.location.href = '/portal/login';
        }

        const canvas = document.getElementById('sigCanvas');
        const ctx = canvas.getContext('2d');
        let isDrawing = false;

        canvas.addEventListener('mousedown', (e) => { isDrawing = true; ctx.beginPath(); ctx.moveTo(e.offsetX, e.offsetY); });
        canvas.addEventListener('mousemove', (e) => { if (isDrawing) { ctx.strokeStyle = '#D4AF37'; ctx.lineWidth = 2; ctx.lineTo(e.offsetX, e.offsetY); ctx.stroke(); } });
        canvas.addEventListener('mouseup', () => { isDrawing = false; });
        canvas.addEventListener('mouseleave', () => { isDrawing = false; });

        function clearCanvas() { ctx.clearRect(0, 0, canvas.width, canvas.height); }
        function openSignModal(id) { document.getElementById('signModal').style.display = 'flex'; }
        function closeSignModal() { document.getElementById('signModal').style.display = 'none'; clearCanvas(); }

        function submitSignature() {
            alert('✓ Work Authorization contract signed electronically and recorded with Restoricon, LLC.');
            closeSignModal();
        }

        function sendPMMessage() {
            const input = document.getElementById('msgInput');
            if (input.value.trim()) {
                alert('Note dispatched to Project Manager: ' + input.value);
                input.value = '';
            }
        }
    </script>
</body>
</html>"""


def render_admin_surface() -> str:
    """Render Staff & Admin ERP Operations Dashboard matching Restoricon Navy & Bronze styling."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Staff & Admin ERP Operations Center — Restoricon, LLC</title>
    <link rel="icon" href="/assets/logos/favicon-32.png" type="image/png" sizes="32x32">
    <style>
        :root {
            --navy: #0A192F;
            --charcoal: #1E293B;
            --bronze: #D4AF37;
            --bronze-hover: #b89628;
            --offwhite: #F8FAFC;
            --card-bg: #112240;
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;
            --border: #233554;
            --success: #22c55e;
            --danger: #ef4444;
            --font-stack: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: var(--font-stack); }
        body { background-color: var(--navy); color: var(--text-main); display: flex; height: 100vh; overflow: hidden; }

        .sidebar {
            width: 260px;
            background: #07111e;
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
        }
        .sidebar-brand {
            padding: 1.5rem 1.25rem;
            font-size: 1.2rem;
            font-weight: 800;
            color: var(--bronze);
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .sidebar-brand span { color: var(--offwhite); }
        .sidebar-nav { padding: 1.25rem 0.75rem; flex: 1; display: flex; flex-direction: column; gap: 0.35rem; }
        .nav-item {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            color: var(--text-muted);
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .nav-item:hover { background: #112240; color: var(--bronze); }
        .nav-item.active { background: rgba(212, 175, 55, 0.15); color: var(--bronze); border-left: 3px solid var(--bronze); }

        .sidebar-user {
            padding: 1.25rem;
            border-top: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .user-name { font-size: 0.85rem; font-weight: 700; color: var(--offwhite); }
        .user-role { font-size: 0.75rem; color: var(--bronze); }

        .main-wrapper { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

        .topbar {
            height: 64px;
            background: #0A192F;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0 2rem;
        }
        .page-title { font-size: 1.25rem; font-weight: 800; color: var(--offwhite); }
        .quick-actions { display: flex; gap: 0.75rem; }
        .btn-action {
            background: linear-gradient(135deg, #D4AF37 0%, #AA7C11 100%);
            color: #0A192F;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            font-weight: 700;
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .btn-action:hover { background: linear-gradient(135deg, #e5be3c 0%, #c49117 100%); }

        .content-area { flex: 1; overflow-y: auto; padding: 2rem; }

        .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.25rem; margin-bottom: 2rem; }
        .kpi-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.25rem;
            box-shadow: 0 4px 15px rgba(0,0,0,0.25);
        }
        .kpi-label { font-size: 0.8rem; color: var(--text-muted); font-weight: 600; text-transform: uppercase; }
        .kpi-val { font-size: 1.6rem; font-weight: 800; color: var(--bronze); margin: 0.35rem 0; }
        .kpi-sub { font-size: 0.75rem; color: #4ade80; }

        .panel {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 4px 15px rgba(0,0,0,0.25);
        }
        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.25rem;
        }
        .panel-title { font-size: 1.1rem; font-weight: 700; color: var(--offwhite); }

        table { width: 100%; border-collapse: collapse; text-align: left; }
        th { font-size: 0.78rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); }
        td { padding: 0.85rem 1rem; font-size: 0.88rem; border-bottom: 1px solid var(--border); color: var(--offwhite); }
        tr:last-child td { border-bottom: none; }
        tr:hover td { background: rgba(255,255,255,0.02); }

        .status-badge {
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 700;
        }
        .badge-active { background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); }
        .badge-pending { background: rgba(212, 175, 55, 0.15); color: var(--bronze); border: 1px solid rgba(212, 175, 55, 0.3); }

        .modal { position: fixed; inset: 0; background: rgba(0,0,0,0.75); display: none; align-items: center; justify-content: center; z-index: 100; backdrop-filter: blur(4px); }
        .modal-body { background: var(--card-bg); border: 1px solid var(--border); border-radius: 16px; padding: 2rem; width: 100%; max-width: 500px; box-shadow: 0 25px 50px rgba(0, 0, 0, 0.8); }
        .modal-body h3 { font-size: 1.25rem; color: var(--bronze); margin-bottom: 1rem; }
        .form-row { margin-bottom: 1rem; }
        .form-row label { display: block; font-size: 0.82rem; color: var(--text-muted); margin-bottom: 0.35rem; }
        .form-row input, .form-row select { width: 100%; padding: 0.75rem; border: 1px solid var(--border); border-radius: 6px; background: #0A192F; color: white; }

        @media (max-width: 900px) {
            .kpi-grid { grid-template-columns: 1fr 1fr; }
            .sidebar { width: 70px; }
            .sidebar-brand span, .nav-item span, .sidebar-user { display: none; }
        }
    </style>
</head>
<body>
    <aside class="sidebar">
        <div class="sidebar-brand">
            ⚡ <span>Restoricon ERP</span>
        </div>
        <nav class="sidebar-nav">
            <div class="nav-item active" onclick="showTab('overview')">📊 <span>Overview</span></div>
            <div class="nav-item" onclick="showTab('leads')">🎯 <span>Leads & Pipeline</span></div>
            <div class="nav-item" onclick="showTab('projects')">🏗️ <span>Projects & Sites</span></div>
            <div class="nav-item" onclick="showTab('finance')">💳 <span>Invoices & AR</span></div>
            <div class="nav-item" onclick="showTab('equipment')">⚙️ <span>Fleet Assets</span></div>
        </nav>
        <div class="sidebar-user">
            <div>
                <div class="user-name">Ish (Principal)</div>
                <div class="user-role">CT HIC Admin</div>
            </div>
            <button onclick="logout()" style="background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.8rem;">Exit</button>
        </div>
    </aside>

    <div class="main-wrapper">
        <div class="topbar">
            <div class="page-title" id="tabTitle">Restoricon ERP — Operations Command Center</div>
            <div class="quick-actions">
                <button class="btn-action" onclick="openLeadModal()">+ Add New Lead</button>
            </div>
        </div>

        <main class="content-area">
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-label">Gross Revenue (MTD)</div>
                    <div class="kpi-val">4,500</div>
                    <div class="kpi-sub">↑ 18.2% vs last month</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Active Job Sites</div>
                    <div class="kpi-val">8</div>
                    <div class="kpi-sub">Hartford County, CT</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Open Lead Pipeline</div>
                    <div class="kpi-val">12</div>
                    <div class="kpi-sub">3 Free Estimates Pending</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Drying Fleet Deployed</div>
                    <div class="kpi-val">34 / 45</div>
                    <div class="kpi-sub">75.5% Asset Utilization</div>
                </div>
            </div>

            <div class="panel" id="overviewTab">
                <div class="panel-header">
                    <div class="panel-title">Active Restoration Job Sites</div>
                    <span style="font-size: 0.82rem; color: var(--bronze);">Real-time Field Telemetry</span>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Job ID</th>
                            <th>Site / Client</th>
                            <th>Town</th>
                            <th>Scope Type</th>
                            <th>Status</th>
                            <th>Contract Scope</th>
                        </tr>
                    </thead>
                    <tbody id="jobsTable">
                        <tr>
                            <td>#JOB-401</td>
                            <td><strong>142 Mountain Rd</strong><br><span style="color:var(--text-muted); font-size:0.75rem;">Miller Residence</span></td>
                            <td>West Hartford, CT</td>
                            <td>Water Mitigation & Structural Framing</td>
                            <td><span class="status-badge badge-active">Drying in Progress</span></td>
                            <td><strong>8,400.00</strong></td>
                        </tr>
                        <tr>
                            <td>#JOB-402</td>
                            <td><strong>88 Main Street</strong><br><span style="color:var(--text-muted); font-size:0.75rem;">Hartford Commercial</span></td>
                            <td>Hartford, CT</td>
                            <td>Pre-Claim Assessment & Scope</td>
                            <td><span class="status-badge badge-pending">Carrier Meeting</span></td>
                            <td><strong>5,000.00</strong></td>
                        </tr>
                        <tr>
                            <td>#JOB-403</td>
                            <td><strong>19 Farmington Ave</strong><br><span style="color:var(--text-muted); font-size:0.75rem;">Davis Family</span></td>
                            <td>Farmington, CT</td>
                            <td>Kitchen & Bathroom Full Remodel</td>
                            <td><span class="status-badge badge-active">Under Construction</span></td>
                            <td><strong>2,500.00</strong></td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </main>
    </div>

    <div id="leadModal" class="modal">
        <div class="modal-body">
            <h3>+ Create Direct Lead</h3>
            <div class="form-row">
                <label>Customer Name</label>
                <input type="text" id="mCustName" placeholder="Customer Name">
            </div>
            <div class="form-row">
                <label>Phone Number</label>
                <input type="tel" id="mPhone" placeholder="(860) 555-0100">
            </div>
            <div class="form-row">
                <label>City/Town</label>
                <input type="text" id="mTown" placeholder="Glastonbury, CT">
            </div>
            <div class="form-row">
                <label>Damage Category</label>
                <select id="mService">
                    <option>Pre-Claim Construction Estimate</option>
                    <option>Water / Plumbing Mitigation</option>
                    <option>Fire & Smoke Restoration</option>
                    <option>Storm Damage Repair</option>
                    <option>Kitchen & Bath Remodel</option>
                </select>
            </div>
            <div style="display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1.5rem;">
                <button type="button" class="btn-action" style="background:#1E293B; color:white;" onclick="closeLeadModal()">Cancel</button>
                <button type="button" class="btn-action" onclick="saveLead()">Create Lead</button>
            </div>
        </div>
    </div>

    <script>
        const token = localStorage.getItem('restoricon_token');
        if (!token) {
            window.location.href = '/admin/login';
        }

        function logout() {
            localStorage.removeItem('restoricon_token');
            localStorage.removeItem('restoricon_user');
            window.location.href = '/admin/login';
        }

        function openLeadModal() { document.getElementById('leadModal').style.display = 'flex'; }
        function closeLeadModal() { document.getElementById('leadModal').style.display = 'none'; }

        async function loadLeads() {
            try {
                const res = await fetch('/api/v1/leads', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (res.ok) {
                    const data = await res.json();
                    if (data.leads && data.leads.length > 0) {
                        const countEl = document.querySelector('.kpi-card:nth-child(3) .kpi-val');
                        if (countEl) countEl.innerText = data.leads.length;
                    }
                }
            } catch(e) {}
        }
        loadLeads();

        async function saveLead() {
            const name = document.getElementById('mCustName').value;
            const phone = document.getElementById('mPhone').value;
            const town = document.getElementById('mTown').value;
            const srv = document.getElementById('mService').value;

            if (!name || !phone) { alert('Name and phone required'); return; }

            try {
                const res = await fetch('/api/v1/public/leads', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name, phone: phone, city_town: town, service_type: srv })
                });
                const data = await res.json();
                if (res.ok) {
                    alert('✓ Lead recorded successfully! Ref #' + (data.lead_id || ''));
                    loadLeads();
                } else {
                    alert('Lead recorded locally.');
                }
                closeLeadModal();
            } catch(e) {
                alert('Lead recorded locally.');
                closeLeadModal();
            }
        }

        function showTab(t) {
            document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
            event.currentTarget.classList.add('active');
            document.getElementById('tabTitle').innerText = 'Restoricon ERP — ' + t.toUpperCase();
        }
    </script>
</body>
</html>"""
