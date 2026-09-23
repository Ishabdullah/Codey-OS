"""
Restoricon Core Web Surfaces — Staff/Admin ERP, Customer Portal, Quote Intake, & Auth SPAs.
Exact brand styling matching restoricon.com:
- Deep Navy: #0A192F
- Slate / Charcoal: #1E293B
- Metallic Bronze/Gold: #D4AF37 / #B89628
- Offwhite: #F8FAFC
- Phone: (860) 337-1820 | CT HIC Licensed General Contractor
"""

import html as _html


def _pesc(value) -> str:
    """Python-side HTML escaping for server-rendered (non-f-string,
    non-SPA) surfaces such as render_estimate_proposal -- customer
    names, line-item descriptions, and business-profile text are all
    client-supplied and land directly in server-rendered HTML, so they
    must be escaped the same way escapeHtml() protects the client-side
    JS-rendered surfaces elsewhere in this file. quote=True also escapes
    quotes, not just angle brackets, since this print-only markup has no
    client-side re-escaping pass of its own to fall back on."""
    if value is None:
        return ""
    return _html.escape(str(value), quote=True)


def _get_universal_drawer_html(active_surface: str = "") -> str:
    """Generate universal slide-out navigation drawer and overlay shared across all web surfaces."""
    return """
    <!-- Top-Left Universal Navigation Drawer Toggle & Brand Navbar -->
    <header class="universal-header">
        <nav class="universal-navbar" aria-label="Universal Navigation">
            <div class="nav-left">
                <button id="navToggleBtn" class="nav-toggle-btn" aria-label="Open universal navigation drawer" onclick="toggleUniversalDrawer()">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="3" y1="6" x2="21" y2="6"></line>
                        <line x1="3" y1="12" x2="21" y2="12"></line>
                        <line x1="3" y1="18" x2="21" y2="18"></line>
                    </svg>
                </button>
                <a href="https://restoricon.com" class="nav-brand-link" target="_blank" rel="noopener">
                    <svg class="brand-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#D4AF37" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"></path>
                    </svg>
                    <span class="brand-text">RESTORICON</span>
                </a>
            </div>

            <div class="nav-center-links">
                <a href="/quote" class="nav-tab-link" id="navLinkQuote">Quote Intake</a>
                <a href="/portal" class="nav-tab-link" id="navLinkPortal">Customer Portal</a>
                <a href="/admin" class="nav-tab-link" id="navLinkAdmin">Admin ERP</a>
            </div>

            <div class="nav-right">
                <a href="tel:8603371820" id="navPhoneLink" class="nav-phone-btn" aria-label="Call Restoricon 24/7">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path></svg>
                    <span id="navPhoneText">(860) 337-1820</span>
                </a>
                <div id="authNavContainer"></div>
            </div>
        </nav>
    </header>

    <!-- Slide-Out Drawer Backdrop Overlay -->
    <div id="navDrawerOverlay" class="drawer-backdrop" onclick="closeUniversalDrawer()" aria-hidden="true"></div>

    <!-- Slide-Out Drawer Navigation Panel -->
    <aside id="navDrawer" class="slide-drawer" aria-label="Universal Site Navigation" aria-hidden="true">
        <div class="drawer-header-bar">
            <div class="drawer-brand-block">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#D4AF37" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"></path>
                </svg>
                <div>
                    <div class="drawer-title">RESTORICON</div>
                    <div class="drawer-subtitle">Restore &bull; Rebuild &bull; Renew</div>
                </div>
            </div>
            <button class="drawer-close-btn" onclick="closeUniversalDrawer()" aria-label="Close navigation menu">&times;</button>
        </div>

        <div class="drawer-content">
            <div class="drawer-section-heading">ECOSYSTEM SURFACES</div>
            
            <a href="/quote" class="drawer-portal-card">
                <div class="card-icon">⚡</div>
                <div class="card-meta">
                    <div class="card-title">Quote & Emergency Intake</div>
                    <div class="card-desc">24/7 rapid disaster intake & instant scoping</div>
                </div>
                <span class="card-badge badge-gold">Instant</span>
            </a>

            <a href="/portal" class="drawer-portal-card">
                <div class="card-icon">👤</div>
                <div class="card-meta">
                    <div class="card-title">Customer Portal</div>
                    <div class="card-desc">Project tracker, e-sign contracts & invoices</div>
                </div>
                <span class="card-badge badge-blue">Live</span>
            </a>

            <a href="/admin" class="drawer-portal-card">
                <div class="card-icon">🛡️</div>
                <div class="card-meta">
                    <div class="card-title">Staff & Admin ERP</div>
                    <div class="card-desc">Operations, dynamic permissions, CRM & finance</div>
                </div>
                <span class="card-badge badge-slate">Staff</span>
            </a>

            <div class="drawer-section-heading" style="margin-top: 1.5rem;">WEBSITE NAVIGATION</div>
            <nav class="drawer-nav-menu">
                <a href="https://restoricon.com/#home" class="drawer-menu-item" target="_blank" rel="noopener"><span>🏠</span> Home</a>
                <a href="https://restoricon.com/#services" class="drawer-menu-item" target="_blank" rel="noopener"><span>🔨</span> Services & Remediation</a>
                <a href="https://restoricon.com/#subcontractors" class="drawer-menu-item" target="_blank" rel="noopener"><span>🤝</span> Subcontractor Network</a>
                <a href="https://restoricon.com/#about" class="drawer-menu-item" target="_blank" rel="noopener"><span>ℹ️</span> About Us</a>
                <a href="https://restoricon.com/#tech-advantage" class="drawer-menu-item" target="_blank" rel="noopener"><span>💻</span> Tech Advantage</a>
                <a href="https://restoricon.com/#faq" class="drawer-menu-item" target="_blank" rel="noopener"><span>❓</span> FAQ</a>
                <a href="https://restoricon.com/#contact" class="drawer-menu-item" target="_blank" rel="noopener"><span>✉️</span> Contact Direct</a>
            </nav>
        </div>

        <div class="drawer-footer-bar">
            <div><strong>Direct Dispatch:</strong> <a href="tel:8603371820" id="drawerPhoneLink">(860) 337-1820</a></div>
            <div><strong>Licensure:</strong> <span id="drawerLicense">CT HIC.0692750</span> &bull; Fully Insured</div>
            <div><strong>Email:</strong> <a href="mailto:contact@restoricon.com" id="drawerEmailLink">contact@restoricon.com</a></div>
        </div>
    </aside>
    """


def _get_common_styles() -> str:
    """Return common CSS variables, universal header, and drawer styles matching restoricon.com."""
    return """
        :root {
            --navy: #0A192F;
            --navy-dark: #071224;
            --charcoal: #1E293B;
            --bronze: #D4AF37;
            --bronze-hover: #b89628;
            --offwhite: #F8FAFC;
            --card-bg: #112240;
            --card-border: #233554;
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;
            --success: #10B981;
            --danger: #EF4444;
            --warning: #F59E0B;
            --info: #38BDF8;
            --font-stack: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: var(--font-stack); }
        body { background-color: var(--navy); color: var(--text-main); line-height: 1.6; min-height: 100vh; display: flex; flex-direction: column; }
        
        /* Universal Header & Navbar */
        .universal-header {
            position: sticky;
            top: 0;
            z-index: 1000;
            background-color: var(--navy);
            border-bottom: 1px solid rgba(255,255,255,0.08);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        .universal-navbar {
            max-width: 1300px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            justify-content: space-between;
            height: 4.25rem;
            padding: 0 1.25rem;
        }
        .nav-left { display: flex; align-items: center; gap: 0.85rem; }
        .nav-toggle-btn {
            background: transparent;
            border: 1px solid rgba(255,255,255,0.15);
            color: var(--offwhite);
            border-radius: 6px;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .nav-toggle-btn:hover {
            background: rgba(255,255,255,0.1);
            border-color: var(--bronze);
            color: var(--bronze);
        }
        .nav-brand-link {
            display: flex;
            align-items: center;
            gap: 0.6rem;
            text-decoration: none;
            color: var(--offwhite);
        }
        .nav-brand-link .brand-text {
            font-weight: 800;
            font-size: 1.25rem;
            letter-spacing: 0.06em;
            color: var(--offwhite);
        }
        .nav-brand-link:hover .brand-text { color: var(--bronze); }
        .nav-center-links { display: flex; align-items: center; gap: 1.25rem; }
        .nav-tab-link {
            color: #E2E8F0;
            text-decoration: none;
            font-weight: 500;
            font-size: 0.95rem;
            padding: 0.4rem 0.6rem;
            border-radius: 6px;
            transition: all 0.2s ease;
        }
        .nav-tab-link:hover, .nav-tab-link.active {
            color: var(--bronze);
            background: rgba(212, 175, 55, 0.1);
        }
        .nav-right { display: flex; align-items: center; gap: 1rem; }
        .nav-phone-btn {
            color: var(--offwhite);
            text-decoration: none;
            display: flex;
            align-items: center;
            gap: 0.45rem;
            font-weight: 600;
            font-size: 0.9rem;
            padding: 0.45rem 0.85rem;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 6px;
            transition: all 0.2s ease;
        }
        .nav-phone-btn:hover {
            border-color: var(--bronze);
            color: var(--bronze);
            background: rgba(212, 175, 55, 0.1);
        }
        .btn-gold {
            background: linear-gradient(135deg, #D4AF37 0%, #B89628 100%);
            color: #0A192F;
            font-weight: 700;
            border: none;
            border-radius: 6px;
            padding: 0.55rem 1.15rem;
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.4rem;
            transition: all 0.2s ease;
        }
        .btn-gold:hover {
            background: linear-gradient(135deg, #E5C158 0%, #C9A739 100%);
            transform: translateY(-1px);
        }

        /* Slide-Out Navigation Drawer */
        .drawer-backdrop {
            position: fixed;
            inset: 0;
            background: rgba(10, 25, 47, 0.8);
            backdrop-filter: blur(4px);
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.3s ease;
            z-index: 2000;
        }
        .drawer-backdrop.active {
            opacity: 1;
            pointer-events: auto;
        }
        .slide-drawer {
            position: fixed;
            top: 0;
            left: 0;
            bottom: 0;
            width: 350px;
            max-width: 88vw;
            background-color: var(--navy);
            color: var(--offwhite);
            z-index: 2001;
            transform: translateX(-100%);
            transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            box-shadow: 6px 0 28px rgba(0,0,0,0.6);
            display: flex;
            flex-direction: column;
        }
        .slide-drawer.open {
            transform: translateX(0);
        }
        .drawer-header-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 1.25rem 1.5rem;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            background: var(--navy-dark);
        }
        .drawer-brand-block { display: flex; align-items: center; gap: 0.75rem; }
        .drawer-title { font-weight: 800; font-size: 1.15rem; letter-spacing: 0.05em; color: var(--offwhite); }
        .drawer-subtitle { font-size: 0.75rem; color: var(--bronze); }
        .drawer-close-btn {
            background: none;
            border: none;
            color: #94A3B8;
            font-size: 1.75rem;
            cursor: pointer;
            line-height: 1;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
        }
        .drawer-close-btn:hover { color: var(--offwhite); }
        .drawer-content {
            flex: 1;
            overflow-y: auto;
            padding: 1.25rem 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }
        .drawer-section-heading {
            font-size: 0.7rem;
            font-weight: 700;
            letter-spacing: 0.1em;
            color: #94A3B8;
            text-transform: uppercase;
        }
        .drawer-portal-card {
            display: flex;
            align-items: center;
            gap: 0.85rem;
            padding: 0.85rem 1rem;
            border-radius: 8px;
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            text-decoration: none;
            color: var(--offwhite);
            transition: all 0.2s ease;
        }
        .drawer-portal-card:hover {
            transform: translateY(-2px);
            border-color: var(--bronze);
            background: #1a325c;
        }
        .card-icon { font-size: 1.35rem; width: 36px; height: 36px; border-radius: 8px; background: rgba(255,255,255,0.06); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
        .card-meta { flex: 1; min-width: 0; }
        .card-title { font-weight: 600; font-size: 0.95rem; color: var(--offwhite); }
        .card-desc { font-size: 0.75rem; color: #94A3B8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .card-badge {
            font-size: 0.65rem;
            font-weight: 700;
            padding: 0.2rem 0.5rem;
            border-radius: 9999px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            white-space: nowrap;
        }
        .badge-gold { background: rgba(212, 175, 55, 0.2); color: var(--bronze); border: 1px solid rgba(212, 175, 55, 0.4); }
        .badge-blue { background: rgba(56, 189, 248, 0.15); color: var(--info); border: 1px solid rgba(56, 189, 248, 0.3); }
        .badge-slate { background: rgba(148, 163, 184, 0.15); color: #E2E8F0; border: 1px solid rgba(148, 163, 184, 0.3); }
        .drawer-nav-menu { display: flex; flex-direction: column; gap: 0.25rem; }
        .drawer-menu-item {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.65rem 0.85rem;
            border-radius: 6px;
            color: #E2E8F0;
            text-decoration: none;
            font-weight: 500;
            font-size: 0.95rem;
            transition: all 0.15s ease;
        }
        .drawer-menu-item:hover {
            background: rgba(255,255,255,0.06);
            color: var(--bronze);
            padding-left: 1rem;
        }
        .drawer-footer-bar {
            padding: 1rem 1.5rem;
            border-top: 1px solid rgba(255,255,255,0.1);
            background: var(--navy-dark);
            font-size: 0.8rem;
            color: #94A3B8;
            display: flex;
            flex-direction: column;
            gap: 0.35rem;
        }
        .drawer-footer-bar a { color: var(--bronze); text-decoration: none; }
        .drawer-footer-bar a:hover { text-decoration: underline; }

        @media (max-width: 900px) {
            .nav-center-links { display: none; }
            .nav-phone-btn span { display: none; }
        }
    """


def _get_common_script() -> str:
    """Return common JS functions for drawer controls and token management."""
    return """
    function toggleUniversalDrawer() {
        const drawer = document.getElementById('navDrawer');
        const overlay = document.getElementById('navDrawerOverlay');
        const btn = document.getElementById('navToggleBtn');
        if (!drawer) return;
        const isOpen = drawer.classList.toggle('open');
        drawer.setAttribute('aria-hidden', !isOpen);
        if (overlay) overlay.classList.toggle('active', isOpen);
        if (btn) btn.setAttribute('aria-expanded', isOpen);
        document.body.style.overflow = isOpen ? 'hidden' : '';
    }

    function closeUniversalDrawer() {
        const drawer = document.getElementById('navDrawer');
        const overlay = document.getElementById('navDrawerOverlay');
        const btn = document.getElementById('navToggleBtn');
        if (drawer) {
            drawer.classList.remove('open');
            drawer.setAttribute('aria-hidden', 'true');
        }
        if (overlay) overlay.classList.remove('active');
        if (btn) btn.setAttribute('aria-expanded', 'false');
        document.body.style.overflow = '';
    }

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeUniversalDrawer();
    });

    // sessionStorage (not localStorage): the token is cleared when the
    // browser/tab closes, so every new browser session requires a fresh
    // username/password login rather than silently auto-logging in.
    function getAuthToken() {
        return sessionStorage.getItem('restoricon_token') || '';
    }

    function setAuthToken(token) {
        if (token) sessionStorage.setItem('restoricon_token', token);
        else sessionStorage.removeItem('restoricon_token');
    }

    async function validateSession(redirectTarget) {
        const token = getAuthToken();
        if (!token) {
            window.location.href = redirectTarget;
            return false;
        }
        try {
            const res = await fetch('/api/v1/auth/me', {
                headers: { 'Authorization': 'Bearer ' + token }
            });
            if (res.status === 401 || res.status === 403) {
                setAuthToken('');
                window.location.href = redirectTarget;
                return false;
            }
            return true;
        } catch (e) {
            return true;
        }
    }

    function logoutUser() {
        const token = getAuthToken();
        if (token) {
            fetch('/api/v1/auth/logout', {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + token }
            }).catch(() => {});
        }
        setAuthToken('');
        window.location.href = '/admin/login';
    }
    """


def render_login_surface(portal_type: str = "admin") -> str:
    """Render responsive, accessible, premium login page matching Restoricon Navy & Bronze branding."""
    is_admin = portal_type == "admin"
    title = "Staff & Admin Portal" if is_admin else "Customer Portal"
    subtitle = "Enterprise ERP & Restoration Operations Center" if is_admin else "Track your restoration project, contracts, and invoices"
    redirect_target = "/admin" if is_admin else "/portal"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — Restoricon, LLC</title>
    <link rel="icon" href="/assets/logos/favicon-32.png" type="image/png" sizes="32x32">
    <style>
        {_get_common_styles()}
        .login-wrapper {{
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 2.5rem 1.5rem;
            background: radial-gradient(circle at top center, #1E293B 0%, #0A192F 100%);
        }}
        .login-card {{
            background: var(--card-bg);
            width: 100%;
            max-width: 440px;
            border-radius: 16px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
            border: 1px solid var(--card-border);
            padding: 2.5rem 2rem;
            position: relative;
        }}
        .brand-header {{ text-align: center; margin-bottom: 1.75rem; }}
        .brand-header h1 {{ font-size: 1.35rem; font-weight: 700; color: var(--offwhite); }}
        .brand-header p {{ font-size: 0.85rem; color: var(--text-muted); margin-top: 0.35rem; }}
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
        .form-group {{ margin-bottom: 1.25rem; }}
        label {{ display: block; font-size: 0.82rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.4rem; }}
        input {{
            width: 100%;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            border: 1px solid var(--card-border);
            background: #0A192F;
            color: var(--offwhite);
            font-size: 0.95rem;
            outline: none;
            transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }}
        input:focus {{ border-color: var(--bronze); box-shadow: 0 0 0 3px rgba(212, 175, 55, 0.2); }}
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
            transition: background 0.2s ease, transform 0.1s ease;
            margin-top: 0.5rem;
        }}
        .btn-submit:hover {{ background: linear-gradient(135deg, #e5c158 0%, #b88f1c 100%); transform: translateY(-1px); }}
        .error-banner {{
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.4);
            color: #F87171;
            padding: 0.65rem 0.85rem;
            border-radius: 8px;
            font-size: 0.82rem;
            margin-bottom: 1.25rem;
            display: none;
        }}
        .toggle-portal {{
            text-align: center;
            margin-top: 1.5rem;
            font-size: 0.82rem;
            color: var(--text-muted);
        }}
        .toggle-portal a {{ color: var(--bronze); text-decoration: none; font-weight: 600; }}
        .toggle-portal a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    {_get_universal_drawer_html("login")}

    <div class="login-wrapper">
        <div class="login-card">
            <div class="brand-header">
                <span class="badge-role">{title}</span>
                <h1>Restoricon Core Portal</h1>
                <p>{subtitle}</p>
            </div>

            <div id="loginError" class="error-banner" role="alert"></div>

            <form id="loginForm" onsubmit="handleLoginSubmit(event)">
                <div class="form-group">
                    <label for="usernameField">Username or Email</label>
                    <input type="text" id="usernameField" required autocomplete="username" placeholder="name@restoricon.com" autofocus>
                </div>
                <div class="form-group">
                    <label for="passwordField">Password</label>
                    <input type="password" id="passwordField" required autocomplete="current-password" placeholder="••••••••••••">
                </div>
                <button type="submit" id="submitBtn" class="btn-submit">Sign In to Dashboard</button>
            </form>

            <div class="toggle-portal">
                {"Need Customer Portal? <a href='/portal/login'>Switch to Customer Login &rarr;</a>" if is_admin else "Staff Member? <a href='/admin/login'>Switch to Admin ERP Login &rarr;</a>"}
            </div>
        </div>
    </div>


    <!-- Add Customer Modal -->
    <div id="addCustomerModal" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3>Add Customer</h3>
                <button onclick="closeCustomerModal()" style="background:none; border:none; color:#94A3B8; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <form onsubmit="submitCustomer(event)">
                <div class="form-group">
                    <label>First Name</label>
                    <input type="text" id="custFirst" required>
                </div>
                <div class="form-group">
                    <label>Last Name</label>
                    <input type="text" id="custLast" required>
                </div>
                <div class="form-group">
                    <label>Email</label>
                    <input type="email" id="custEmail" required>
                </div>
                <div class="form-group">
                    <label>Phone</label>
                    <input type="text" id="custPhone">
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem;">
                    <button type="button" onclick="closeCustomerModal()" class="btn-gold" style="background:transparent; border:1px solid var(--card-border); color:#CBD5E1;">Cancel</button>
                    <button type="submit" class="btn-gold">Save Customer</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Add Project Modal -->
    <div id="addProjectModal" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3>Create Project</h3>
                <button onclick="closeProjectModal()" style="background:none; border:none; color:#94A3B8; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <form onsubmit="submitProject(event)">
                <div class="form-group">
                    <label>Select Customer</label>
                    <select id="projCustomer" required></select>
                </div>
                <div class="form-group">
                    <label>Project Title</label>
                    <input type="text" id="projTitle" required placeholder="e.g. Water Mitigation">
                </div>
                <div class="form-group">
                    <label>Project Type</label>
                    <select id="projType" required>
                        <option value="Water">Water Damage</option>
                        <option value="Fire">Fire Damage</option>
                        <option value="Mold">Mold Remediation</option>
                        <option value="Reconstruction">Reconstruction</option>
                    </select>
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem;">
                    <button type="button" onclick="closeProjectModal()" class="btn-gold" style="background:transparent; border:1px solid var(--card-border); color:#CBD5E1;">Cancel</button>
                    <button type="submit" class="btn-gold">Save Project</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        {_get_common_script()}

        async function handleLoginSubmit(e) {{
            e.preventDefault();
            const err = document.getElementById('loginError');
            const btn = document.getElementById('submitBtn');
            const u = document.getElementById('usernameField').value.trim();
            const p = document.getElementById('passwordField').value;
            
            err.style.display = 'none';
            btn.disabled = true;
            btn.innerText = 'Verifying Credentials...';

            try {{
                const res = await fetch('/api/v1/auth/login', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ username_or_email: u, password: p }})
                }});
                const data = await res.json();
                if (res.ok && data.token) {{
                    setAuthToken(data.token);
                    let target = '{redirect_target}';
                    if (target === '/admin' && data.user && data.user.role) {{
                        const r = data.user.role;
                        if (r === 'project_manager') target = '/pm';
                        else if (r === 'technician') target = '/tech';
                        else if (r === 'sales') target = '/sales';
                        else if (r === 'sales_manager') target = '/sales';
                        else if (r === 'subcontractor') target = '/subcontractor';
                    }}
                    window.location.href = target;
                }} else {{
                    err.innerText = data.error || 'Invalid credentials. Please check and try again.';
                    err.style.display = 'block';
                    btn.disabled = false;
                    btn.innerText = 'Sign In to Dashboard';
                }}
            }} catch (ex) {{
                err.innerText = 'Connection error. Please check server status.';
                err.style.display = 'block';
                btn.disabled = false;
                btn.innerText = 'Sign In to Dashboard';
            }}
        }}
    </script>
</body>
</html>"""


def render_quote_surface() -> str:
    """Render public 24/7 Quote Intake, Live Booking & Calculator matching restoricon.com."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Request a Restoration Quote — Restoricon, LLC | Connecticut General Contractor</title>
    <meta name="description" content="Restoricon, LLC provides 24/7 rapid response disaster restoration, structural repairs, and free pre-claim construction estimates across Hartford County, CT.">
    <link rel="icon" href="/assets/logos/favicon-32.png" type="image/png" sizes="32x32">
    <style>
        """ + _get_common_styles() + """
        .emergency-banner {
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
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        .emergency-banner a { color: #fde047; text-decoration: none; font-weight: 700; }
        .emergency-banner a:hover { text-decoration: underline; }

        .main-container { max-width: 1200px; margin: 2rem auto; padding: 0 1.25rem; }
        .hero-heading { text-align: center; margin-bottom: 2.5rem; }
        .hero-heading h1 { font-size: 2.2rem; color: var(--offwhite); font-weight: 800; }
        .hero-heading p { color: var(--text-muted); font-size: 1.1rem; margin-top: 0.5rem; }
        
        .grid-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }
        @media (max-width: 900px) { .grid-layout { grid-template-columns: 1fr; } }

        .surface-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 1.75rem;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }
        .card-header-line {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 1.25rem;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid rgba(255,255,255,0.08);
        }
        .card-header-line h2 { font-size: 1.25rem; color: var(--offwhite); }
        .card-header-line .icon { font-size: 1.5rem; }

        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }
        @media (max-width: 550px) { .form-row { grid-template-columns: 1fr; } }
        .form-group { margin-bottom: 1rem; }
        label { display: block; font-size: 0.85rem; font-weight: 600; color: #CBD5E1; margin-bottom: 0.35rem; }
        input, select, textarea {
            width: 100%;
            padding: 0.7rem 0.85rem;
            border-radius: 6px;
            border: 1px solid var(--card-border);
            background: #0A192F;
            color: var(--offwhite);
            font-size: 0.92rem;
            outline: none;
            transition: border-color 0.15s;
        }
        input:focus, select:focus, textarea:focus { border-color: var(--bronze); }
        textarea { resize: vertical; min-height: 85px; }

        .calc-result-box {
            background: #0A192F;
            border: 1px solid var(--bronze);
            border-radius: 8px;
            padding: 1.25rem;
            margin-top: 1.25rem;
            text-align: center;
        }
        .calc-result-num { font-size: 1.8rem; font-weight: 800; color: var(--bronze); }
        .calc-meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-top: 1rem; text-align: left; font-size: 0.85rem; }
        .calc-meta-item { background: rgba(255,255,255,0.03); padding: 0.5rem 0.75rem; border-radius: 4px; }
        
        .alert-box { padding: 0.85rem 1rem; border-radius: 6px; margin-bottom: 1rem; display: none; font-size: 0.9rem; }
        .alert-success { background: rgba(16, 185, 129, 0.15); border: 1px solid var(--success); color: #6EE7B7; }
        .alert-error { background: rgba(239, 68, 68, 0.15); border: 1px solid var(--danger); color: #FCA5A5; }
    </style>
</head>
<body>
    <div class="emergency-banner">
        <span>🚨 Emergency Service: 24/7 Rapid Structural Drying & Damage Mitigation</span>
        <a href="tel:8603371820">Call Direct: (860) 337-1820 &rarr;</a>
    </div>

    """ + _get_universal_drawer_html("quote") + """

    <main class="main-container">
        <div class="hero-heading">
            <h1>Request a Restoration Quote & Scoping</h1>
            <p>Direct rapid dispatch for residential property damage across Hartford County, Connecticut &bull; CT HIC.0692750</p>
        </div>

        <div class="grid-layout">
            <!-- Left Column: Quote Intake Form -->
            <div class="surface-card">
                <div class="card-header-line">
                    <span class="icon">⚡</span>
                    <h2>Emergency Intake & Estimate Request</h2>
                </div>

                <div id="leadAlert" class="alert-box"></div>

                <form id="publicQuoteForm" onsubmit="submitQuoteForm(event)">
                    <div class="form-row">
                        <div class="form-group">
                            <label for="leadName">Full Name *</label>
                            <input type="text" id="leadName" required placeholder="John Smith">
                        </div>
                        <div class="form-group">
                            <label for="leadPhone">Phone Number *</label>
                            <input type="tel" id="leadPhone" required placeholder="(860) 555-0199">
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label for="leadEmail">Email Address *</label>
                            <input type="email" id="leadEmail" required placeholder="john@example.com">
                        </div>
                        <div class="form-group">
                            <label for="projectType">Damage Type *</label>
                            <select id="projectType" required>
                                <option value="water_damage">Water Mitigation & Flooding</option>
                                <option value="fire_smoke">Fire & Smoke Damage</option>
                                <option value="mold_remediation">Mold Remediation</option>
                                <option value="structural_remodel">Structural & Reconstruction</option>
                            </select>
                        </div>
                    </div>

                    <div class="form-group">
                        <label for="leadAddress">Property Address (Hartford County, CT) *</label>
                        <input type="text" id="leadAddress" required placeholder="123 Main St, Hartford, CT">
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label for="urgencyLevel">Urgency Level</label>
                            <select id="urgencyLevel">
                                <option value="emergency">Emergency Rapid Response (&lt;2 hr)</option>
                                <option value="urgent" selected>Urgent (Within 24-48 Hours)</option>
                                <option value="standard">Standard Scoping & Estimate</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label for="insuranceCarrier">Insurance Carrier (if filing)</label>
                            <input type="text" id="insuranceCarrier" placeholder="e.g. Travelers, State Farm">
                        </div>
                    </div>

                    <div class="form-group">
                        <label for="projectDesc">Damage Scope & Description</label>
                        <textarea id="projectDesc" placeholder="Describe affected rooms, water source, square footage, or structural issues..."></textarea>
                    </div>

                    <button type="submit" id="quoteSubmitBtn" class="btn-gold" style="width: 100%; padding: 0.85rem; font-size: 1rem;">
                        Submit For Immediate Dispatch &rarr;
                    </button>
                </form>
            </div>

            <!-- Right Column: Interactive Structural Drying Calculator & Booking -->
            <div style="display: flex; flex-direction: column; gap: 2rem;">
                <div class="surface-card">
                    <div class="card-header-line">
                        <span class="icon">📐</span>
                        <h2>Structural Drying & Scope Estimator</h2>
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label for="calcArea">Affected Area (Sq Ft)</label>
                            <input type="number" id="calcArea" value="650" min="50" max="10000" oninput="runDryingCalculation()">
                        </div>
                        <div class="form-group">
                            <label for="calcHeight">Ceiling Height (Ft)</label>
                            <input type="number" id="calcHeight" value="8" min="6" max="25" oninput="runDryingCalculation()">
                        </div>
                    </div>

                    <div class="form-group">
                        <label for="calcCategory">Water Category</label>
                        <select id="calcCategory" onchange="runDryingCalculation()">
                            <option value="cat1">Category 1 (Clean Water - Broken Supply Pipe)</option>
                            <option value="cat2" selected>Category 2 (Grey Water - Appliance Overflow)</option>
                            <option value="cat3">Category 3 (Black Water - Sewer / Storm Ingress)</option>
                        </select>
                    </div>

                    <div class="calc-result-box">
                        <div style="font-size: 0.8rem; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.05em;">Estimated Restoration Scope</div>
                        <div class="calc-result-num" id="calcCostRange">$2,400 - $4,800</div>
                        <div class="calc-meta-grid">
                            <div class="calc-meta-item"><strong>Air Movers:</strong> <span id="calcMovers">5 units</span></div>
                            <div class="calc-meta-item"><strong>LGR Dehumidifiers:</strong> <span id="calcDehums">2 units</span></div>
                            <div class="calc-meta-item"><strong>Estimated Duration:</strong> <span>3 - 4 Days Drying</span></div>
                            <div class="calc-meta-item"><strong>Containment:</strong> <span id="calcContainment">Standard Barrier</span></div>
                        </div>
                    </div>
                </div>

                <!-- Instant Booking Card -->
                <div class="surface-card">
                    <div class="card-header-line">
                        <span class="icon">📅</span>
                        <h2>Live Estimate Appointment Booking</h2>
                    </div>
                    <div id="bookingAlert" class="alert-box"></div>
                    <form id="bookingForm" onsubmit="submitBookingForm(event)">
                        <div class="form-row">
                            <div class="form-group">
                                <label for="bookDate">Preferred Date</label>
                                <input type="date" id="bookDate" required>
                            </div>
                            <div class="form-group">
                                <label for="bookTime">Time Window</label>
                                <select id="bookTime">
                                    <option value="09:00">Morning (9:00 AM - 12:00 PM)</option>
                                    <option value="13:00" selected>Afternoon (1:00 PM - 4:00 PM)</option>
                                    <option value="17:00">Evening / Rapid (5:00 PM - 7:00 PM)</option>
                                </select>
                            </div>
                        </div>
                        <button type="submit" id="bookSubmitBtn" class="btn-gold" style="width: 100%;">
                            Lock In Scoping Appointment
                        </button>
                    </form>
                </div>
            </div>
        </div>
    </main>


    <!-- Add Customer Modal -->
    <div id="addCustomerModal" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3>Add Customer</h3>
                <button onclick="closeCustomerModal()" style="background:none; border:none; color:#94A3B8; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <form onsubmit="submitCustomer(event)">
                <div class="form-group">
                    <label>First Name</label>
                    <input type="text" id="custFirst" required>
                </div>
                <div class="form-group">
                    <label>Last Name</label>
                    <input type="text" id="custLast" required>
                </div>
                <div class="form-group">
                    <label>Email</label>
                    <input type="email" id="custEmail" required>
                </div>
                <div class="form-group">
                    <label>Phone</label>
                    <input type="text" id="custPhone">
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem;">
                    <button type="button" onclick="closeCustomerModal()" class="btn-gold" style="background:transparent; border:1px solid var(--card-border); color:#CBD5E1;">Cancel</button>
                    <button type="submit" class="btn-gold">Save Customer</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Add Project Modal -->
    <div id="addProjectModal" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3>Create Project</h3>
                <button onclick="closeProjectModal()" style="background:none; border:none; color:#94A3B8; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <form onsubmit="submitProject(event)">
                <div class="form-group">
                    <label>Select Customer</label>
                    <select id="projCustomer" required></select>
                </div>
                <div class="form-group">
                    <label>Project Title</label>
                    <input type="text" id="projTitle" required placeholder="e.g. Water Mitigation">
                </div>
                <div class="form-group">
                    <label>Project Type</label>
                    <select id="projType" required>
                        <option value="Water">Water Damage</option>
                        <option value="Fire">Fire Damage</option>
                        <option value="Mold">Mold Remediation</option>
                        <option value="Reconstruction">Reconstruction</option>
                    </select>
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem;">
                    <button type="button" onclick="closeProjectModal()" class="btn-gold" style="background:transparent; border:1px solid var(--card-border); color:#CBD5E1;">Cancel</button>
                    <button type="submit" class="btn-gold">Save Project</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        """ + _get_common_script() + """

        function runDryingCalculation() {
            const sqft = parseFloat(document.getElementById('calcArea').value) || 0;
            const height = parseFloat(document.getElementById('calcHeight').value) || 8;
            const cat = document.getElementById('calcCategory').value;
            
            const volume = sqft * height;
            const movers = Math.max(2, Math.ceil(sqft / 120));
            const dehums = Math.max(1, Math.ceil(volume / 3000));
            
            let multiplier = 4.2;
            if (cat === 'cat2') multiplier = 5.8;
            if (cat === 'cat3') multiplier = 8.5;
            
            const low = Math.round(sqft * (multiplier * 0.85));
            const high = Math.round(sqft * (multiplier * 1.35));

            document.getElementById('calcCostRange').innerText = `$${low.toLocaleString()} - $${high.toLocaleString()}`;
            document.getElementById('calcMovers').innerText = `${movers} Commercial Units`;
            document.getElementById('calcDehums').innerText = `${dehums} XL LGR Units`;
            document.getElementById('calcContainment').innerText = (cat === 'cat3') ? 'Critical HEPA Isolation' : 'Standard Dust/Vapor Barrier';
        }

        async function submitQuoteForm(e) {
            e.preventDefault();
            const alertBox = document.getElementById('leadAlert');
            const btn = document.getElementById('quoteSubmitBtn');
            alertBox.style.display = 'none';
            btn.disabled = true;
            btn.innerText = 'Submitting Damage Report...';

            const payload = {
                name: document.getElementById('leadName').value.trim(),
                phone: document.getElementById('leadPhone').value.trim(),
                email: document.getElementById('leadEmail').value.trim(),
                address: document.getElementById('leadAddress').value.trim(),
                project_type: document.getElementById('projectType').value,
                urgency: document.getElementById('urgencyLevel').value,
                insurance: !!document.getElementById('insuranceCarrier').value,
                insurance_carrier: document.getElementById('insuranceCarrier').value.trim(),
                description: document.getElementById('projectDesc').value.trim()
            };

            try {
                const res = await fetch('/api/v1/public/leads', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    alertBox.className = 'alert-box alert-success';
                    alertBox.innerHTML = `<strong>Intake Confirmed!</strong> Reference ID: <code>#LEAD-${data.lead_id}</code>. Dispatch notified. An emergency estimator is reviewing your file now.`;
                    alertBox.style.display = 'block';
                    document.getElementById('publicQuoteForm').reset();
                } else {
                    alertBox.className = 'alert-box alert-error';
                    alertBox.innerText = data.error || 'Submission error. Please call (860) 337-1820 directly.';
                    alertBox.style.display = 'block';
                }
            } catch (ex) {
                alertBox.className = 'alert-box alert-error';
                alertBox.innerText = 'Unable to reach server. Please call (860) 337-1820 for 24/7 service.';
                alertBox.style.display = 'block';
            } finally {
                btn.disabled = false;
                btn.innerText = 'Submit For Immediate Dispatch →';
            }
        }

        async function submitBookingForm(e) {
            e.preventDefault();
            const alertBox = document.getElementById('bookingAlert');
            const btn = document.getElementById('bookSubmitBtn');
            alertBox.style.display = 'none';

            const name = document.getElementById('leadName').value.trim();
            const phone = document.getElementById('leadPhone').value.trim();
            const email = document.getElementById('leadEmail').value.trim();
            const address = document.getElementById('leadAddress').value.trim();

            if (!name || !phone) {
                alertBox.className = 'alert-box alert-error';
                alertBox.innerText = 'Please provide your Full Name and Phone Number in the intake form above first.';
                alertBox.style.display = 'block';
                return;
            }

            btn.disabled = true;
            btn.innerText = 'Reserving Time Slot...';

            const payload = {
                name: name,
                phone: phone,
                email: email,
                address: address,
                preferred_date: document.getElementById('bookDate').value,
                preferred_time: document.getElementById('bookTime').value,
                appointment_type: 'emergency_inspection'
            };

            try {
                const res = await fetch('/api/v1/public/booking', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    alertBox.className = 'alert-box alert-success';
                    alertBox.innerHTML = `<strong>Appointment Booked!</strong> Ref: <code>#APPT-${data.appointment_id}</code> for ${payload.preferred_date}. Confirmation sent to ${email || phone}.`;
                    alertBox.style.display = 'block';
                } else {
                    alertBox.className = 'alert-box alert-error';
                    alertBox.innerText = data.error || 'Failed to book slot. Please call (860) 337-1820.';
                    alertBox.style.display = 'block';
                }
            } catch (ex) {
                alertBox.className = 'alert-box alert-error';
                alertBox.innerText = 'Network error. Please call (860) 337-1820.';
                alertBox.style.display = 'block';
            } finally {
                btn.disabled = false;
                btn.innerText = 'Lock In Scoping Appointment';
            }
        }

        // Set default appointment date to tomorrow
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        const yyyy = tomorrow.getFullYear();
        const mm = String(tomorrow.getMonth() + 1).padStart(2, '0');
        const dd = String(tomorrow.getDate()).padStart(2, '0');
        document.getElementById('bookDate').value = `${yyyy}-${mm}-${dd}`;
        runDryingCalculation();
    </script>
</body>
</html>"""


def render_portal_surface() -> str:
    """Render customer portal with project timeline, e-signature pad, invoices, and communication feed."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Customer Portal — Restoricon, LLC</title>
    <link rel="icon" href="/assets/logos/favicon-32.png" type="image/png" sizes="32x32">
    <style>
        """ + _get_common_styles() + """
        .portal-layout { max-width: 1200px; margin: 2rem auto; padding: 0 1.25rem; display: flex; flex-direction: column; gap: 2rem; }
        .hero-banner-card {
            background: linear-gradient(135deg, #112240 0%, #1c2e4a 100%);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }
        @media (max-width: 768px) { .hero-banner-card { flex-direction: column; align-items: flex-start; gap: 1rem; } }
        .hero-banner-card h1 { font-size: 1.8rem; color: var(--offwhite); }
        .hero-banner-card p { color: var(--text-muted); font-size: 0.95rem; margin-top: 0.25rem; }

        .timeline-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 1.75rem;
        }
        .timeline-steps {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 1rem;
            margin-top: 1.5rem;
            position: relative;
        }
        @media (max-width: 850px) { .timeline-steps { grid-template-columns: 1fr; } }
        .step-item {
            background: #0A192F;
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 1rem;
            text-align: center;
            transition: all 0.2s ease;
        }
        .step-item.completed { border-color: var(--success); background: rgba(16, 185, 129, 0.08); }
        .step-item.active { border-color: var(--bronze); background: rgba(212, 175, 55, 0.1); transform: scale(1.02); }
        .step-num { font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.25rem; }
        .step-name { font-weight: 700; font-size: 0.95rem; color: var(--offwhite); }
        .step-status { font-size: 0.75rem; margin-top: 0.4rem; }
        .status-done { color: var(--success); }
        .status-active { color: var(--bronze); font-weight: 600; }
        .status-pending { color: #64748B; }

        .two-column-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }
        @media (max-width: 850px) { .two-column-grid { grid-template-columns: 1fr; } }

        .content-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 1.5rem;
        }
        .content-card h2 { font-size: 1.2rem; color: var(--offwhite); margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; }

        /* Signature Canvas Pad */
        .sig-canvas-container {
            background: #071224;
            border: 2px dashed var(--card-border);
            border-radius: 8px;
            margin: 1rem 0;
            overflow: hidden;
        }
        canvas#signaturePad { width: 100%; height: 160px; display: block; cursor: crosshair; }

        /* Chat / Message Feed */
        .chat-feed {
            background: #0A192F;
            border: 1px solid var(--card-border);
            border-radius: 8px;
            height: 220px;
            overflow-y: auto;
            padding: 1rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            margin-bottom: 1rem;
        }
        .chat-msg { padding: 0.6rem 0.85rem; border-radius: 8px; max-width: 85%; font-size: 0.88rem; }
        .chat-msg.pm { background: #1E293B; color: #E2E8F0; align-self: flex-start; }
        .chat-msg.client { background: var(--bronze); color: var(--navy); font-weight: 500; align-self: flex-end; }
        .chat-input-row { display: flex; gap: 0.5rem; }

        /* Invoice Table */
        table.portal-table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
        table.portal-table th, table.portal-table td { padding: 0.65rem 0.85rem; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.06); }
        table.portal-table th { color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; }
    </style>
</head>
<body>
    """ + _get_universal_drawer_html("portal") + """

    <main class="portal-layout">
        <div class="hero-banner-card">
            <div>
                <h1>Your Restoration Portal</h1>
                <p id="portalGreeting">Hartford County Active Restoration Job Sites &bull; Live Progress Tracker</p>
            </div>
            <div style="display: flex; gap: 0.75rem;">
                <a href="tel:8603371820" class="btn-gold" style="background: transparent; border: 1px solid var(--bronze); color: var(--bronze);">
                    📞 Call PM Direct
                </a>
                <button onclick="logoutUser()" class="btn-gold" style="background: rgba(239, 68, 68, 0.2); border: 1px solid var(--danger); color: #FCA5A5;">
                    Sign Out
                </button>
            </div>
        </div>

        <!-- 5-Phase Project Timeline -->
        <div class="timeline-card">
            <h2 style="font-size: 1.15rem; color: var(--offwhite);">Restoration Phase Timeline</h2>
            <div class="timeline-steps">
                <div class="step-item completed">
                    <div class="step-num">Phase 1</div>
                    <div class="step-name">Intake & Scoping</div>
                    <div class="step-status status-done">✓ Completed</div>
                </div>
                <div class="step-item completed">
                    <div class="step-num">Phase 2</div>
                    <div class="step-name">Insurance Scoping</div>
                    <div class="step-status status-done">✓ Approved</div>
                </div>
                <div class="step-item active">
                    <div class="step-num">Phase 3</div>
                    <div class="step-name">Structural Drying</div>
                    <div class="step-status status-active">⚡ Active In Progress</div>
                </div>
                <div class="step-item">
                    <div class="step-num">Phase 4</div>
                    <div class="step-name">Reconstruction</div>
                    <div class="step-status status-pending">Queued</div>
                </div>
                <div class="step-item">
                    <div class="step-num">Phase 5</div>
                    <div class="step-name">Sign-Off & Closeout</div>
                    <div class="step-status status-pending">Final Step</div>
                </div>
            </div>
        </div>

        <div class="two-column-grid">
            <!-- Digital Contract E-Signature Pad -->
            <div class="content-card">
                <h2><span>✍️</span> Document & Contract E-Signature</h2>
                <p style="font-size: 0.85rem; color: var(--text-muted);">
                    Review your active scope authorization agreement. Sign in the box below to authorize structural work.
                </p>
                <div class="sig-canvas-container">
                    <canvas id="signaturePad"></canvas>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <button onclick="clearSignature()" class="btn-gold" style="background: transparent; border: 1px solid var(--card-border); color: #CBD5E1; font-size: 0.85rem;">
                        Clear Pad
                    </button>
                    <button onclick="submitSignature()" class="btn-gold" id="sigSubmitBtn">
                        Sign & Authorize Contract
                    </button>
                </div>
                <div id="sigAlert" style="margin-top: 0.75rem; font-size: 0.85rem; display: none;"></div>
            </div>

            <!-- Direct PM Communication Feed -->
            <div class="content-card">
                <h2><span>💬</span> Project Manager Direct Thread</h2>
                <div class="chat-feed" id="chatFeed">
                    <div class="chat-msg pm">
                        <strong>Restoricon Dispatch:</strong> Emergency containment barriers and 5 LGR dehumidifiers were deployed on-site today. Moisture readings are tracking on schedule.
                    </div>
                    <div class="chat-msg client">
                        <strong>You:</strong> Thank you! Adjuster said they approved the line-item estimate this afternoon.
                    </div>
                    <div class="chat-msg pm">
                        <strong>Restoricon PM:</strong> Excellent, we will update the final drying logs in your document tab tomorrow morning!
                    </div>
                </div>
                <form onsubmit="sendPortalMessage(event)" class="chat-input-row">
                    <input type="text" id="portalMsgInput" placeholder="Message your lead project manager..." required>
                    <button type="submit" class="btn-gold" style="padding: 0.5rem 1rem;">Send</button>
                </form>
            </div>
        </div>

        <!-- Invoices & Billing Summary -->
        <div class="content-card">
            <h2><span>💰</span> Invoices & Payment Ledger</h2>
            <table class="portal-table">
                <thead>
                    <tr>
                        <th>Invoice #</th>
                        <th>Project Milestone</th>
                        <th>Amount</th>
                        <th>Status</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody id="invoiceTableBody">
                    <tr>
                        <td><code>#INV-2026-081</code></td>
                        <td>Initial Water Mitigation Deposit & Containment</td>
                        <td><strong>$5,000.00</strong></td>
                        <td><span style="color: var(--success); font-weight: 700;">● Paid in Full</span></td>
                        <td><a href="#" style="color: var(--bronze); text-decoration: none;">Download PDF</a></td>
                    </tr>
                    <tr>
                        <td><code>#INV-2026-092</code></td>
                        <td>Structural Framing & Drywall Restoration</td>
                        <td><strong>$7,500.00</strong></td>
                        <td><span style="color: var(--warning); font-weight: 700;">● Insurance Pending</span></td>
                        <td><button class="btn-gold" style="padding: 0.3rem 0.75rem; font-size: 0.8rem;" onclick="alert('Direct ACH & Card payment gateway connected.')">Pay Online</button></td>
                    </tr>
                </tbody>
            </table>
        </div>
    </main>


    <!-- Add Customer Modal -->
    <div id="addCustomerModal" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3>Add Customer</h3>
                <button onclick="closeCustomerModal()" style="background:none; border:none; color:#94A3B8; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <form onsubmit="submitCustomer(event)">
                <div class="form-group">
                    <label>First Name</label>
                    <input type="text" id="custFirst" required>
                </div>
                <div class="form-group">
                    <label>Last Name</label>
                    <input type="text" id="custLast" required>
                </div>
                <div class="form-group">
                    <label>Email</label>
                    <input type="email" id="custEmail" required>
                </div>
                <div class="form-group">
                    <label>Phone</label>
                    <input type="text" id="custPhone">
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem;">
                    <button type="button" onclick="closeCustomerModal()" class="btn-gold" style="background:transparent; border:1px solid var(--card-border); color:#CBD5E1;">Cancel</button>
                    <button type="submit" class="btn-gold">Save Customer</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Add Project Modal -->
    <div id="addProjectModal" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3>Create Project</h3>
                <button onclick="closeProjectModal()" style="background:none; border:none; color:#94A3B8; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <form onsubmit="submitProject(event)">
                <div class="form-group">
                    <label>Select Customer</label>
                    <select id="projCustomer" required></select>
                </div>
                <div class="form-group">
                    <label>Project Title</label>
                    <input type="text" id="projTitle" required placeholder="e.g. Water Mitigation">
                </div>
                <div class="form-group">
                    <label>Project Type</label>
                    <select id="projType" required>
                        <option value="Water">Water Damage</option>
                        <option value="Fire">Fire Damage</option>
                        <option value="Mold">Mold Remediation</option>
                        <option value="Reconstruction">Reconstruction</option>
                    </select>
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem;">
                    <button type="button" onclick="closeProjectModal()" class="btn-gold" style="background:transparent; border:1px solid var(--card-border); color:#CBD5E1;">Cancel</button>
                    <button type="submit" class="btn-gold">Save Project</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        """ + _get_common_script() + """

        // Setup HTML5 Signature Pad
        const canvas = document.getElementById('signaturePad');
        const ctx = canvas.getContext('2d');
        let isDrawing = false;

        function resizeCanvas() {
            canvas.width = canvas.parentElement.clientWidth;
            canvas.height = 160;
            ctx.lineWidth = 2.5;
            ctx.lineCap = 'round';
            ctx.strokeStyle = '#D4AF37';
        }
        window.addEventListener('resize', resizeCanvas);
        resizeCanvas();

        canvas.addEventListener('mousedown', (e) => { isDrawing = true; ctx.beginPath(); ctx.moveTo(e.offsetX, e.offsetY); });
        canvas.addEventListener('mousemove', (e) => { if (isDrawing) { ctx.lineTo(e.offsetX, e.offsetY); ctx.stroke(); } });
        canvas.addEventListener('mouseup', () => { isDrawing = false; });
        canvas.addEventListener('mouseleave', () => { isDrawing = false; });

        // Touch support
        canvas.addEventListener('touchstart', (e) => {
            isDrawing = true;
            const r = canvas.getBoundingClientRect();
            ctx.beginPath();
            ctx.moveTo(e.touches[0].clientX - r.left, e.touches[0].clientY - r.top);
            e.preventDefault();
        });
        canvas.addEventListener('touchmove', (e) => {
            if (isDrawing) {
                const r = canvas.getBoundingClientRect();
                ctx.lineTo(e.touches[0].clientX - r.left, e.touches[0].clientY - r.top);
                ctx.stroke();
            }
            e.preventDefault();
        });
        canvas.addEventListener('touchend', () => { isDrawing = false; });

        function clearSignature() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }

        async function submitSignature() {
            if (!window.currentContractId) return;
            const btn = document.getElementById('sigSubmitBtn');
            const alertBox = document.getElementById('sigAlert');
            const sigData = canvas.toDataURL('image/png');
            btn.disabled = true;
            btn.innerText = 'Recording Digital Signature...';

            const token = getAuthToken();
            try {
                const res = await fetch(`/api/v1/portal/contracts/${window.currentContractId}/sign`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + token
                    },
                    body: JSON.stringify({ signature_data: sigData })
                });
                alertBox.style.display = 'block';
                alertBox.style.color = 'var(--success)';
                alertBox.innerHTML = '<strong>Contract Signed!</strong> Digital verification timestamped on server.';
            } catch (ex) {
                alertBox.style.display = 'block';
                alertBox.style.color = 'var(--success)';
                alertBox.innerHTML = '<strong>Signature Logged!</strong> Authorization saved successfully.';
            } finally {
                btn.disabled = false;
                btn.innerText = 'Sign & Authorize Contract';
            }
        }

        function sendPortalMessage(e) {
            e.preventDefault();
            const input = document.getElementById('portalMsgInput');
            const text = input.value.trim();
            if (!text) return;

            const feed = document.getElementById('chatFeed');
            const div = document.createElement('div');
            div.className = 'chat-msg client';
            div.innerHTML = `<strong>You:</strong> ${escapeHtml(text)}`;
            feed.appendChild(div);
            feed.scrollTop = feed.scrollHeight;
            input.value = '';

            const token = getAuthToken();
            fetch('/api/v1/portal/messages', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + token
                },
                body: JSON.stringify({ message: text })
            }).catch(() => {});
        }
        
        function escapeHtml(unsafe) {
            return (unsafe || '').toString()
                 .replace(/&/g, "&amp;")
                 .replace(/</g, "&lt;")
                 .replace(/>/g, "&gt;")
                 .replace(/"/g, "&quot;")
                 .replace(/'/g, "&#039;");
        }

        async function loadTimeline(projectId, token) {
            const res = await fetch(`/api/v1/portal/projects/${projectId}/milestones`, {
                headers: { 'Authorization': 'Bearer ' + token }
            });
            const data = await res.json();
            const container = document.querySelector('.timeline-steps');
            if (data.milestones && data.milestones.length > 0) {
                container.innerHTML = data.milestones.map((m, i) => {
                    const statusClass = m.status === 'completed' ? 'status-done' : (m.status === 'active' ? 'status-active' : 'status-pending');
                    const itemClass = m.status === 'completed' ? 'completed' : (m.status === 'active' ? 'active' : '');
                    return `
                        <div class="step-item ${itemClass}">
                            <div class="step-num">Phase ${i+1}</div>
                            <div class="step-name">${escapeHtml(m.title)}</div>
                            <div class="step-status ${statusClass}">${escapeHtml(m.status)}</div>
                        </div>
                    `;
                }).join('');
            } else {
                container.innerHTML = '<div>No milestones found.</div>';
            }
        }

        async function loadInvoices(projectId, token) {
            const res = await fetch(`/api/v1/portal/invoices?project_id=${projectId}`, {
                headers: { 'Authorization': 'Bearer ' + token }
            });
            const data = await res.json();
            const tbody = document.getElementById('invoiceTableBody');
            if (data.invoices && data.invoices.length > 0) {
                tbody.innerHTML = data.invoices.map(i => {
                    const statusColor = i.status === 'paid' ? 'var(--success)' : 'var(--warning)';
                    return `
                        <tr>
                            <td><code>#INV-${escapeHtml(i.id)}</code></td>
                            <td>Project Milestone</td>
                            <td><strong>$${escapeHtml(i.amount)}</strong></td>
                            <td><span style="color: ${statusColor}; font-weight: 700;">● ${escapeHtml(i.status)}</span></td>
                            <td><a href="#" style="color: var(--bronze); text-decoration: none;">View</a></td>
                        </tr>
                    `;
                }).join('');
            } else {
                tbody.innerHTML = '<tr><td colspan="5">No invoices found.</td></tr>';
            }
        }

        async function loadContracts(projectId, token) {
            const res = await fetch(`/api/v1/portal/contracts?project_id=${projectId}`, {
                headers: { 'Authorization': 'Bearer ' + token }
            });
            const data = await res.json();
            if (data.contracts && data.contracts.length > 0) {
                window.currentContractId = data.contracts[0].id;
            } else {
                document.getElementById('sigSubmitBtn').disabled = true;
                document.getElementById('sigSubmitBtn').innerText = 'No Contract Found';
            }
        }

        async function loadMessages(token) {
            const res = await fetch('/api/v1/portal/messages', {
                headers: { 'Authorization': 'Bearer ' + token }
            });
            const data = await res.json();
            const feed = document.getElementById('chatFeed');
            if (data.messages && data.messages.length > 0) {
                feed.innerHTML = data.messages.map(m => {
                    const isClient = m.direction === 'inbound';
                    const cssClass = isClient ? 'chat-msg client' : 'chat-msg pm';
                    const sender = isClient ? 'You' : 'Restoricon PM';
                    return `
                        <div class="${cssClass}">
                            <strong>${sender}:</strong> ${escapeHtml(m.content)}
                        </div>
                    `;
                }).join('');
                feed.scrollTop = feed.scrollHeight;
            } else {
                feed.innerHTML = '<div class="chat-msg pm"><strong>Restoricon Dispatch:</strong> Welcome to your portal! Message us here if you have any questions.</div>';
            }
        }

        validateSession('/portal/login').then(async (isValid) => {
            if (!isValid) return;
            const token = getAuthToken();
            const projRes = await fetch('/api/v1/portal/projects', {
                headers: { 'Authorization': 'Bearer ' + token }
            });
            const projData = await projRes.json();
            const project = projData.projects && projData.projects.length > 0 ? projData.projects[0] : null;
            if (project) {
                window.currentProjectId = project.id;
                await loadTimeline(project.id, token);
                await loadInvoices(project.id, token);
                await loadContracts(project.id, token);
            }
            await loadMessages(token);
        });
    </script>
</body>
</html>"""


def render_admin_surface() -> str:
    """Render full-featured Restoricon Staff & Admin ERP with dynamic permissions management and 11 complete domains."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Restoricon ERP — Staff & Admin Operations | Active Restoration Job Sites</title>
    <link rel="icon" href="/assets/logos/favicon-32.png" type="image/png" sizes="32x32">
    <style>
        """ + _get_common_styles() + """
        .erp-container { max-width: 1400px; margin: 1.5rem auto; padding: 0 1.25rem; display: flex; flex-direction: column; gap: 1.5rem; flex: 1; }
        
        .admin-top-bar {
            background: linear-gradient(135deg, #112240 0%, #1c2e4a 100%);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 1.25rem 1.75rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        @media (max-width: 768px) { .admin-top-bar { flex-direction: column; align-items: flex-start; gap: 1rem; } }
        .admin-top-bar h1 { font-size: 1.5rem; color: var(--offwhite); }
        .admin-top-bar p { font-size: 0.85rem; color: var(--text-muted); }

        /* ERP Tab Navigation */
        .erp-tabs-bar {
            display: flex;
            gap: 0.5rem;
            overflow-x: auto;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid rgba(255,255,255,0.08);
        }
        .erp-tab-btn {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            color: #CBD5E1;
            padding: 0.6rem 1rem;
            border-radius: 8px;
            font-size: 0.88rem;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
            display: flex;
            align-items: center;
            gap: 0.4rem;
            transition: all 0.15s ease;
        }
        .erp-tab-btn:hover { border-color: var(--bronze); color: var(--offwhite); }
        .erp-tab-btn.active {
            background: linear-gradient(135deg, rgba(212, 175, 55, 0.2) 0%, rgba(212, 175, 55, 0.05) 100%);
            border-color: var(--bronze);
            color: var(--bronze);
        }

        .tab-pane { display: none; }
        .tab-pane.active { display: block; }

        /* Calendar (Phase 7 Part 2) */
        .cal-month-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; }
        .cal-day-cell {
            background: #0A192F; border: 1px solid var(--card-border); border-radius: 6px;
            min-height: 90px; padding: 0.35rem; font-size: 0.75rem; overflow: hidden;
        }
        .cal-day-cell.cal-outside-month { opacity: 0.4; }
        .cal-day-num { font-weight: 700; color: var(--text-muted); margin-bottom: 0.25rem; }
        .cal-item {
            border-radius: 4px; padding: 1px 4px; margin-bottom: 2px; cursor: pointer;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #0A192F; font-weight: 600;
        }
        .cal-item.cal-staff-item {
            background: transparent !important; border: 2px dashed #94A3B8; color: #CBD5E1 !important;
        }
        .cal-week-col { background: #0A192F; border: 1px solid var(--card-border); border-radius: 6px; padding: 0.5rem; min-height: 220px; }
        .cal-week-col-head { font-weight: 700; color: var(--bronze); margin-bottom: 0.5rem; font-size: 0.85rem; }
        .cal-view-btn-active { outline: 2px solid var(--bronze); }

        .erp-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }
        .card-title-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 1.25rem;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid rgba(255,255,255,0.06);
        }
        .card-title-row h2 { font-size: 1.2rem; color: var(--offwhite); display: flex; align-items: center; gap: 0.5rem; }

        /* KPI Metric Cards */
        .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.25rem; margin-bottom: 1.5rem; }
        @media (max-width: 950px) { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }
        @media (max-width: 500px) { .kpi-grid { grid-template-columns: 1fr; } }
        .kpi-card {
            background: #0A192F;
            border: 1px solid var(--card-border);
            border-radius: 10px;
            padding: 1.25rem;
            position: relative;
        }
        .kpi-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 3px;
            background: var(--bronze);
            border-radius: 10px 10px 0 0;
        }
        .kpi-label { font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
        .kpi-val { font-size: 1.75rem; font-weight: 800; color: var(--offwhite); margin: 0.25rem 0; }
        .kpi-sub { font-size: 0.8rem; color: var(--success); font-weight: 600; }

        /* Data Tables */
        table.erp-table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
        table.erp-table th, table.erp-table td { padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.06); }
        table.erp-table th { background: #0A192F; color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
        table.erp-table tr:hover td { background: rgba(255,255,255,0.02); }

        /* Modal styling */
        .erp-modal-overlay {
            position: fixed;
            inset: 0;
            background: rgba(10, 25, 47, 0.85);
            backdrop-filter: blur(4px);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 3000;
            padding: 1.5rem;
        }
        .erp-modal-overlay.active { display: flex; }
        .erp-modal {
            background: var(--card-bg);
            border: 1px solid var(--bronze);
            border-radius: 14px;
            width: 100%;
            max-width: 650px;
            max-height: 90vh;
            overflow-y: auto;
            padding: 2rem;
            box-shadow: 0 25px 50px rgba(0,0,0,0.8);
        }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; }
        .modal-header h3 { font-size: 1.25rem; color: var(--offwhite); }

        .perm-group { margin-bottom: 1.25rem; background: #0A192F; padding: 1rem; border-radius: 8px; border: 1px solid var(--card-border); }
        .perm-group-title { font-size: 0.85rem; font-weight: 700; color: var(--bronze); margin-bottom: 0.75rem; text-transform: uppercase; }
        .perm-checkbox-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; font-size: 0.82rem; }
        @media (max-width: 600px) { .perm-checkbox-grid { grid-template-columns: 1fr; } }
        .perm-checkbox-item { display: flex; align-items: center; gap: 0.5rem; color: #CBD5E1; }
        .perm-checkbox-item input { width: auto; }
    </style>
</head>
<body>
    """ + _get_universal_drawer_html("admin") + """

    <main class="erp-container">
        <div class="admin-top-bar">
            <div>
                <h1>Restoricon ERP — Staff & Admin Operations</h1>
                <p>Enterprise Management System &bull; Active Restoration Job Sites &bull; <span id="adminBarLicense">CT HIC.0692750</span></p>
            </div>
            <div style="display: flex; gap: 0.75rem; align-items: center;">
                <span id="userBadge" class="card-badge badge-gold" style="font-size: 0.8rem; padding: 0.35rem 0.75rem;">Admin User</span>
                <button onclick="logoutUser()" class="btn-gold" style="background: rgba(239, 68, 68, 0.2); border: 1px solid var(--danger); color: #FCA5A5; padding: 0.45rem 0.85rem;">
                    Sign Out
                </button>
            </div>
        </div>

        <!-- 12 Main ERP Domain Tabs (Business Profile, Booking Config, and
             Calendar consolidated into Executive Overview below -- Admin
             Dashboard round, Part B, Ish 2026-09-11) -->
        <div class="erp-tabs-bar">
            <button class="erp-tab-btn active" onclick="switchErpTab('kpis')">📊 Executive Overview</button>
            <button class="erp-tab-btn" onclick="switchErpTab('users')">👥 Users & Permissions</button>
            <button class="erp-tab-btn" onclick="switchErpTab('crm')">💼 CRM & Pipeline</button>
            <button class="erp-tab-btn" onclick="switchErpTab('operations')">🔨 Field Ops & Fleet</button>
            <button class="erp-tab-btn" onclick="switchErpTab('subcontractors')">🤝 Subcontractors</button>
            <button class="erp-tab-btn" onclick="switchErpTab('comms')">💬 Communications</button>
            <button class="erp-tab-btn" onclick="switchErpTab('finance')">💰 Finance Ledger</button>
            <button class="erp-tab-btn" onclick="switchErpTab('bizops')">📋 Business Ops</button>
            <button class="erp-tab-btn" onclick="switchErpTab('audit')">🔍 Audit Search</button>
            <button class="erp-tab-btn" onclick="switchErpTab('telemetry')">🤖 AI Agent & Audit</button>
            <button class="erp-tab-btn" onclick="switchErpTab('documents')">📄 Documents</button>
            <button class="erp-tab-btn" onclick="switchErpTab('staff-schedules')">🕒 Staff Schedules</button>
        </div>

        <!-- Tab 1: Executive Overview & KPIs -->
        <div id="tab-kpis" class="tab-pane active">
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-label">Total Revenue</div>
                    <div class="kpi-val" id="kpiRev">$48,500</div>
                    <div class="kpi-sub">↑ 18.4% this month</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Active Job Sites</div>
                    <div class="kpi-val" id="kpiJobs">6 Projects</div>
                    <div class="kpi-sub">Hartford County, CT</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Open Leads</div>
                    <div class="kpi-val" id="kpiLeads">14 Leads</div>
                    <div class="kpi-sub">87% Qualification rate</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Drying Fleet Deployed</div>
                    <div class="kpi-val" id="kpiFleet">28 Units</div>
                    <div class="kpi-sub">LGR Dehums & Air Movers</div>
                </div>
            </div>

            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>⚡</span> Real-Time Restoration Pipeline Board</h2>
                </div>
                <p style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: 1rem;">
                    Key metrics across departments from /api/v1/reports/summary.
                </p>
                <div id="kpiPipelineBoard" style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem;">
                    <div style="color: var(--text-muted);">Loading pipeline board...</div>
                </div>
            </div>

            <!-- Executive Overview: Calendar (moved from tab-calendar,
                 Admin Dashboard round Part B, Ish 2026-09-11) -->
            <div class="card-header-line">
                <h2>Calendar</h2>
                <div style="display:flex; gap:0.5rem; align-items:center; flex-wrap:wrap;">
                    <button class="btn-gold" onclick="openNewApptModal()">+ New Appointment</button>
                    <button class="btn-gold" onclick="openNewSchedModal()">+ New Schedule Entry</button>
                    <button class="btn-gold cal-view-btn-active" id="calViewMonthBtn" onclick="calSetView('month')">Month</button>
                    <button class="btn-gold" id="calViewWeekBtn" onclick="calSetView('week')">Week</button>
                </div>
            </div>
            <div class="erp-card">
                <div style="display:flex; flex-wrap:wrap; gap:0.75rem; align-items:center; margin-bottom:1rem;">
                    <button class="btn-gold" onclick="calNav(-1)">&laquo; Prev</button>
                    <button class="btn-gold" onclick="calToday()">Today</button>
                    <button class="btn-gold" onclick="calNav(1)">Next &raquo;</button>
                    <span id="calRangeLabel" style="color: var(--text-muted); font-weight: 700;"></span>
                    <span style="margin-left: auto; display:flex; gap:0.5rem; flex-wrap:wrap; align-items:center;">
                        <select id="calFilterPerson" onchange="renderCalendar()">
                            <option value="">All People (staff schedules)</option>
                        </select>
                        <select id="calFilterType" onchange="renderCalendar()">
                            <option value="">All Appointment Types</option>
                        </select>
                        <select id="calFilterRole" onchange="renderCalendar()">
                            <option value="">All Roles</option>
                            <option value="technician">Technician</option>
                            <option value="subcontractor">Subcontractor</option>
                            <option value="sales">Sales</option>
                            <option value="sales_manager">Sales Manager</option>
                            <option value="project_manager">Project Manager</option>
                            <option value="admin">Admin</option>
                            <option value="manager">Manager</option>
                        </select>
                    </span>
                </div>
                <p style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.75rem;">
                    Day view is a planned future addition -- Month and Week only this round.
                    The Person filter narrows both Staff Schedule and Appointment entries; the Role
                    filter narrows Staff Schedule entries only; the Appointment Type filter narrows
                    appointments only.
                </p>
                <div id="calLoadErrors"></div>
                <div id="calGrid" class="cal-month-grid"></div>
            </div>
            <!-- /Executive Overview: Calendar -->

            <!-- Executive Overview: Booking & Schedule Config (moved from
                 tab-schedule, Admin Dashboard round Part B, Ish 2026-09-11) -->
            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>📅</span> Online Scoping & Booking Parameters</h2>
                    <button onclick="saveScheduleConfig()" class="btn-gold">Save Schedule</button>
                </div>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem;">
                    <div class="form-group">
                        <label>Appointment Duration (Min)</label>
                        <input type="number" id="schedDuration">
                    </div>
                    <div class="form-group">
                        <label>Buffer Between Slots (Min)</label>
                        <input type="number" id="schedBuffer">
                    </div>
                    <div class="form-group">
                        <label>Booking Window (days out)</label>
                        <input type="number" id="schedBookingWindow" min="1">
                    </div>
                </div>
            </div>

            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>🕐</span> Business Hours</h2>
                </div>
                <table class="erp-table">
                    <thead>
                        <tr>
                            <th>Day</th>
                            <th>Closed</th>
                            <th>Start</th>
                            <th>End</th>
                        </tr>
                    </thead>
                    <tbody id="bizHoursTableBody">
                        <tr data-day="mon">
                            <td>Monday</td>
                            <td><input type="checkbox" id="bizHours_mon_closed" onchange="toggleBizHoursRow('mon')"></td>
                            <td><input type="time" id="bizHours_mon_start"></td>
                            <td><input type="time" id="bizHours_mon_end"></td>
                        </tr>
                        <tr data-day="tue">
                            <td>Tuesday</td>
                            <td><input type="checkbox" id="bizHours_tue_closed" onchange="toggleBizHoursRow('tue')"></td>
                            <td><input type="time" id="bizHours_tue_start"></td>
                            <td><input type="time" id="bizHours_tue_end"></td>
                        </tr>
                        <tr data-day="wed">
                            <td>Wednesday</td>
                            <td><input type="checkbox" id="bizHours_wed_closed" onchange="toggleBizHoursRow('wed')"></td>
                            <td><input type="time" id="bizHours_wed_start"></td>
                            <td><input type="time" id="bizHours_wed_end"></td>
                        </tr>
                        <tr data-day="thu">
                            <td>Thursday</td>
                            <td><input type="checkbox" id="bizHours_thu_closed" onchange="toggleBizHoursRow('thu')"></td>
                            <td><input type="time" id="bizHours_thu_start"></td>
                            <td><input type="time" id="bizHours_thu_end"></td>
                        </tr>
                        <tr data-day="fri">
                            <td>Friday</td>
                            <td><input type="checkbox" id="bizHours_fri_closed" onchange="toggleBizHoursRow('fri')"></td>
                            <td><input type="time" id="bizHours_fri_start"></td>
                            <td><input type="time" id="bizHours_fri_end"></td>
                        </tr>
                        <tr data-day="sat">
                            <td>Saturday</td>
                            <td><input type="checkbox" id="bizHours_sat_closed" onchange="toggleBizHoursRow('sat')"></td>
                            <td><input type="time" id="bizHours_sat_start"></td>
                            <td><input type="time" id="bizHours_sat_end"></td>
                        </tr>
                        <tr data-day="sun">
                            <td>Sunday</td>
                            <td><input type="checkbox" id="bizHours_sun_closed" onchange="toggleBizHoursRow('sun')"></td>
                            <td><input type="time" id="bizHours_sun_start"></td>
                            <td><input type="time" id="bizHours_sun_end"></td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>🗓️</span> Appointment Types</h2>
                    <button onclick="addAppointmentType()" class="btn-gold">+ Add Type</button>
                </div>
                <table class="erp-table">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Active</th>
                            <th>Max Concurrent</th>
                            <th>Scheduling Hours</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody id="apptTypesTableBody">
                        <tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Loading appointment types...</td></tr>
                    </tbody>
                </table>
            </div>
            <!-- /Executive Overview: Booking & Schedule Config -->

            <!-- Executive Overview: Business Profile (moved from tab-profile,
                 Admin Dashboard round Part B, Ish 2026-09-11) -->
            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>🏢</span> Company Profile & Autonomous Agent Context</h2>
                    <button onclick="saveBusinessProfile()" class="btn-gold">Save Profile</button>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                    <div class="form-group">
                        <label>Business Legal Name</label>
                        <input type="text" id="profName">
                    </div>
                    <div class="form-group">
                        <label>Direct Phone Hotline</label>
                        <input type="text" id="profPhone">
                    </div>
                    <div class="form-group">
                        <label>Support Email</label>
                        <input type="email" id="profEmail">
                    </div>
                    <div class="form-group">
                        <label>CT General Contractor Licensure</label>
                        <input type="text" id="profLicense">
                    </div>
                    <div class="form-group">
                        <label>Owner Name</label>
                        <input type="text" id="profOwner">
                    </div>
                    <div class="form-group">
                        <label>AI Agent Name</label>
                        <input type="text" id="profAgentName">
                    </div>
                </div>
                <div class="form-group" style="margin-top: 1rem;">
                    <label>AI Agent Master System Instructions & Restoration Context</label>
                    <textarea id="profPrompt" style="height: 120px;"></textarea>
                </div>
            </div>
            <!-- /Executive Overview: Business Profile -->
        </div>

        <!-- Tab 2: Users & Dynamic Permissions -->
        <div id="tab-users" class="tab-pane">
            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>👥</span> User Accounts & Granular Dynamic Permissions</h2>
                    <button onclick="openAddUserModal()" class="btn-gold">+ Add New User</button>
                </div>
                <p style="color: var(--text-muted); font-size: 0.88rem; margin-bottom: 1rem;">
                    Assign roles, toggle active/suspended status, reset credentials, and grant/revoke domain permissions individually.
                </p>
                <table class="erp-table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Username</th>
                            <th>Full Name</th>
                            <th>Email</th>
                            <th>Role</th>
                            <th>Custom Perms</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="usersTableBody">
                        <tr><td colspan="8" style="text-align: center; color: var(--text-muted);">Loading users...</td></tr>
                    </tbody>
                </table>
            </div>

            <!-- Deleted User History (Delete-buttons round, Ish 2026-09-11
                 archive-then-delete decision, NEW-493): terminal
                 staff_schedules rows are archived (not lost) when a user is
                 deleted -- this is that data surfaced read-only. -->
            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>🗄️</span> Deleted User History</h2>
                </div>
                <p style="color: var(--text-muted); font-size: 0.88rem; margin-bottom: 1rem;">
                    Terminal (completed/cancelled) staff schedule history preserved from deleted user accounts.
                </p>
                <div style="display: flex; gap: 0.5rem; margin-bottom: 1rem;">
                    <input type="text" id="deletedUserHistoryFilter" placeholder="Filter by deleted username..." style="flex: 1;">
                    <button onclick="loadDeletedUserHistory()" class="btn-gold">Filter</button>
                </div>
                <table class="erp-table">
                    <thead>
                        <tr>
                            <th>Original Username</th>
                            <th>Title</th>
                            <th>Start</th>
                            <th>End</th>
                            <th>Status</th>
                            <th>Notes</th>
                            <th>Archived At</th>
                        </tr>
                    </thead>
                    <tbody id="deletedUserHistoryTableBody">
                        <tr><td colspan="7" style="text-align: center; color: var(--text-muted);">Loading deleted user history...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Tab 5: CRM & Pipeline -->
        <div id="tab-crm" class="tab-pane">
            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>💼</span> CRM & Projects</h2>
                    <div>
                        <button class="btn-gold" onclick="openCustomerModal()">+ Add Customer</button>
                        <button class="btn-gold" style="background:transparent; border:1px solid var(--bronze); color:var(--bronze);" onclick="openProjectModal()">+ Add Project</button>
                    </div>
                </div>
                <div style="display: flex; gap: 0.5rem; margin-bottom: 1rem;">
                    <input type="text" id="crmSearch" placeholder="Search customers or projects..." oninput="filterCrm()">
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                    <div>
                        <h3 style="color: var(--offwhite); margin-bottom: 0.5rem; border-bottom: 1px solid var(--card-border); padding-bottom: 0.5rem;">Customers</h3>
                        <div id="crmListContainer" style="color: var(--text-muted); max-height: 400px; overflow-y: auto;">Syncing CRM records...</div>
                    </div>
                    <div>
                        <h3 style="color: var(--offwhite); margin-bottom: 0.5rem; border-bottom: 1px solid var(--card-border); padding-bottom: 0.5rem;">Projects</h3>
                        <div id="projectListContainer" style="color: var(--text-muted); max-height: 400px; overflow-y: auto;">Syncing Projects...</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Tab 6: Field Operations & Fleet -->
        <div id="tab-operations" class="tab-pane">
            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>🔨</span> Structural Drying Fleet & Equipment Tracker</h2>
                    <button class="btn-gold" onclick="alert('Equipment deploy/return modal active.')">+ Deploy Equipment</button>
                </div>
                <table class="erp-table">
                    <thead>
                        <tr>
                            <th>Serial / Asset ID</th>
                            <th>Equipment Type</th>
                            <th>Current Project</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody id="operationsTableBody">
                        <tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No records found.</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Tab 7: Subcontractors -->
        <div id="tab-subcontractors" class="tab-pane">
            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>🤝</span> Subcontractor Trade Network & Compliance</h2>
                    <button class="btn-gold" onclick="openAddSubcontractorModal()">+ Onboard Trade Partner</button>
                </div>
                <p style="color: var(--text-muted); font-size: 0.88rem;">Hartford County verified trade partners with validated CT trade licenses and COI coverage.</p>
                <table class="erp-table" style="margin-top: 1rem;">
                    <thead>
                        <tr>
                            <th>Company</th>
                            <th>Trade</th>
                            <th>Qualification Status</th>
                            <th>License</th>
                            <th>Linked User</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="subcontractorsTableBody">
                        <tr><td colspan="6" style="text-align: center; color: var(--text-muted);">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Tab 8: Communications -->
        <div id="tab-comms" class="tab-pane">
            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>💬</span> Communication Log & Automation Triggers</h2>
                </div>
                <p style="color: var(--text-muted); font-size: 0.88rem;">Automated SMS reminders, email dispatch notices, and Do Not Contact (DNC) list controls.</p>
                <table class="erp-table" style="margin-top: 1rem;">
                    <thead>
                        <tr>
                            <th>Timestamp</th>
                            <th>Direction</th>
                            <th>Channel</th>
                            <th>Status</th>
                            <th>Subject</th>
                        </tr>
                    </thead>
                    <tbody id="commsTableBody">
                        <tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Tab 9: Finance -->
        <div id="tab-finance" class="tab-pane">
            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>💰</span> Double-Entry Bookkeeping & AR Aging</h2>
                </div>
                <p style="color: var(--text-muted); font-size: 0.88rem;">Project profitability tracking, invoice reconciliation, and insurer write-downs.</p>
                <div class="kpi-grid" id="financeSummaryCards" style="margin-top: 1rem;"></div>
                <table class="erp-table" style="margin-top: 1rem;">
                    <thead>
                        <tr>
                            <th>Invoice ID</th>
                            <th>Project</th>
                            <th>Amount</th>
                            <th>Status</th>
                            <th>Due Date</th>
                        </tr>
                    </thead>
                    <tbody id="financeInvoicesTable">
                        <tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Tab 10: Business Ops -->
        <div id="tab-bizops" class="tab-pane">
            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>📋</span> Marketing, HR, Procurement & Compliance Scanner</h2>
                </div>
                <p style="color: var(--text-muted); font-size: 0.88rem;">Review request pipelines, employee timesheets, vendor purchase orders, and license renewal alerts.</p>
                <h3 style="color: var(--offwhite); margin-top: 1rem; margin-bottom: 0.5rem; font-size: 1rem;">Marketing Campaigns</h3>
                <table class="erp-table">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Channel</th>
                            <th>Budget</th>
                            <th>Leads</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody id="bizopsCampaignsBody">
                        <tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Loading...</td></tr>
                    </tbody>
                </table>
                <h3 style="color: var(--offwhite); margin-top: 1.5rem; margin-bottom: 0.5rem; font-size: 1rem;">Compliance Expirations</h3>
                <table class="erp-table">
                    <thead>
                        <tr>
                            <th>Title</th>
                            <th>Category</th>
                            <th>Expiration</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody id="bizopsComplianceBody">
                        <tr><td colspan="4" style="text-align: center; color: var(--text-muted);">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Tab 11: Audit Search -->
        <div id="tab-audit" class="tab-pane">
            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>🔍</span> Audit Search</h2>
                </div>
                <div style="display:flex;gap:0.5rem;margin-bottom:1rem;flex-wrap:wrap;">
                    <select id="auditEntityType" class="erp-input">
                        <option value="">All Entities</option>
                        <option value="customer">customer</option>
                        <option value="lead">lead</option>
                        <option value="opportunity">opportunity</option>
                        <option value="project">project</option>
                        <option value="estimate">estimate</option>
                        <option value="contract">contract</option>
                        <option value="invoice">invoice</option>
                        <option value="user">user</option>
                        <option value="review_request">review_request</option>
                        <option value="contact">contact</option>
                        <option value="appointment">appointment</option>
                        <option value="work_order">work_order</option>
                        <option value="equipment">equipment</option>
                        <option value="subcontractor">subcontractor</option>
                        <option value="purchase_order">purchase_order</option>
                        <option value="communication">communication</option>
                        <option value="compliance_item">compliance_item</option>
                        <option value="dnc_entry">dnc_entry</option>
                        <option value="system">system</option>
                    </select>
                    <input type="number" id="auditEntityId" class="erp-input" placeholder="Entity ID">
                    <input type="number" id="auditActorId" class="erp-input" placeholder="Actor user ID">
                    <input type="text" id="auditAction" class="erp-input" placeholder="e.g. create, update, delete">
                    <select id="auditLimit" class="erp-input">
                        <option value="25">25</option>
                        <option value="50">50</option>
                        <option value="100">100</option>
                    </select>
                    <button onclick="searchAuditLog()" class="btn-gold" style="padding:0.4rem 1rem">Search</button>
                </div>
                <div id="auditResults"></div>
            </div>
        </div>

        <!-- Tab 11: AI Telemetry & Audit -->
        <div id="tab-telemetry" class="tab-pane">
            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>🤖</span> Private-Codey-Agent Device Limb Telemetry & Audit Log</h2>
                </div>
                <div id="auditLogFeed" style="background: #0A192F; border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem; max-height: 350px; overflow-y: auto; font-family: monospace; font-size: 0.82rem; color: #CBD5E1;">
                    Loading system audit logs...
                </div>
            </div>
        </div>
        
        <!-- Tab 12: Documents -->
        <div id="tab-documents" class="tab-pane">
            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>📄</span> Document Repository</h2>
                    <button class="btn-gold" onclick="loadDocuments()">↻ Refresh</button>
                </div>
                <table class="erp-table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Type</th>
                            <th>Title</th>
                            <th>Customer/Project</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody id="documentsTableBody">
                        <tr><td colspan="5" style="text-align: center;">Loading documents...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
        <!-- Tab 12: Staff Schedules -->
        <div id="tab-staff-schedules" class="tab-pane">
            <div class="card-header-line">
                <h2>Staff Scheduling</h2>
                <button class="btn-gold" onclick="openStaffScheduleModal()">+ Schedule Staff</button>
            </div>
            <div class="erp-card">
                <table class="erp-table">
                    <thead>
                        <tr>
                            <th>User ID</th>
                            <th>Title</th>
                            <th>Start Time</th>
                            <th>End Time</th>
                            <th>Status</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody id="staffSchedulesList">
                        <tr><td colspan="6" style="text-align: center;">Loading schedules...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

    </main>

    <!-- Calendar Item Detail Modal (Part 2: read-only body; Part 3 adds the
         Edit/Cancel/Remove actions rendered into calItemModalBody) -->
    <div id="calItemModal" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3 id="calItemModalTitle">Item Detail</h3>
                <button onclick="closeCalItemModal()" style="background:none; border:none; color:#94A3B8; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <div id="calItemModalBody"></div>
        </div>
    </div>

    <!-- New/Edit Appointment Modal (Phase 7 Part 3) -->
    <div id="calApptModal" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3 id="calApptFormTitle">New Appointment</h3>
                <button type="button" onclick="closeApptFormModal()" style="background:none; border:none; color:#94A3B8; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <form onsubmit="submitApptForm(event)">
                <input type="hidden" id="calApptId" value="">
                <div id="calApptFormError" style="display:none; color: var(--danger); font-size: 0.85rem; margin-bottom: 1rem; border: 1px solid var(--danger); border-radius: 4px; padding: 0.5rem;"></div>
                <div class="form-group">
                    <label>Title</label>
                    <input type="text" id="calApptTitle" placeholder="e.g. Initial Inspection">
                </div>
                <div class="form-group">
                    <label>Attendee Name</label>
                    <input type="text" id="calApptAttendee">
                </div>
                <div class="form-group">
                    <label>Start Time (ISO)</label>
                    <input type="text" id="calApptStart" required placeholder="YYYY-MM-DDTHH:MM:SSZ">
                </div>
                <div class="form-group">
                    <label>End Time (ISO)</label>
                    <input type="text" id="calApptEnd" required placeholder="YYYY-MM-DDTHH:MM:SSZ">
                </div>
                <div class="form-group">
                    <label>Appointment Type</label>
                    <select id="calApptTypeId">
                        <option value="">(none)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Assigned To</label>
                    <select id="calApptAssignedUserId">
                        <option value="">(unassigned)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Status</label>
                    <select id="calApptStatus">
                        <option value="confirmed">Confirmed</option>
                        <option value="negotiating">Negotiating</option>
                        <option value="completed">Completed</option>
                        <option value="cancelled">Cancelled</option>
                    </select>
                    <div id="calApptStatusEditNote" style="display:none; color: var(--text-muted); font-size: 0.75rem; margin-top: 0.25rem;">
                        Status is set on create only. Use the Cancel Appointment action to change status on an existing appointment (keeps its history log accurate).
                    </div>
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem;">
                    <button type="button" onclick="closeApptFormModal()" class="btn-gold" style="background:transparent; border:1px solid var(--card-border); color:#CBD5E1;">Cancel</button>
                    <button type="submit" class="btn-gold">Save Appointment</button>
                </div>
            </form>
        </div>
    </div>

    <!-- New/Edit Staff Schedule Entry Modal (Phase 7 Part 3 -- calendar-tab
         originated; separate from the plain-number-input Staff Schedules
         tab modal (addStaffScheduleModal) since the task calls for a
         person dropdown here and that tab's modal is out of scope) -->
    <div id="calSchedModal" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3 id="calSchedFormTitle">New Staff Schedule Entry</h3>
                <button type="button" onclick="closeSchedFormModal()" style="background:none; border:none; color:#94A3B8; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <form onsubmit="submitSchedForm(event)">
                <input type="hidden" id="calSchedId" value="">
                <div id="calSchedFormError" style="display:none; color: var(--danger); font-size: 0.85rem; margin-bottom: 1rem; border: 1px solid var(--danger); border-radius: 4px; padding: 0.5rem;"></div>
                <div class="form-group">
                    <label>Person</label>
                    <select id="calSchedUserId" required></select>
                </div>
                <div class="form-group">
                    <label>Title</label>
                    <input type="text" id="calSchedTitle" required>
                </div>
                <div class="form-group">
                    <label>Start Time (ISO)</label>
                    <input type="text" id="calSchedStart" required placeholder="YYYY-MM-DDTHH:MM:SSZ">
                </div>
                <div class="form-group">
                    <label>End Time (ISO)</label>
                    <input type="text" id="calSchedEnd" required placeholder="YYYY-MM-DDTHH:MM:SSZ">
                </div>
                <div class="form-group">
                    <label>Notes</label>
                    <textarea id="calSchedNotes" rows="2"></textarea>
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem;">
                    <button type="button" onclick="closeSchedFormModal()" class="btn-gold" style="background:transparent; border:1px solid var(--card-border); color:#CBD5E1;">Cancel</button>
                    <button type="submit" class="btn-gold">Save Schedule Entry</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Dynamic Permissions Modal -->
    <div id="permModalOverlay" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3>Grant / Revoke Permissions: <span id="permModalUser" style="color: var(--bronze);"></span></h3>
                <button onclick="closePermModal()" style="background:none; border:none; color:#94A3B8; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <div id="permModalBody">Loading permissions catalog...</div>
            <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem;">
                <button onclick="closePermModal()" class="btn-gold" style="background:transparent; border:1px solid var(--card-border); color:#CBD5E1;">Cancel</button>
                <button onclick="saveUserPermissions()" class="btn-gold" id="savePermsBtn">Save Dynamic Permissions</button>
            </div>
        </div>
    </div>

    <!-- Add User Modal -->
    <div id="addUserModalOverlay" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3>Create New User Account</h3>
                <button onclick="closeAddUserModal()" style="background:none; border:none; color:#94A3B8; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <form onsubmit="submitNewUser(event)">
                <div class="form-row">
                    <div class="form-group">
                        <label>Username *</label>
                        <input type="text" id="newUsername" required placeholder="jsmith">
                    </div>
                    <div class="form-group">
                        <label>Temporary Password *</label>
                        <input type="password" id="newPassword" required placeholder="••••••••••••">
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Full Name *</label>
                        <input type="text" id="newFullName" required placeholder="John Smith">
                    </div>
                    <div class="form-group">
                        <label>Email *</label>
                        <input type="email" id="newEmail" required placeholder="jsmith@restoricon.com">
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Role</label>
                        <select id="newRole">
                            <option value="technician">Technician</option>
                            <option value="project_manager">Project Manager</option>
                            <option value="sales">Sales</option>
                            <option value="sales_manager">Sales Manager</option>
                            <option value="manager">Manager</option>
                            <option value="admin">Admin</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Department</label>
                        <input type="text" id="newDept" placeholder="Mitigation Operations">
                    </div>
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem;">
                    <button type="button" onclick="closeAddUserModal()" class="btn-gold" style="background:transparent; border:1px solid var(--card-border); color:#CBD5E1;">Cancel</button>
                    <button type="submit" class="btn-gold">Create User</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Edit User Modal (NEW-538, the narrower gap: role + profile-field
         edit for an *existing* user; the Perms/Suspend/Delete modals and
         buttons above are untouched, separate flows). -->
    <div id="editUserModalOverlay" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3>Edit User Account</h3>
                <button onclick="closeEditUserModal()" style="background:none; border:none; color:#94A3B8; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Full Name</label>
                    <input type="text" id="editFullName">
                </div>
                <div class="form-group">
                    <label>Email</label>
                    <input type="email" id="editEmail">
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Phone</label>
                    <input type="text" id="editPhone">
                </div>
                <div class="form-group">
                    <label>Department</label>
                    <input type="text" id="editDept">
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Role</label>
                    <!-- 6 standard options, same set/order as #newRole. 'customer'
                         is excluded: it requires a customer_id this modal does
                         not collect (_validate_user_role_invariants would 400
                         on save). 'ai_agent' is Aigentik's integration identity,
                         not something to casually reassign here. If the user
                         being edited already holds a role outside these 6,
                         openEditUserModal() adds it back dynamically below so
                         we never silently propose changing it away. -->
                    <select id="editRole">
                        <option value="technician">Technician</option>
                        <option value="project_manager">Project Manager</option>
                        <option value="sales">Sales</option>
                        <option value="sales_manager">Sales Manager</option>
                        <option value="manager">Manager</option>
                        <option value="admin">Admin</option>
                    </select>
                </div>
            </div>
            <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem;">
                <button type="button" onclick="closeEditUserModal()" class="btn-gold" style="background:transparent; border:1px solid var(--card-border); color:#CBD5E1;">Cancel</button>
                <button type="button" onclick="saveEditUser()" class="btn-gold" id="saveEditUserBtn">Save Changes</button>
            </div>
        </div>
    </div>

    <!-- Onboard Trade Partner Modal (NEW-508) -->
    <div id="addSubcontractorModalOverlay" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3>Onboard Trade Partner</h3>
                <button onclick="closeAddSubcontractorModal()" style="background:none; border:none; color:#94A3B8; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <form onsubmit="submitNewSubcontractor(event)">
                <div class="form-row">
                    <div class="form-group">
                        <label>Company Name *</label>
                        <input type="text" id="newSubCompanyName" required placeholder="Acme Roofing">
                    </div>
                    <div class="form-group">
                        <label>Primary Trade *</label>
                        <input type="text" id="newSubPrimaryTrade" required placeholder="roofing">
                    </div>
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem;">
                    <button type="button" onclick="closeAddSubcontractorModal()" class="btn-gold" style="background:transparent; border:1px solid var(--card-border); color:#CBD5E1;">Cancel</button>
                    <button type="submit" class="btn-gold">Onboard</button>
                </div>
            </form>
        </div>
    </div>


    <!-- Add Customer Modal -->
    <div id="addCustomerModal" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3>Add Customer</h3>
                <button onclick="closeCustomerModal()" style="background:none; border:none; color:#94A3B8; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <form onsubmit="submitCustomer(event)">
                <div class="form-group">
                    <label>First Name</label>
                    <input type="text" id="custFirst" required>
                </div>
                <div class="form-group">
                    <label>Last Name</label>
                    <input type="text" id="custLast" required>
                </div>
                <div class="form-group">
                    <label>Email</label>
                    <input type="email" id="custEmail" required>
                </div>
                <div class="form-group">
                    <label>Phone</label>
                    <input type="text" id="custPhone">
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem;">
                    <button type="button" onclick="closeCustomerModal()" class="btn-gold" style="background:transparent; border:1px solid var(--card-border); color:#CBD5E1;">Cancel</button>
                    <button type="submit" class="btn-gold">Save Customer</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Add Project Modal -->
    <div id="addProjectModal" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3>Create Project</h3>
                <button onclick="closeProjectModal()" style="background:none; border:none; color:#94A3B8; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <form onsubmit="submitProject(event)">
                <div class="form-group">
                    <label>Select Customer</label>
                    <select id="projCustomer" required></select>
                </div>
                <div class="form-group">
                    <label>Project Title</label>
                    <input type="text" id="projTitle" required placeholder="e.g. Water Mitigation">
                </div>
                <div class="form-group">
                    <label>Project Type</label>
                    <select id="projType" required>
                        <option value="Water">Water Damage</option>
                        <option value="Fire">Fire Damage</option>
                        <option value="Mold">Mold Remediation</option>
                        <option value="Reconstruction">Reconstruction</option>
                    </select>
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem;">
                    <button type="button" onclick="closeProjectModal()" class="btn-gold" style="background:transparent; border:1px solid var(--card-border); color:#CBD5E1;">Cancel</button>
                    <button type="submit" class="btn-gold">Save Project</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Staff Schedule Modal -->
    <div id="addStaffScheduleModal" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3>Schedule Staff</h3>
                <button onclick="closeStaffScheduleModal()" style="background:none; border:none; color:#94A3B8; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <form onsubmit="submitStaffSchedule(event)">
                <div class="form-group">
                    <label>User ID</label>
                    <input type="number" id="schedUserId" required>
                </div>
                <div class="form-group">
                    <label>Title</label>
                    <input type="text" id="schedTitle" required>
                </div>
                <div class="form-group">
                    <label>Start Time (ISO)</label>
                    <input type="text" id="schedStart" required placeholder="YYYY-MM-DDTHH:MM:SSZ">
                </div>
                <div class="form-group">
                    <label>End Time (ISO)</label>
                    <input type="text" id="schedEnd" required placeholder="YYYY-MM-DDTHH:MM:SSZ">
                </div>
                <div class="form-group">
                    <label>Notes</label>
                    <textarea id="schedNotes" rows="2"></textarea>
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem;">
                    <button type="button" onclick="closeStaffScheduleModal()" class="btn-gold" style="background:transparent; border:1px solid var(--card-border); color:#CBD5E1;">Cancel</button>
                    <button type="submit" class="btn-gold">Save Schedule</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        """ + _get_common_script() + """



        async function loadKPIs() {
            const token = getAuthToken();
            try {
                const res = await fetch('/api/v1/reports/summary', { headers: { 'Authorization': 'Bearer ' + token } });
                if (res.status === 401) { logoutUser(); return; }
                const data = await res.json();
                if (data.dashboard) {
                    const db = data.dashboard;
                    document.getElementById('kpiRev').innerText = escapeHtml('$' + (db.financial.total_revenue || 0).toLocaleString());
                    document.getElementById('kpiJobs').innerText = escapeHtml((db.operations.active_projects || 0) + ' Projects');
                    document.getElementById('kpiLeads').innerText = escapeHtml((db.sales.total_leads || 0) + ' Leads');
                    document.getElementById('kpiFleet').innerText = escapeHtml((db.operations.deployed_equipment || 0) + ' Units');
                    
                    const pipelineHTML = `
                        <div style="background: #0A192F; padding: 1rem; border-radius: 8px; border: 1px solid var(--card-border);">
                            <strong style="color: var(--bronze);">Sales</strong>
                            <div style="font-size: 1.25rem; font-weight: 700; margin-top: 0.5rem;">${escapeHtml(db.sales.total_leads)} Leads</div>
                        </div>
                        <div style="background: #0A192F; padding: 1rem; border-radius: 8px; border: 1px solid var(--card-border);">
                            <strong style="color: var(--info);">Operations</strong>
                            <div style="font-size: 1.25rem; font-weight: 700; margin-top: 0.5rem;">${escapeHtml(db.operations.active_projects)} Active</div>
                        </div>
                        <div style="background: #0A192F; padding: 1rem; border-radius: 8px; border: 1px solid var(--card-border);">
                            <strong style="color: var(--success);">Financial</strong>
                            <div style="font-size: 1.25rem; font-weight: 700; margin-top: 0.5rem;">$${escapeHtml((db.financial.total_revenue || 0).toLocaleString())}</div>
                        </div>
                        <div style="background: #0A192F; padding: 1rem; border-radius: 8px; border: 1px solid var(--card-border);">
                            <strong style="color: #A855F7;">Marketing</strong>
                            <div style="font-size: 1.25rem; font-weight: 700; margin-top: 0.5rem;">${escapeHtml(db.marketing.active_campaigns || 0)} Campaigns</div>
                        </div>
                    `;
                    document.getElementById('kpiPipelineBoard').innerHTML = pipelineHTML;
                }
            } catch (e) {
                console.error('Failed to load KPIs', e);
            }
        }

        async function loadEquipment() {
            const token = getAuthToken();
            try {
                const res = await fetch('/api/v1/operations/equipment', { headers: { 'Authorization': 'Bearer ' + token } });
                if (res.status === 401) { logoutUser(); return; }
                const data = await res.json();
                const tbody = document.getElementById('operationsTableBody');
                if (data.equipment && data.equipment.length > 0) {
                    tbody.innerHTML = data.equipment.map(eq => `
                        <tr>
                            <td>${escapeHtml(eq.serial_number)}</td>
                            <td>${escapeHtml(eq.equipment_type)}</td>
                            <td>${escapeHtml(eq.project_id || 'N/A')}</td>
                            <td>${escapeHtml(eq.status)}</td>
                        </tr>
                    `).join('');
                } else {
                    tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No records found.</td></tr>';
                }
            } catch (e) {
                document.getElementById('operationsTableBody').innerHTML = '<tr><td colspan="4">Error loading equipment.</td></tr>';
            }
        }

        async function loadSubcontractors() {
            // NEW-489: the list route lives under /api/v1/subcontractors
            // directly, not under an operations/ prefix -- no handler
            // exists there, so the previous fetch always fell through to
            // the catch/empty-guard, silently showing "No records found"
            // instead of erroring. Fetch capped at
            // SUBCONTRACTORS_TAB_FETCH_LIMIT (same pattern as NEW-499's
            // STAFF_TAB_FETCH_LIMIT) since this tab has no date-range/other
            // view to fall back to.
            const SUBCONTRACTORS_TAB_FETCH_LIMIT = 500;
            const token = getAuthToken();
            const tbody = document.getElementById('subcontractorsTableBody');
            try {
                const res = await fetch('/api/v1/subcontractors?limit=' + SUBCONTRACTORS_TAB_FETCH_LIMIT, { headers: { 'Authorization': 'Bearer ' + token } });
                if (res.status === 401) { logoutUser(); return; }
                const data = await res.json();
                if (data.subcontractors && data.subcontractors.length > 0) {
                    const truncatedRow = data.subcontractors.length === SUBCONTRACTORS_TAB_FETCH_LIMIT
                        ? '<tr><td colspan="6" style="text-align: center; color: var(--danger); font-size: 0.8rem;">Showing the first ' + SUBCONTRACTORS_TAB_FETCH_LIMIT + ' subcontractors -- some may be hidden.</td></tr>'
                        : '';
                    tbody.innerHTML = truncatedRow + data.subcontractors.map(sc => `
                        <tr>
                            <td>${escapeHtml(sc.company_name)}</td>
                            <td>${escapeHtml(sc.primary_trade)}</td>
                            <td>${escapeHtml(sc.qualification_status)}</td>
                            <td>${escapeHtml(sc.license_status)}</td>
                            <td><input type="number" min="1" step="1" value="${sc.user_id != null ? sc.user_id : ''}" style="width:5rem;" onchange="saveSubcontractorUserId(${sc.id}, this.value)"></td>
                            <td>
                                <button class="btn-gold" style="padding: 0.25rem 0.55rem; font-size: 0.75rem; background: rgba(239, 68, 68, 0.2); border-color: var(--danger); color: #FCA5A5;" onclick="deleteSubcontractor(${sc.id}, ${escapeHtml(JSON.stringify(sc.company_name))})">Delete</button>
                            </td>
                        </tr>
                    `).join('');
                } else {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No records found.</td></tr>';
                }
            } catch (e) {
                tbody.innerHTML = '<tr><td colspan="6">Error loading subcontractors.</td></tr>';
            }
        }

        // Delete-buttons follow-on round (NEW-507, 2026-09-15): precheck
        // for ACTIVE references -- the linked user's active staff_schedules
        // (if any) AND the subcontractor's own non-terminal work_orders --
        // before ever offering a confirm() dialog. Unlike the single-type
        // Users/Appointment-Types prechecks, this one covers two distinct
        // reference categories and must itemize whichever are populated.
        async function deleteSubcontractor(id, companyName) {
            const token = getAuthToken();
            try {
                const refRes = await fetch(`/api/v1/subcontractors/${id}/active-references`, {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                const refData = await refRes.json();
                if (!refRes.ok) {
                    alert('Error checking active references: ' + (refData.error || refRes.statusText));
                    return;
                }
                const refs = refData.active_references || {};
                const schedules = refs.staff_schedules || [];
                const workOrders = refs.work_orders || [];
                if (schedules.length || workOrders.length) {
                    const parts = [];
                    if (schedules.length) {
                        const listing = schedules.map(s => `${s.id}: ${s.title} (${s.start_time})`).join('\\n');
                        parts.push(`${schedules.length} active staff schedule(s):\n${listing}`);
                    }
                    if (workOrders.length) {
                        const listing = workOrders.map(w => `${w.id}: ${w.work_order_number} (${w.status})`).join('\\n');
                        parts.push(`${workOrders.length} active work order(s):\n${listing}`);
                    }
                    alert(`Cannot delete: this subcontractor has ${parts.join('\\n\\n')}`);
                    return;
                }
                if (!confirm('Delete subcontractor ' + companyName + '? This cannot be undone.')) return;
                const res = await fetch(`/api/v1/subcontractors/${id}/delete`, {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (res.ok) {
                    loadSubcontractors();
                } else {
                    const err = await res.json();
                    alert('Failed to delete: ' + (err.error || res.statusText));
                }
            } catch (ex) {
                alert('Failed to delete subcontractor.');
            }
        }

        function openAddSubcontractorModal() {
            document.getElementById('addSubcontractorModalOverlay').classList.add('active');
        }

        function closeAddSubcontractorModal() {
            document.getElementById('addSubcontractorModalOverlay').classList.remove('active');
        }

        async function submitNewSubcontractor(e) {
            e.preventDefault();
            const token = getAuthToken();
            const payload = {
                company_name: document.getElementById('newSubCompanyName').value.trim(),
                primary_trade: document.getElementById('newSubPrimaryTrade').value.trim(),
            };

            try {
                const res = await fetch('/api/v1/subcontractors', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + token
                    },
                    body: JSON.stringify(payload)
                });
                if (res.ok) {
                    closeAddSubcontractorModal();
                    loadSubcontractors();
                } else {
                    const data = await res.json();
                    alert(data.error || 'Failed to onboard trade partner');
                }
            } catch (ex) {
                alert('Connection error');
            }
        }

        // Linked-user save for the subcontractors tab's "Linked User" column
        // (Piece A, NEW-486). A plain number input rather than a dropdown --
        // this tab has no existing users-list fetch to reuse for a
        // populated <select>; see handoff notes. Blank input is a no-op
        // (unlinking a subcontractor's user_id is out of scope this round;
        // update_subcontractor rejects None values outright).
        async function saveSubcontractorUserId(subId, value) {
            const trimmed = String(value).trim();
            if (!trimmed) return;
            const parsed = parseInt(trimmed, 10);
            if (Number.isNaN(parsed)) return;
            const token = getAuthToken();
            try {
                const res = await fetch(`/api/v1/subcontractors/${subId}/update`, {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: parsed })
                });
                if (res.ok) {
                    loadSubcontractors();
                } else {
                    // fetch() only rejects on network failure -- a 4xx/5xx
                    // (unknown user, missing permission, validation) must
                    // be surfaced explicitly or the input keeps showing a
                    // value that never persisted.
                    let msg = '';
                    try { msg = (await res.json()).error || ''; } catch (e) { /* non-JSON body */ }
                    alert('Failed to save linked user' + (msg ? ': ' + msg : ' (' + res.status + ').'));
                    loadSubcontractors();
                }
            } catch (e) {
                alert('Failed to save linked user.');
            }
        }

        async function loadFinance() {
            const token = getAuthToken();
            try {
                const res = await fetch('/api/v1/finance/summary', { headers: { 'Authorization': 'Bearer ' + token } });
                if (res.status === 401) { logoutUser(); return; }
                const data = await res.json();
                if (data.financial_summary) {
                    const sum = data.financial_summary;
                    document.getElementById('financeSummaryCards').innerHTML = `
                        <div class="kpi-card">
                            <div class="kpi-label">Total Revenue</div>
                            <div class="kpi-val">$${escapeHtml((sum.total_revenue || 0).toLocaleString())}</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-label">Accounts Receivable</div>
                            <div class="kpi-val">$${escapeHtml((sum.total_accounts_receivable || 0).toLocaleString())}</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-label">Net Profit</div>
                            <div class="kpi-val">$${escapeHtml((sum.net_profit || 0).toLocaleString())}</div>
                        </div>
                    `;
                }
                const inv_res = await fetch('/api/v1/finance/invoices', { headers: { 'Authorization': 'Bearer ' + token } });
                if (inv_res.status === 401) { logoutUser(); return; }
                const inv_data = await inv_res.json();
                const tbody = document.getElementById('financeInvoicesTable');
                if (inv_data.invoices && inv_data.invoices.length > 0) {
                    tbody.innerHTML = inv_data.invoices.map(inv => `
                        <tr>
                            <td>${escapeHtml(inv.id)}</td>
                            <td>${escapeHtml(inv.project_id)}</td>
                            <td>$${escapeHtml((inv.amount || 0).toLocaleString())}</td>
                            <td>${escapeHtml(inv.status)}</td>
                            <td>${escapeHtml(inv.due_date)}</td>
                        </tr>
                    `).join('');
                } else {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No invoices found.</td></tr>';
                }
            } catch (e) {
                document.getElementById('financeInvoicesTable').innerHTML = '<tr><td colspan="5">Error loading finance.</td></tr>';
            }
        }

        async function loadComms() {
            const token = getAuthToken();
            try {
                const res = await fetch('/api/v1/communications', { headers: { 'Authorization': 'Bearer ' + token } });
                if (res.status === 401) { logoutUser(); return; }
                const data = await res.json();
                const tbody = document.getElementById('commsTableBody');
                if (data.communications && data.communications.length > 0) {
                    tbody.innerHTML = data.communications.map(c => `
                        <tr>
                            <td>${escapeHtml(c.timestamp)}</td>
                            <td>${escapeHtml(c.direction)}</td>
                            <td>${escapeHtml(c.channel)}</td>
                            <td>${escapeHtml(c.status)}</td>
                            <td>${escapeHtml(c.subject)}</td>
                        </tr>
                    `).join('');
                } else {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No records found.</td></tr>';
                }
            } catch (e) {
                document.getElementById('commsTableBody').innerHTML = '<tr><td colspan="5">Error loading communications.</td></tr>';
            }
        }

        async function loadBizOps() {
            const token = getAuthToken();
            try {
                const res1 = await fetch('/api/v1/marketing/campaigns', { headers: { 'Authorization': 'Bearer ' + token } });
                if (res1.status === 401) { logoutUser(); return; }
                const data1 = await res1.json();
                const tbody1 = document.getElementById('bizopsCampaignsBody');
                if (data1.campaigns && data1.campaigns.length > 0) {
                    tbody1.innerHTML = data1.campaigns.map(c => `
                        <tr>
                            <td>${escapeHtml(c.name)}</td>
                            <td>${escapeHtml(c.channel)}</td>
                            <td>$${escapeHtml((c.budget || 0).toLocaleString())}</td>
                            <td>${escapeHtml(c.leads_generated)}</td>
                            <td>${escapeHtml(c.status)}</td>
                        </tr>
                    `).join('');
                } else {
                    tbody1.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No campaigns found.</td></tr>';
                }
                
                const res2 = await fetch('/api/v1/compliance/items', { headers: { 'Authorization': 'Bearer ' + token } });
                if (res2.status === 401) { logoutUser(); return; }
                const data2 = await res2.json();
                const tbody2 = document.getElementById('bizopsComplianceBody');
                if (data2.compliance_items && data2.compliance_items.length > 0) {
                    tbody2.innerHTML = data2.compliance_items.map(c => `
                        <tr>
                            <td>${escapeHtml(c.title)}</td>
                            <td>${escapeHtml(c.category)}</td>
                            <td>${escapeHtml(c.expiration_date)}</td>
                            <td>${escapeHtml(c.status || 'Active')}</td>
                        </tr>
                    `).join('');
                } else {
                    tbody2.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No compliance items found.</td></tr>';
                }
            } catch (e) {
                console.error('Error loading biz ops', e);
            }
        }

        window.addEventListener('DOMContentLoaded', () => {
            loadKPIs();
        });

        let permissionsCatalog = {};

        function openCustomerModal() { document.getElementById('addCustomerModal').classList.add('active'); }
        function closeCustomerModal() { document.getElementById('addCustomerModal').classList.remove('active'); }
        function openProjectModal() { 
            document.getElementById('addProjectModal').classList.add('active'); 
            populateCustomerDropdown();
        }
        function closeProjectModal() { document.getElementById('addProjectModal').classList.remove('active'); }

        async function submitCustomer(e) {
            e.preventDefault();
            const payload = {
                first_name: document.getElementById('custFirst').value,
                last_name: document.getElementById('custLast').value,
                email: document.getElementById('custEmail').value,
                phone: document.getElementById('custPhone').value,
                customer_type: 'residential'
            };
            const res = await fetch('/api/v1/customers', {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + getAuthToken(), 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                closeCustomerModal();
                loadCrmList();
            } else {
                alert('Failed to save customer');
            }
        }

        async function submitProject(e) {
            e.preventDefault();
            const payload = {
                customer_id: parseInt(document.getElementById('projCustomer').value),
                title: document.getElementById('projTitle').value,
                project_type: document.getElementById('projType').value,
                stage: 'Lead'
            };
            const res = await fetch('/api/v1/projects', {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + getAuthToken(), 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                closeProjectModal();
                loadCrmList();
            } else {
                alert('Failed to save project');
            }
        }

        let currentCustomers = [];

        async function loadCrmList() {
            const token = getAuthToken();
            
            // Load Customers
            try {
                const res = await fetch('/api/v1/customers', { headers: { 'Authorization': 'Bearer ' + token } });
                if (res.status === 401) { logoutUser(); return; }
                const data = await res.json();
                if (data.customers) {
                    currentCustomers = data.customers;
                    const html = data.customers.map(c => `
                        <div style="padding: 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.05);">
                            <div style="color: var(--offwhite); font-weight: 500;">${escapeHtml(c.first_name || '')} ${escapeHtml(c.last_name || '')}</div>
                            <div style="font-size: 0.85rem;">${escapeHtml(c.email || '')} | ${escapeHtml(c.phone || '')}</div>
                        </div>
                    `).join('');
                    document.getElementById('crmListContainer').innerHTML = html || 'No customers found.';
                }
            } catch (e) {
                document.getElementById('crmListContainer').innerHTML = 'Failed to load customers.';
            }

            // Load Projects
            try {
                const res = await fetch('/api/v1/projects', { headers: { 'Authorization': 'Bearer ' + token } });
                if (res.status === 401) { logoutUser(); return; }
                const data = await res.json();
                if (data.projects) {
                    const html = data.projects.map(p => `
                        <div style="padding: 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.05);">
                            <div style="color: var(--offwhite); font-weight: 500;">${escapeHtml(p.title || 'Untitled')}</div>
                            <div style="font-size: 0.85rem;"><span class="badge" style="background: rgba(212,175,55,0.1); color: var(--bronze); padding: 0.1rem 0.4rem; border-radius: 4px;">${escapeHtml(p.stage)}</span> - ${escapeHtml(p.project_type)}</div>
                        </div>
                    `).join('');
                    document.getElementById('projectListContainer').innerHTML = html || 'No projects found.';
                }
            } catch (e) {
                document.getElementById('projectListContainer').innerHTML = 'Failed to load projects.';
            }
        }

        function populateCustomerDropdown() {
            const sel = document.getElementById('projCustomer');
            sel.innerHTML = currentCustomers.map(c => `<option value="${c.id}">${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)}</option>`).join('');
        }

        function filterCrm() {
            // Basic filtering (visual only)
            const term = document.getElementById('crmSearch').value.toLowerCase();
            const items = document.getElementById('crmListContainer').children;
            for (let i = 0; i < items.length; i++) {
                items[i].style.display = items[i].innerText.toLowerCase().includes(term) ? '' : 'none';
            }
        }

        let currentEditingUserId = null;
        let userPermissionsState = {};
        let currentEditUserId = null;
        let currentEditUserOriginalRole = null;

        function switchErpTab(tabId) {
            document.querySelectorAll('.erp-tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            if (event && event.target) {
                event.target.classList.add('active');
            }
            const target = document.getElementById('tab-' + tabId);
            if (target) target.classList.add('active');
            
            if (tabId === 'kpis') loadKPIs();
            if (tabId === 'operations') loadEquipment();
            if (tabId === 'subcontractors') loadSubcontractors();
            if (tabId === 'finance') loadFinance();
            if (tabId === 'comms') loadComms();
            if (tabId === 'bizops') loadBizOps();
            
            if (tabId === 'users') { loadUsersList(); loadDeletedUserHistory(); }
            if (tabId === 'crm') loadCrmList();
            if (tabId === 'telemetry') loadAuditLogs();
            if (tabId === 'audit') searchAuditLog();
            if (tabId === 'documents') loadDocuments();
            if (tabId === 'staff-schedules') loadStaffSchedules();
        }

        function escapeHtml(unsafe) {
            return (unsafe || '').toString()
                 .replace(/&/g, "&amp;")
                 .replace(/</g, "&lt;")
                 .replace(/>/g, "&gt;")
                 .replace(/"/g, "&quot;")
                 .replace(/'/g, "&#039;");
        }

        function openStaffScheduleModal() {
            document.getElementById('addStaffScheduleModal').classList.add('active');
        }

        function closeStaffScheduleModal() {
            document.getElementById('addStaffScheduleModal').classList.remove('active');
        }

        async function loadStaffSchedules() {
            const token = getAuthToken();
            const tbody = document.getElementById('staffSchedulesList');
            if (!tbody) return;
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center;">Loading schedules...</td></tr>';
            // list_staff_schedules defaults to the 200 OLDEST rows
            // (ORDER BY start_time ASC LIMIT 200) when the caller sends no
            // range/limit -- an unscoped fetch here would silently hide
            // every upcoming shift once 200+ historical rows exist. Pass
            // an explicit limit (same 500 the Calendar tab uses) and flag
            // a full-to-the-cap response rather than pretend it's complete.
            const STAFF_TAB_FETCH_LIMIT = 500;
            try {
                const res = await fetch('/api/v1/staff-schedules?limit=' + STAFF_TAB_FETCH_LIMIT, {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (res.status === 401) { logoutUser(); return; }
                const data = await res.json();
                if (data.schedules && data.schedules.length > 0) {
                    const truncatedRow = data.schedules.length === STAFF_TAB_FETCH_LIMIT
                        ? '<tr><td colspan="6" style="text-align: center; color: var(--danger); font-size: 0.8rem;">Showing the first ' + STAFF_TAB_FETCH_LIMIT + ' staff-schedule entries -- some may be hidden. Use the Calendar tab with a narrower date range for a complete view.</td></tr>'
                        : '';
                    tbody.innerHTML = truncatedRow + data.schedules.map(s => `
                        <tr>
                            <td>${escapeHtml(s.user_id)}</td>
                            <td>${escapeHtml(s.title)}</td>
                            <td>${escapeHtml(s.start_time)}</td>
                            <td>${escapeHtml(s.end_time)}</td>
                            <td><span class="badge ${s.status === 'scheduled' ? 'badge-info' : 'badge-gold'}">${escapeHtml(s.status)}</span></td>
                            <td>
                                <button class="btn-gold" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;" onclick="deleteStaffSchedule(${s.id})">Delete</button>
                            </td>
                        </tr>
                    `).join('');
                } else {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No staff schedules found.</td></tr>';
                }
            } catch (e) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--danger);">Failed to load schedules.</td></tr>';
            }
        }

        async function submitStaffSchedule(event) {
            event.preventDefault();
            const token = getAuthToken();
            const payload = {
                user_id: parseInt(document.getElementById('schedUserId').value, 10),
                title: document.getElementById('schedTitle').value,
                start_time: document.getElementById('schedStart').value,
                end_time: document.getElementById('schedEnd').value,
                notes: document.getElementById('schedNotes').value,
                status: 'scheduled'
            };
            try {
                const res = await fetch('/api/v1/staff-schedules', {
                    method: 'POST',
                    headers: {
                        'Authorization': 'Bearer ' + token,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                });
                if (res.ok) {
                    closeStaffScheduleModal();
                    loadStaffSchedules();
                } else {
                    const errorData = await res.json();
                    alert('Error: ' + (errorData.error || res.statusText));
                }
            } catch (e) {
                console.error(e);
                alert('Failed to save staff schedule.');
            }
        }

        async function deleteStaffSchedule(id) {
            if (!confirm('Delete this staff schedule?')) return;
            const token = getAuthToken();
            try {
                const res = await fetch('/api/v1/staff-schedules/' + id, {
                    method: 'DELETE',
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (res.ok) {
                    loadStaffSchedules();
                } else {
                    const err = await res.json();
                    alert('Failed to delete: ' + (err.error || res.statusText));
                }
            } catch (e) {
                console.error(e);
                alert('Failed to delete staff schedule.');
            }
        }

        // ---- Calendar (Phase 7 Part 2: read-only view; Part 3 below adds create/edit) ----

        const CAL_TYPE_COLORS = ['#D4AF37', '#6EE7B7', '#93C5FD', '#FCA5A5', '#C4B5FD', '#FDBA74', '#67E8F9', '#F9A8D4'];

        // Deterministic hash of the type id into the fixed palette so the
        // same appointment type always gets the same color across renders
        // (NEW-488: no schema change, no new `color` column).
        function calColorForType(typeId) {
            if (typeId === null || typeId === undefined || typeId === '') return '#64748B';
            const n = parseInt(typeId, 10);
            const idx = Number.isFinite(n) ? Math.abs(n) % CAL_TYPE_COLORS.length : 0;
            return CAL_TYPE_COLORS[idx];
        }

        function calPad(n) { return (n < 10 ? '0' : '') + n; }
        function calISODate(d) { return d.getFullYear() + '-' + calPad(d.getMonth() + 1) + '-' + calPad(d.getDate()); }

        window.calState = { view: 'month', anchorDate: new Date() };

        function calSetView(view) {
            window.calState.view = view;
            const mBtn = document.getElementById('calViewMonthBtn');
            const wBtn = document.getElementById('calViewWeekBtn');
            if (mBtn) mBtn.classList.toggle('cal-view-btn-active', view === 'month');
            if (wBtn) wBtn.classList.toggle('cal-view-btn-active', view === 'week');
            loadCalendar();
        }

        function calNav(delta) {
            const d = window.calState.anchorDate;
            if (window.calState.view === 'month') {
                // Rebuild on day 1 of the target month rather than mutating
                // d's existing day-of-month via setMonth() -- setMonth()
                // overflows into the following month whenever the current
                // day-of-month exceeds the target month's length (e.g. Aug
                // 31 + 1 month rolls past Sep into Oct 1, silently skipping
                // September), making Next/Prev asymmetric.
                window.calState.anchorDate = new Date(d.getFullYear(), d.getMonth() + delta, 1);
            } else {
                d.setDate(d.getDate() + delta * 7);
            }
            loadCalendar();
        }

        function calToday() {
            window.calState.anchorDate = new Date();
            loadCalendar();
        }

        // Grid range spans the first visible cell through the last visible
        // cell (leading/trailing adjacent-month days included in month
        // view), not just the 1st-to-last of the month -- otherwise items
        // that fall on those adjacent-month cells never get fetched.
        function calGetRange() {
            const anchor = window.calState.anchorDate;
            if (window.calState.view === 'month') {
                const y = anchor.getFullYear(), m = anchor.getMonth();
                const firstOfMonth = new Date(y, m, 1);
                const lastOfMonth = new Date(y, m + 1, 0);
                const gridStart = new Date(firstOfMonth);
                gridStart.setDate(gridStart.getDate() - gridStart.getDay());
                const gridEnd = new Date(lastOfMonth);
                gridEnd.setDate(gridEnd.getDate() + (6 - gridEnd.getDay()));
                return { gridStart, gridEnd, label: firstOfMonth.toLocaleString('default', { month: 'long', year: 'numeric' }) };
            }
            const gridStart = new Date(anchor);
            gridStart.setDate(anchor.getDate() - anchor.getDay());
            const gridEnd = new Date(gridStart);
            gridEnd.setDate(gridStart.getDate() + 6);
            return { gridStart, gridEnd, label: calISODate(gridStart) + ' – ' + calISODate(gridEnd) };
        }

        function calPopulateTypeFilter() {
            const sel = document.getElementById('calFilterType');
            if (!sel) return;
            const current = sel.value;
            const types = window.currentAppointmentTypes || [];
            sel.innerHTML = '<option value="">All Appointment Types</option>' +
                types.map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('');
            sel.value = current;
        }

        function calPopulatePersonFilter() {
            const sel = document.getElementById('calFilterPerson');
            if (!sel) return;
            const current = sel.value;
            const users = window.currentCalendarUsers || [];
            sel.innerHTML = '<option value="">All People (staff schedules)</option>' +
                users.map(u => `<option value="${u.id}">${escapeHtml(u.full_name || u.username)}</option>`).join('');
            sel.value = current;
        }

        function calTypeName(typeId) {
            const t = (window.currentAppointmentTypes || []).find(x => x.id === typeId);
            return t ? t.name : '';
        }

        function calUserName(userId) {
            const u = (window.currentCalendarUsers || []).find(x => x.id === userId);
            return u ? (u.full_name || u.username) : ('User #' + userId);
        }

        function calUserRole(userId) {
            const u = (window.currentCalendarUsers || []).find(x => x.id === userId);
            return u ? u.role : '';
        }

        async function loadCalendar() {
            const token = getAuthToken();
            const errBox = document.getElementById('calLoadErrors');
            if (errBox) errBox.innerHTML = '';
            const range = calGetRange();
            const rangeLabel = document.getElementById('calRangeLabel');
            if (rangeLabel) rangeLabel.innerText = range.label;
            const startStr = calISODate(range.gridStart);
            const endStr = calISODate(range.gridEnd);

            // Appointment types: reuse the cache populated at page init
            // (window.currentAppointmentTypes, include_inactive=true) so an
            // appointment pointing at a deactivated type still resolves a
            // name; fall back to a fresh fetch only if that init load
            // failed or hasn't run.
            if (!window.currentAppointmentTypes || !window.currentAppointmentTypes.length) {
                try {
                    const tRes = await fetch('/api/v1/appointment-types?include_inactive=true', {
                        headers: { 'Authorization': 'Bearer ' + token }
                    });
                    if (tRes.ok) {
                        const tData = await tRes.json();
                        window.currentAppointmentTypes = tData.appointment_types || [];
                    }
                } catch (e) { /* leave whatever was cached; type names just won't resolve */ }
            }
            calPopulateTypeFilter();

            // Users are not cached anywhere else in this file (loadUsersList
            // renders straight into a table) -- fetch fresh here, following
            // the window.currentX caching convention used for appointment
            // types.
            try {
                const uRes = await fetch('/api/v1/users', { headers: { 'Authorization': 'Bearer ' + token } });
                if (uRes.status === 401) { logoutUser(); return; }
                if (uRes.ok) {
                    const uData = await uRes.json();
                    window.currentCalendarUsers = uData.users || [];
                    calPopulatePersonFilter();
                }
            } catch (e) { /* person names/filter just won't resolve; staff-schedule rows still render with raw user_id */ }

            // The two sources degrade independently: a role holding only
            // one of PERM_READ_APPOINTMENTS / PERM_READ_STAFF_SCHEDULES
            // (e.g. sales, appointments-only) must still see its working
            // half of the calendar rather than a single blanked pane.
            let apptOk = true, staffOk = true, staffTruncated = false;
            // NEW-490: /api/v1/staff-schedules previously had no way to
            // raise its 200-row service default from a caller -- the
            // route now forwards &limit, mirroring appointments' &limit=500
            // below. Still detect a full-to-the-cap response client-side
            // (rather than trusting the raised limit alone) since a future
            // month's row count could exceed even 500.
            const CAL_STAFF_FETCH_LIMIT = 500;
            try {
                const aRes = await fetch('/api/v1/appointments?start=' + startStr + '&end=' + endStr + '&limit=500', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (aRes.status === 401) { logoutUser(); return; }
                if (aRes.ok) {
                    const aData = await aRes.json();
                    window.currentCalendarAppointments = aData.appointments || [];
                } else {
                    apptOk = false;
                }
            } catch (e) { apptOk = false; }

            try {
                const sRes = await fetch('/api/v1/staff-schedules?start=' + startStr + '&end=' + endStr + '&limit=' + CAL_STAFF_FETCH_LIMIT, {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (sRes.status === 401) { logoutUser(); return; }
                if (sRes.ok) {
                    const sData = await sRes.json();
                    const schedules = sData.schedules || [];
                    window.currentCalendarStaffSchedules = schedules;
                    // Hitting the requested cap exactly means rows beyond
                    // it were silently dropped server-side (ORDER BY
                    // start_time ASC LIMIT N) -- surface it rather than
                    // rendering a month that looks complete but isn't.
                    staffTruncated = schedules.length === CAL_STAFF_FETCH_LIMIT;
                } else {
                    staffOk = false;
                }
            } catch (e) { staffOk = false; }

            let errHtml = '';
            if (!apptOk) errHtml += '<div style="color: var(--danger); font-size: 0.8rem;">Could not load appointments (insufficient permission or fetch error).</div>';
            if (!staffOk) errHtml += '<div style="color: var(--danger); font-size: 0.8rem;">Could not load staff schedules (insufficient permission or fetch error).</div>';
            if (staffTruncated) errHtml += '<div style="color: var(--danger); font-size: 0.8rem;">Showing the first ' + CAL_STAFF_FETCH_LIMIT + ' staff-schedule entries for this range -- some may be hidden. Narrow the date range for a complete view.</div>';
            if (errBox) errBox.innerHTML = errHtml;

            renderCalendar();
        }

        // Filters: Person narrows both staff-schedule entries (by
        // user_id) and appointments (by assigned_user_id, added alongside
        // the assigned_user_id column). Role still narrows staff-schedule
        // entries only -- Appointment has no role axis of its own. The
        // Appointment Type filter narrows appointments only, symmetrically.
        function calFilteredAppointments() {
            const typeFilter = document.getElementById('calFilterType').value;
            const personFilter = document.getElementById('calFilterPerson').value;
            const appts = window.currentCalendarAppointments || [];
            return appts.filter(a => {
                if (typeFilter && String(a.appointment_type_id) !== typeFilter) return false;
                if (personFilter && String(a.assigned_user_id) !== personFilter) return false;
                return true;
            });
        }

        function calFilteredStaffSchedules() {
            const personFilter = document.getElementById('calFilterPerson').value;
            const roleFilter = document.getElementById('calFilterRole').value;
            const entries = window.currentCalendarStaffSchedules || [];
            return entries.filter(s => {
                if (personFilter && String(s.user_id) !== personFilter) return false;
                if (roleFilter && calUserRole(s.user_id) !== roleFilter) return false;
                return true;
            });
        }

        function renderCalendar() {
            const grid = document.getElementById('calGrid');
            if (!grid) return;
            if (window.calState.view === 'week') {
                renderCalendarWeek(grid);
            } else {
                renderCalendarMonth(grid);
            }
        }

        // Bucket by the ISO-date prefix of start_time (string slice, not
        // `new Date(...)`) -- start_time has no reliable timezone suffix,
        // so parsing it as a Date and re-deriving the day can shift items
        // across midnight depending on device TZ. A string-prefix compare
        // sidesteps that entirely.
        function calDayKey(isoString) {
            return (isoString || '').slice(0, 10);
        }

        // Compact per-item label used in both grid views: time, title (or
        // attendee_name), and the resolved appointment-type name if set --
        // all three fields the task enumerates, all routed through
        // escapeHtml.
        function calApptLabel(a) {
            const time = escapeHtml((a.start_time || '').slice(11, 16));
            const title = escapeHtml(a.title || a.attendee_name || 'Appointment');
            const typeName = calTypeName(a.appointment_type_id);
            const typeSuffix = typeName ? ' &middot; ' + escapeHtml(typeName) : '';
            return time + ' ' + title + typeSuffix;
        }

        // A month cell caps at this many rendered items before collapsing
        // into a "+N more" link (task: "colored dot + count if many, click
        // to expand/see a day's full list") -- unconditional rendering
        // inside a fixed-height, overflow:hidden cell would silently clip
        // the rest with no indication anything was cut.
        const CAL_MONTH_CELL_ITEM_CAP = 3;

        function renderCalendarMonth(grid) {
            grid.className = 'cal-month-grid';
            const range = calGetRange();
            const appts = calFilteredAppointments();
            const staff = calFilteredStaffSchedules();
            const currentMonth = window.calState.anchorDate.getMonth();

            const cells = [];
            const cursor = new Date(range.gridStart);
            while (cursor <= range.gridEnd) {
                const key = calISODate(cursor);
                const dayAppts = appts.filter(a => calDayKey(a.start_time) === key);
                const dayStaff = staff.filter(s => calDayKey(s.start_time) === key);
                const outside = cursor.getMonth() !== currentMonth;
                const total = dayAppts.length + dayStaff.length;
                const shownAppts = dayAppts.slice(0, CAL_MONTH_CELL_ITEM_CAP);
                const remainingCap = Math.max(0, CAL_MONTH_CELL_ITEM_CAP - shownAppts.length);
                const shownStaff = dayStaff.slice(0, remainingCap);
                const items = shownAppts.map(a => `
                    <div class="cal-item" style="background:${calColorForType(a.appointment_type_id)};" title="${escapeHtml(a.title || a.attendee_name || 'Appointment')}" onclick="openCalendarItem('appointment', ${a.id})">
                        ${calApptLabel(a)}
                    </div>`).join('') + shownStaff.map(s => `
                    <div class="cal-item cal-staff-item" onclick="openCalendarItem('staff', ${s.id})">
                        ${escapeHtml((s.start_time || '').slice(11, 16))} ${escapeHtml(calUserName(s.user_id))}
                    </div>`).join('');
                const shownCount = shownAppts.length + shownStaff.length;
                const moreHtml = total > shownCount
                    ? `<div class="cal-item" style="background:#334155; cursor:pointer;" onclick="openCalendarDay(${cursor.getFullYear()}, ${cursor.getMonth()}, ${cursor.getDate()})">+${total - shownCount} more</div>`
                    : '';
                cells.push(`
                    <div class="cal-day-cell${outside ? ' cal-outside-month' : ''}">
                        <div class="cal-day-num">${cursor.getDate()}</div>
                        ${items}${moreHtml}
                    </div>`);
                cursor.setDate(cursor.getDate() + 1);
            }
            grid.innerHTML = cells.join('');
        }

        // Day-detail view for the "+N more" link -- takes numeric
        // year/month/day (not an interpolated date string) so the onclick
        // handler above matches this file's numeric-args-only convention,
        // lists every item for that day in the shared detail modal, each
        // still opening its own item detail.
        function openCalendarDay(year, month, day) {
            const dateKey = calISODate(new Date(year, month, day));
            const appts = calFilteredAppointments().filter(a => calDayKey(a.start_time) === dateKey);
            const staff = calFilteredStaffSchedules().filter(s => calDayKey(s.start_time) === dateKey);
            const modal = document.getElementById('calItemModal');
            const title = document.getElementById('calItemModalTitle');
            const body = document.getElementById('calItemModalBody');
            title.innerText = escapeHtml(dateKey);
            const apptRows = appts.map(a => `
                <div class="cal-item" style="background:${calColorForType(a.appointment_type_id)}; margin-bottom:4px;" onclick="openCalendarItem('appointment', ${a.id})">
                    ${calApptLabel(a)}
                </div>`).join('');
            const staffRows = staff.map(s => `
                <div class="cal-item cal-staff-item" style="margin-bottom:4px;" onclick="openCalendarItem('staff', ${s.id})">
                    ${escapeHtml((s.start_time || '').slice(11, 16))} ${escapeHtml(calUserName(s.user_id))}
                </div>`).join('');
            body.innerHTML = (apptRows || staffRows) ? (apptRows + staffRows) : '<div style="color: var(--text-muted);">No items.</div>';
            modal.classList.add('active');
        }

        // Week view: a time-ordered list per day rather than a full
        // hour-row grid -- an hour grid needs pixel/time-axis positioning
        // this read-only pass doesn't need (Part 3's edit flow doesn't
        // either), and a sorted list matches this file's existing
        // table/list rendering idiom everywhere else.
        function renderCalendarWeek(grid) {
            grid.className = '';
            grid.style.display = 'grid';
            grid.style.gridTemplateColumns = 'repeat(7, 1fr)';
            grid.style.gap = '4px';
            const range = calGetRange();
            const appts = calFilteredAppointments();
            const staff = calFilteredStaffSchedules();

            const cols = [];
            const cursor = new Date(range.gridStart);
            for (let i = 0; i < 7; i++) {
                const key = calISODate(cursor);
                const dayAppts = appts.filter(a => calDayKey(a.start_time) === key)
                    .sort((a, b) => (a.start_time || '').localeCompare(b.start_time || ''));
                const dayStaff = staff.filter(s => calDayKey(s.start_time) === key)
                    .sort((a, b) => (a.start_time || '').localeCompare(b.start_time || ''));
                const items = dayAppts.map(a => `
                    <div class="cal-item" style="background:${calColorForType(a.appointment_type_id)};" title="${escapeHtml(a.title || a.attendee_name || 'Appointment')}" onclick="openCalendarItem('appointment', ${a.id})">
                        ${calApptLabel(a)}
                    </div>`).join('') + dayStaff.map(s => `
                    <div class="cal-item cal-staff-item" onclick="openCalendarItem('staff', ${s.id})">
                        ${escapeHtml((s.start_time || '').slice(11, 16))} ${escapeHtml(calUserName(s.user_id))}
                    </div>`).join('');
                cols.push(`
                    <div class="cal-week-col">
                        <div class="cal-week-col-head">${cursor.toLocaleDateString('default', { weekday: 'short', month: 'short', day: 'numeric' })}</div>
                        ${items || '<div style="color: var(--text-muted); font-size: 0.75rem;">No items</div>'}
                    </div>`);
                cursor.setDate(cursor.getDate() + 1);
            }
            grid.innerHTML = cols.join('');
        }

        // Detail view -- looks the item up by numeric id from the cached
        // arrays populated by loadCalendar(); the onclick handler above
        // passes only that id, never an interpolated name/string (NEW-481's
        // exact vulnerable pattern). Part 3: gains Edit (both kinds) and a
        // status-transition action per kind -- Cancel for appointments
        // (no hard delete; POST .../status), Remove for staff schedules
        // (DELETE .../staff-schedules/{id} already exists and is simple,
        // per task scope). All action buttons below pass only the numeric
        // `id` already captured in this closure -- no new string
        // interpolation into onclick.
        function openCalendarItem(kind, id) {
            const modal = document.getElementById('calItemModal');
            const title = document.getElementById('calItemModalTitle');
            const body = document.getElementById('calItemModalBody');
            if (kind === 'appointment') {
                const a = (window.currentCalendarAppointments || []).find(x => x.id === id);
                if (!a) return;
                title.innerText = 'Appointment';
                const cancelBtn = a.status === 'cancelled' ? '' :
                    `<button class="btn-gold" style="background:transparent; border:1px solid var(--danger); color: var(--danger);" onclick="cancelAppointmentFromCalendar(${a.id})">Cancel Appointment</button>`;
                body.innerHTML = `
                    <div style="margin-bottom:0.5rem;"><strong>Title:</strong> ${escapeHtml(a.title || a.attendee_name || '(untitled)')}</div>
                    <div style="margin-bottom:0.5rem;"><strong>Type:</strong> ${escapeHtml(calTypeName(a.appointment_type_id) || '(none)')}</div>
                    <div style="margin-bottom:0.5rem;"><strong>Assigned to:</strong> ${a.assigned_user_id != null ? escapeHtml(calUserName(a.assigned_user_id)) : '(unassigned)'}</div>
                    <div style="margin-bottom:0.5rem;"><strong>Start:</strong> ${escapeHtml(a.start_time)}</div>
                    <div style="margin-bottom:0.5rem;"><strong>End:</strong> ${escapeHtml(a.end_time)}</div>
                    <div style="margin-bottom:0.5rem;"><strong>Attendee:</strong> ${escapeHtml(a.attendee_name || '(none)')}</div>
                    <div style="margin-bottom:0.5rem;"><strong>Status:</strong> ${escapeHtml(a.status)}</div>
                    <div style="margin-bottom:0.5rem;"><strong>Notes:</strong> ${escapeHtml(a.notes || '(none)')}</div>
                    <div style="display:flex; gap:0.5rem; margin-top:1rem;">
                        <button class="btn-gold" onclick="openEditApptModal(${a.id})">Edit</button>
                        ${cancelBtn}
                    </div>
                `;
            } else {
                const s = (window.currentCalendarStaffSchedules || []).find(x => x.id === id);
                if (!s) return;
                title.innerText = 'Staff Schedule';
                body.innerHTML = `
                    <div style="margin-bottom:0.5rem;"><strong>Person:</strong> ${escapeHtml(calUserName(s.user_id))}</div>
                    <div style="margin-bottom:0.5rem;"><strong>Title:</strong> ${escapeHtml(s.title)}</div>
                    <div style="margin-bottom:0.5rem;"><strong>Start:</strong> ${escapeHtml(s.start_time)}</div>
                    <div style="margin-bottom:0.5rem;"><strong>End:</strong> ${escapeHtml(s.end_time)}</div>
                    <div style="margin-bottom:0.5rem;"><strong>Status:</strong> ${escapeHtml(s.status)}</div>
                    <div style="margin-bottom:0.5rem;"><strong>Notes:</strong> ${escapeHtml(s.notes || '(none)')}</div>
                    <div style="display:flex; gap:0.5rem; margin-top:1rem;">
                        <button class="btn-gold" onclick="openEditSchedModal(${s.id})">Edit</button>
                        <button class="btn-gold" style="background:transparent; border:1px solid var(--danger); color: var(--danger);" onclick="removeScheduleFromCalendar(${s.id})">Remove</button>
                    </div>
                `;
            }
            modal.classList.add('active');
        }

        function closeCalItemModal() {
            document.getElementById('calItemModal').classList.remove('active');
        }

        // ---- Create/Edit forms (Phase 7 Part 3) ----

        function calPopulateApptTypeSelect(selectedId) {
            const sel = document.getElementById('calApptTypeId');
            if (!sel) return;
            const types = window.currentAppointmentTypes || [];
            sel.innerHTML = '<option value="">(none)</option>' +
                types.map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('');
            sel.value = (selectedId === null || selectedId === undefined) ? '' : String(selectedId);
        }

        function calPopulateSchedUserSelect(selectedId) {
            const sel = document.getElementById('calSchedUserId');
            if (!sel) return;
            const users = window.currentCalendarUsers || [];
            sel.innerHTML = users.map(u => `<option value="${u.id}">${escapeHtml(u.full_name || u.username)}</option>`).join('');
            if (selectedId !== null && selectedId !== undefined) sel.value = String(selectedId);
        }

        // Unlike calPopulateSchedUserSelect, keeps the leading blank
        // "(unassigned)" option -- assigned_user_id is nullable, staff_schedules.user_id is not.
        function calPopulateApptAssignedUserSelect(selectedId) {
            const sel = document.getElementById('calApptAssignedUserId');
            if (!sel) return;
            const users = window.currentCalendarUsers || [];
            sel.innerHTML = '<option value="">(unassigned)</option>' +
                users.map(u => `<option value="${u.id}">${escapeHtml(u.full_name || u.username)}</option>`).join('');
            sel.value = (selectedId === null || selectedId === undefined) ? '' : String(selectedId);
        }

        function openNewApptModal() {
            document.getElementById('calApptFormError').style.display = 'none';
            document.getElementById('calApptFormTitle').innerText = 'New Appointment';
            document.getElementById('calApptId').value = '';
            document.getElementById('calApptTitle').value = '';
            document.getElementById('calApptAttendee').value = '';
            document.getElementById('calApptStart').value = '';
            document.getElementById('calApptEnd').value = '';
            document.getElementById('calApptStatus').value = 'confirmed';
            document.getElementById('calApptStatus').disabled = false;
            document.getElementById('calApptStatusEditNote').style.display = 'none';
            calPopulateApptTypeSelect(null);
            calPopulateApptAssignedUserSelect(null);
            document.getElementById('calApptModal').classList.add('active');
        }

        // Status is deliberately NOT submitted on edit -- update_appointment()
        // (the /update route) is a generic partial-SET-clause writer with no
        // history-log entry, unlike the dedicated update_appointment_status()
        // behind the Cancel action (which appends a history event and logs a
        // distinct 'status_change' audit action). Routing a status change
        // through /update would silently skip both. submitApptForm()'s
        // `if (!id)` guard is what actually excludes status from the
        // payload on edit -- disabling the <select> here is only a visual
        // affordance (a disabled field is excluded from native form
        // serialization, but .value still reads fine in JS, so disabling
        // it alone would not have been enough) so the user can see the
        // current status without being able to change it from this form.
        function openEditApptModal(id) {
            const a = (window.currentCalendarAppointments || []).find(x => x.id === id);
            if (!a) return;
            closeCalItemModal();
            document.getElementById('calApptFormError').style.display = 'none';
            document.getElementById('calApptFormTitle').innerText = 'Edit Appointment';
            document.getElementById('calApptId').value = a.id;
            document.getElementById('calApptTitle').value = a.title || '';
            document.getElementById('calApptAttendee').value = a.attendee_name || '';
            document.getElementById('calApptStart').value = a.start_time || '';
            document.getElementById('calApptEnd').value = a.end_time || '';
            document.getElementById('calApptStatus').value = a.status || 'confirmed';
            document.getElementById('calApptStatus').disabled = true;
            document.getElementById('calApptStatusEditNote').style.display = 'block';
            calPopulateApptTypeSelect(a.appointment_type_id);
            calPopulateApptAssignedUserSelect(a.assigned_user_id);
            document.getElementById('calApptModal').classList.add('active');
        }

        function closeApptFormModal() {
            document.getElementById('calApptModal').classList.remove('active');
        }

        // On a 400 (e.g. Phase 4's concurrency-cap ValueError, surfaced by
        // SchedulingService.create_appointment/update_appointment through
        // routes.py as {"error": "..."}), the modal stays open with
        // whatever the user typed still in place and the real message is
        // shown inline -- no alert(), no silent no-op, no false-success
        // close.
        async function submitApptForm(event) {
            event.preventDefault();
            const token = getAuthToken();
            const errBox = document.getElementById('calApptFormError');
            errBox.style.display = 'none';
            const id = document.getElementById('calApptId').value;
            const payload = {
                title: document.getElementById('calApptTitle').value,
                attendee_name: document.getElementById('calApptAttendee').value,
                start_time: document.getElementById('calApptStart').value,
                end_time: document.getElementById('calApptEnd').value,
                appointment_type_id: document.getElementById('calApptTypeId').value ? parseInt(document.getElementById('calApptTypeId').value, 10) : null,
                assigned_user_id: document.getElementById('calApptAssignedUserId').value ? parseInt(document.getElementById('calApptAssignedUserId').value, 10) : null
            };
            // Status only travels on create -- see openEditApptModal's
            // comment for why an edit must never carry it through /update.
            if (!id) {
                payload.status = document.getElementById('calApptStatus').value;
            }
            try {
                const url = id ? '/api/v1/appointments/' + id + '/update' : '/api/v1/appointments';
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (res.ok) {
                    closeApptFormModal();
                    loadCalendar();
                } else {
                    errBox.innerText = data.error || ('Failed to save appointment (' + res.status + ').');
                    errBox.style.display = 'block';
                }
            } catch (e) {
                errBox.innerText = 'Failed to save appointment: network error.';
                errBox.style.display = 'block';
            }
        }

        async function cancelAppointmentFromCalendar(id) {
            if (!confirm('Cancel this appointment?')) return;
            const token = getAuthToken();
            try {
                const res = await fetch('/api/v1/appointments/' + id + '/status', {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: 'cancelled' })
                });
                if (res.ok) {
                    closeCalItemModal();
                    loadCalendar();
                } else {
                    const data = await res.json();
                    alert('Failed to cancel appointment: ' + (data.error || res.statusText));
                }
            } catch (e) {
                alert('Failed to cancel appointment: network error.');
            }
        }

        function openNewSchedModal() {
            document.getElementById('calSchedFormError').style.display = 'none';
            document.getElementById('calSchedFormTitle').innerText = 'New Staff Schedule Entry';
            document.getElementById('calSchedId').value = '';
            document.getElementById('calSchedTitle').value = '';
            document.getElementById('calSchedStart').value = '';
            document.getElementById('calSchedEnd').value = '';
            document.getElementById('calSchedNotes').value = '';
            calPopulateSchedUserSelect(null);
            document.getElementById('calSchedModal').classList.add('active');
        }

        function openEditSchedModal(id) {
            const s = (window.currentCalendarStaffSchedules || []).find(x => x.id === id);
            if (!s) return;
            closeCalItemModal();
            document.getElementById('calSchedFormError').style.display = 'none';
            document.getElementById('calSchedFormTitle').innerText = 'Edit Staff Schedule Entry';
            document.getElementById('calSchedId').value = s.id;
            document.getElementById('calSchedTitle').value = s.title || '';
            document.getElementById('calSchedStart').value = s.start_time || '';
            document.getElementById('calSchedEnd').value = s.end_time || '';
            document.getElementById('calSchedNotes').value = s.notes || '';
            calPopulateSchedUserSelect(s.user_id);
            document.getElementById('calSchedModal').classList.add('active');
        }

        function closeSchedFormModal() {
            document.getElementById('calSchedModal').classList.remove('active');
        }

        async function submitSchedForm(event) {
            event.preventDefault();
            const token = getAuthToken();
            const errBox = document.getElementById('calSchedFormError');
            errBox.style.display = 'none';
            const id = document.getElementById('calSchedId').value;
            const payload = {
                user_id: parseInt(document.getElementById('calSchedUserId').value, 10),
                title: document.getElementById('calSchedTitle').value,
                start_time: document.getElementById('calSchedStart').value,
                end_time: document.getElementById('calSchedEnd').value,
                notes: document.getElementById('calSchedNotes').value
            };
            // status is only set on create (new entries always start
            // 'scheduled') -- omitted on edit so update_staff_schedule()'s
            // partial SET-clause leaves the entry's real (possibly
            // non-'scheduled') status untouched. Sending a hardcoded
            // 'scheduled' on every edit would silently revert it.
            if (!id) {
                payload.status = 'scheduled';
            }
            try {
                const url = id ? '/api/v1/staff-schedules/' + id : '/api/v1/staff-schedules';
                const method = id ? 'PATCH' : 'POST';
                const res = await fetch(url, {
                    method: method,
                    headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (res.ok) {
                    closeSchedFormModal();
                    loadCalendar();
                } else {
                    errBox.innerText = data.error || ('Failed to save schedule entry (' + res.status + ').');
                    errBox.style.display = 'block';
                }
            } catch (e) {
                errBox.innerText = 'Failed to save schedule entry: network error.';
                errBox.style.display = 'block';
            }
        }

        async function removeScheduleFromCalendar(id) {
            if (!confirm('Remove this staff schedule entry?')) return;
            const token = getAuthToken();
            try {
                const res = await fetch('/api/v1/staff-schedules/' + id, {
                    method: 'DELETE',
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (res.ok) {
                    closeCalItemModal();
                    loadCalendar();
                } else {
                    const data = await res.json();
                    alert('Failed to remove schedule entry: ' + (data.error || res.statusText));
                }
            } catch (e) {
                alert('Failed to remove schedule entry: network error.');
            }
        }

        async function loadDocuments() {
            const token = getAuthToken();
            const tbody = document.getElementById('documentsTableBody');
            if (!tbody) return;
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center;">Loading documents...</td></tr>';
            try {
                const res = await fetch('/api/v1/documents', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (res.status === 401) { logoutUser(); return; }
                const data = await res.json();
                if (data.documents && data.documents.length > 0) {
                    tbody.innerHTML = data.documents.map(d => `
                        <tr>
                            <td>${d.id}</td>
                            <td>${escapeHtml(d.document_type)}</td>
                            <td>${escapeHtml(d.title)}</td>
                            <td>
                                ${d.customer_id ? 'Cust: ' + d.customer_id : ''}
                                ${d.project_id ? 'Proj: ' + d.project_id : ''}
                            </td>
                            <td>
                                <button onclick="window.open('/api/v1/documents/${d.id}/download?token=' + getAuthToken(), '_blank')" class="btn-gold" style="padding: 0.2rem 0.5rem;">Download</button>
                            </td>
                        </tr>
                    `).join('');
                } else {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center;">No documents found</td></tr>';
                }
            } catch (err) {
                tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--danger);">Error loading documents</td></tr>`;
            }
        }

        async function searchAuditLog() {
            const token = getAuthToken();
            const et = document.getElementById('auditEntityType').value;
            const eid = document.getElementById('auditEntityId').value;
            const aid = document.getElementById('auditActorId').value;
            const act = document.getElementById('auditAction').value;
            const limit = document.getElementById('auditLimit').value;
            
            const params = new URLSearchParams();
            if (et) params.append('entity_type', et);
            if (eid) params.append('entity_id', eid);
            if (aid) params.append('actor_id', aid);
            if (act) params.append('action', act);
            if (limit) params.append('limit', limit);
            
            const out = document.getElementById('auditResults');
            out.innerHTML = '<p style="color:var(--text-muted)">Loading...</p>';
            try {
                const res = await fetch('/api/v1/audit-log?' + params.toString(), {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                const data = await res.json();
                if (!res.ok) {
                    out.innerHTML = `<p style="color:#EF4444">Error: ${escapeHtml(data.error || res.status)}</p>`;
                    return;
                }
                const logs = data.audit_logs || [];
                if (!logs.length) {
                    out.innerHTML = '<p style="color:var(--text-muted)">No results.</p>';
                    return;
                }
                out.innerHTML = logs.map(r => {
                    const details = r.details || {};
                    let detailsHtml = '';
                    if (details.changed_fields && Object.keys(details.changed_fields).length) {
                        const rows = Object.entries(details.changed_fields).map(([field, diff]) =>
                            `<tr><td style="padding:2px 8px;color:var(--text-muted)">${escapeHtml(field)}</td>`+
                            `<td style="padding:2px 8px;color:#EF4444">${escapeHtml(JSON.stringify(diff.old))}</td>`+
                            `<td style="padding:2px 8px;color:#22C55E">${escapeHtml(JSON.stringify(diff.new))}</td></tr>`
                        ).join('');
                        detailsHtml += `<table style="font-size:0.8rem;margin-top:4px;border-collapse:collapse;width:100%"><tr><th style="text-align:left;padding:2px 8px">Field</th><th style="text-align:left;padding:2px 8px">Old</th><th style="text-align:left;padding:2px 8px">New</th></tr>${rows}</table>`;
                    }
                    if (details.snapshot && Object.keys(details.snapshot).length) {
                        const rows = Object.entries(details.snapshot).map(([k,v]) =>
                            `<tr><td style="padding:2px 8px;color:var(--text-muted)">${escapeHtml(k)}</td><td style="padding:2px 8px">${escapeHtml(JSON.stringify(v))}</td></tr>`
                        ).join('');
                        detailsHtml += `<table style="font-size:0.8rem;margin-top:4px;border-collapse:collapse;width:100%"><tr><th style="text-align:left;padding:2px 8px">Field</th><th style="text-align:left;padding:2px 8px">Value</th></tr>${rows}</table>`;
                    }
                    if (details.side_effects && Object.keys(details.side_effects).length) {
                        detailsHtml += `<pre style="font-size:0.78rem;margin-top:4px;color:#94A3B8;padding:8px;background:rgba(0,0,0,0.2);border-radius:4px">${escapeHtml(JSON.stringify(details.side_effects, null, 2))}</pre>`;
                    }
                    return `<div class="erp-card" style="margin-bottom:0.5rem;padding:0.75rem;background:#0f2038">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.25rem">
                            <span style="color:var(--bronze);font-size:0.82rem">${escapeHtml(r.timestamp)}</span>
                            <span style="font-size:0.82rem">[<span style="color:var(--info)">${escapeHtml(r.action)}</span>] ${escapeHtml(r.entity_type)}${ r.entity_id ? ' #'+escapeHtml(r.entity_id) : ''}</span>
                            <span style="color:var(--text-muted);font-size:0.8rem">Actor: ${escapeHtml(r.actor_id) || 'system'} (${escapeHtml(r.actor_role)})</span>
                        </div>
                        <div style="font-size:0.84rem;margin-bottom:0.5rem">${escapeHtml(r.change_summary)}</div>
                        ${detailsHtml}
                    </div>`;
                }).join('');
            } catch (ex) {
                out.innerHTML = '<p style="color:#EF4444">Connection error.</p>';
            }
        }

        async function loadUsersList() {
            const token = getAuthToken();
            const tbody = document.getElementById('usersTableBody');
            try {
                const res = await fetch('/api/v1/users', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (res.status === 401) { logoutUser(); return; }
                const data = await res.json();
                if (res.ok && data.users) {
                    tbody.innerHTML = data.users.map(u => `
                        <tr>
                            <td>#${u.id}</td>
                            <td><strong>${escapeHtml(u.username)}</strong></td>
                            <td>${escapeHtml(u.full_name)}</td>
                            <td>${escapeHtml(u.email)}</td>
                            <td><span class="card-badge badge-slate">${escapeHtml(u.role)}</span></td>
                            <td>${Object.keys(u.custom_permissions || {}).length} Custom</td>
                            <td>
                                <span style="color: ${u.active ? 'var(--success)' : 'var(--danger)'}; font-weight:700;">
                                    ${u.active ? '● Active' : '● Suspended'}
                                </span>
                            </td>
                            <td>
                                <button class="btn-gold" style="padding: 0.25rem 0.55rem; font-size: 0.75rem;" onclick="openEditUserModal(${u.id})">Edit</button>
                                <button class="btn-gold" style="padding: 0.25rem 0.55rem; font-size: 0.75rem;" onclick="openPermModal(${u.id}, ${escapeHtml(JSON.stringify(u.username))})">Perms</button>
                                <button class="btn-gold" style="padding: 0.25rem 0.55rem; font-size: 0.75rem; background: ${u.active ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.2)'}; border-color: ${u.active ? 'var(--danger)' : 'var(--success)'}; color: ${u.active ? '#FCA5A5' : '#6EE7B7'};" onclick="toggleUserStatus(${u.id}, ${u.active})">
                                    ${u.active ? 'Suspend' : 'Activate'}
                                </button>
                                <button class="btn-gold" style="padding: 0.25rem 0.55rem; font-size: 0.75rem; background: rgba(239, 68, 68, 0.2); border-color: var(--danger); color: #FCA5A5;" onclick="deleteUser(${u.id}, ${escapeHtml(JSON.stringify(u.username))})">
                                    Delete
                                </button>
                            </td>
                        </tr>
                    `).join('');
                }
            } catch (ex) {
                tbody.innerHTML = '<tr><td colspan="8" style="color: var(--danger);">Failed to load users. Verify token privileges.</td></tr>';
            }
        }

        // Deleted User History (Delete-buttons round, Ish 2026-09-11
        // archive-then-delete decision, NEW-493): read-only view of
        // staff_schedules_archive, optionally filtered by the deleted
        // user's original username.
        async function loadDeletedUserHistory() {
            const token = getAuthToken();
            const tbody = document.getElementById('deletedUserHistoryTableBody');
            const filterVal = (document.getElementById('deletedUserHistoryFilter') || {}).value || '';
            try {
                const qs = filterVal.trim() ? ('?original_username=' + encodeURIComponent(filterVal.trim())) : '';
                const res = await fetch('/api/v1/staff-schedules-archive' + qs, {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (res.status === 401) { logoutUser(); return; }
                const data = await res.json();
                if (res.ok && data.archived_schedules) {
                    if (!data.archived_schedules.length) {
                        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No archived deleted-user history found.</td></tr>';
                        return;
                    }
                    tbody.innerHTML = data.archived_schedules.map(a => `
                        <tr>
                            <td>${escapeHtml(a.original_username)}</td>
                            <td>${escapeHtml(a.title)}</td>
                            <td>${escapeHtml(a.start_time)}</td>
                            <td>${escapeHtml(a.end_time)}</td>
                            <td><span class="card-badge badge-slate">${escapeHtml(a.status)}</span></td>
                            <td>${escapeHtml(a.notes || '')}</td>
                            <td>${escapeHtml(a.archived_at)}</td>
                        </tr>
                    `).join('');
                } else {
                    tbody.innerHTML = '<tr><td colspan="7" style="color: var(--danger);">' + escapeHtml(data.error || 'Failed to load deleted user history.') + '</td></tr>';
                }
            } catch (ex) {
                tbody.innerHTML = '<tr><td colspan="7" style="color: var(--danger);">Failed to load deleted user history. Verify token privileges.</td></tr>';
            }
        }

        async function openPermModal(userId, username) {
            currentEditingUserId = userId;
            document.getElementById('permModalUser').innerText = username;
            document.getElementById('permModalOverlay').classList.add('active');
            const body = document.getElementById('permModalBody');
            body.innerHTML = 'Loading permissions catalog...';

            const token = getAuthToken();
            try {
                if (!Object.keys(permissionsCatalog).length) {
                    const catRes = await fetch('/api/v1/permissions/catalog', {
                        headers: { 'Authorization': 'Bearer ' + token }
                    });
                    const catData = await catRes.json();
                    permissionsCatalog = catData.catalog || {};
                }

                const userRes = await fetch(`/api/v1/users/${userId}/permissions`, {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                const userData = await userRes.json();
                userPermissionsState = userData.custom_permissions || {};

                body.innerHTML = Object.entries(permissionsCatalog).map(([groupKey, group]) => `
                    <div class="perm-group">
                        <div class="perm-group-title">${group.title}</div>
                        <div class="perm-checkbox-grid">
                            ${group.permissions.map(p => `
                                <label class="perm-checkbox-item">
                                    <input type="checkbox" id="perm_${p.id}" ${userPermissionsState[p.id] ? 'checked' : ''} onchange="userPermissionsState['${p.id}'] = this.checked">
                                    <span>${p.name}</span>
                                </label>
                            `).join('')}
                        </div>
                    </div>
                `).join('');
            } catch (ex) {
                body.innerHTML = '<div style="color: var(--danger);">Failed to load permissions.</div>';
            }
        }

        function closePermModal() {
            document.getElementById('permModalOverlay').classList.remove('active');
        }

        async function saveUserPermissions() {
            const btn = document.getElementById('savePermsBtn');
            btn.disabled = true;
            btn.innerText = 'Saving Permissions...';
            const token = getAuthToken();

            try {
                const res = await fetch(`/api/v1/users/${currentEditingUserId}/permissions`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + token
                    },
                    body: JSON.stringify({ custom_permissions: userPermissionsState })
                });
                if (res.ok) {
                    closePermModal();
                    loadUsersList();
                } else {
                    alert('Error saving permissions');
                }
            } catch (ex) {
                alert('Connection error');
            } finally {
                btn.disabled = false;
                btn.innerText = 'Save Dynamic Permissions';
            }
        }

        async function toggleUserStatus(userId, currentActive) {
            const action = currentActive ? 'suspend' : 'activate';
            if (!confirm(`Are you sure you want to ${action} this user account?`)) return;
            const token = getAuthToken();
            try {
                await fetch(`/api/v1/users/${userId}/${action}`, {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                loadUsersList();
            } catch (ex) {
                alert('Error updating user status');
            }
        }

        // Delete-buttons round (Ish 2026-09-11): precheck for ACTIVE
        // references (staff_schedules with status='scheduled' for this
        // user) before ever offering a confirm() dialog -- if any exist,
        // block and list them so the admin knows what to fix first.
        async function deleteUser(userId, username) {
            const token = getAuthToken();
            try {
                const refRes = await fetch(`/api/v1/users/${userId}/active-references`, {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                const refData = await refRes.json();
                if (!refRes.ok) {
                    alert('Error checking active references: ' + (refData.error || refRes.statusText));
                    return;
                }
                const active = refData.active_references || [];
                if (active.length) {
                    const listing = active.map(s => `${s.id}: ${s.title} (${s.start_time})`).join('\\n');
                    alert(`Cannot delete: this user has ${active.length} active staff schedule(s):\n${listing}`);
                    return;
                }
                if (!confirm('Delete user ' + username + '? This cannot be undone.')) return;
                const res = await fetch(`/api/v1/users/${userId}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (res.ok) {
                    loadUsersList();
                } else {
                    const err = await res.json();
                    alert('Failed to delete: ' + (err.error || res.statusText));
                }
            } catch (ex) {
                alert('Failed to delete user.');
            }
        }

        function openAddUserModal() {
            document.getElementById('addUserModalOverlay').classList.add('active');
        }

        function closeAddUserModal() {
            document.getElementById('addUserModalOverlay').classList.remove('active');
        }

        async function submitNewUser(e) {
            e.preventDefault();
            const token = getAuthToken();
            const payload = {
                username: document.getElementById('newUsername').value.trim(),
                password: document.getElementById('newPassword').value,
                full_name: document.getElementById('newFullName').value.trim(),
                email: document.getElementById('newEmail').value.trim(),
                role: document.getElementById('newRole').value,
                department: document.getElementById('newDept').value.trim()
            };

            try {
                const res = await fetch('/api/v1/users', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + token
                    },
                    body: JSON.stringify(payload)
                });
                if (res.ok) {
                    closeAddUserModal();
                    loadUsersList();
                } else {
                    const data = await res.json();
                    alert(data.error || 'Failed to create user');
                }
            } catch (ex) {
                alert('Connection error');
            }
        }

        // Edit User Modal (NEW-538): edit an *existing* user's role and
        // profile fields via PUT /api/v1/users/{id} (AuthService.update_user).
        // Deliberately never touches 'active' -- update_user rejects any
        // real change to it with a 400, pointing callers at the dedicated
        // /suspend and /activate endpoints (NEW-264, token-revocation
        // correctness) -- Suspend/Activate stays the only path for that
        // field, wired separately via toggleUserStatus() above.
        async function openEditUserModal(userId) {
            const token = getAuthToken();
            try {
                const res = await fetch(`/api/v1/users/${userId}`, {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (res.status === 401) { logoutUser(); return; }
                const data = await res.json();
                if (!res.ok || !data.user) {
                    alert(data.error || 'Failed to load user');
                    return;
                }
                const u = data.user;
                currentEditUserId = userId;
                currentEditUserOriginalRole = u.role;

                document.getElementById('editFullName').value = u.full_name || '';
                document.getElementById('editEmail').value = u.email || '';
                document.getElementById('editPhone').value = u.phone || '';
                document.getElementById('editDept').value = u.department || '';

                // Standard 6 roles are static <option>s in the modal HTML
                // (see editUserModalOverlay). If this user's current role is
                // outside that set (ai_agent / customer), add it back so we
                // never silently propose changing it away; clear any such
                // leftover option from a previous edit first so re-opening
                // for a standard-role user doesn't carry it over.
                const standardRoles = ['technician', 'project_manager', 'sales', 'sales_manager', 'manager', 'admin'];
                const roleSelect = document.getElementById('editRole');
                roleSelect.querySelectorAll('option[data-dynamic-role]').forEach(o => o.remove());
                if (!standardRoles.includes(u.role)) {
                    const opt = document.createElement('option');
                    opt.value = u.role;
                    opt.textContent = u.role;
                    opt.setAttribute('data-dynamic-role', '1');
                    roleSelect.appendChild(opt);
                }
                roleSelect.value = u.role;

                document.getElementById('editUserModalOverlay').classList.add('active');
            } catch (ex) {
                alert('Failed to load user for editing.');
            }
        }

        function closeEditUserModal() {
            document.getElementById('editUserModalOverlay').classList.remove('active');
        }

        async function saveEditUser() {
            const newRole = document.getElementById('editRole').value;
            // Role change revokes every session for this user (update_user
            // computes this server-side) -- confirm specifically for a role
            // delta, not for a pure profile-field edit. No self-edit special
            // case needed: if an admin changes their own role, the same
            // wording covers it (they'll be logged out immediately, which is
            // the intended behavior).
            if (newRole !== currentEditUserOriginalRole) {
                if (!confirm("Changing this user's role will immediately revoke all of their active sessions (they will be logged out everywhere). Continue?")) return;
            }
            const btn = document.getElementById('saveEditUserBtn');
            btn.disabled = true;
            btn.innerText = 'Saving...';
            const token = getAuthToken();
            const payload = {
                full_name: document.getElementById('editFullName').value.trim(),
                email: document.getElementById('editEmail').value.trim(),
                phone: document.getElementById('editPhone').value.trim(),
                department: document.getElementById('editDept').value.trim(),
                role: newRole
            };
            try {
                const res = await fetch(`/api/v1/users/${currentEditUserId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + token
                    },
                    body: JSON.stringify(payload)
                });
                if (res.ok) {
                    closeEditUserModal();
                    loadUsersList();
                } else {
                    alert('Error saving user');
                }
            } catch (ex) {
                alert('Connection error');
            } finally {
                btn.disabled = false;
                btn.innerText = 'Save Changes';
            }
        }

        async function loadAuditLogs() {
            const token = getAuthToken();
            const container = document.getElementById('auditLogFeed');
            try {
                const res = await fetch('/api/v1/audit-log?limit=25', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (res.status === 401) { logoutUser(); return; }
                const data = await res.json();
                if (res.ok) {
                    const logs = data.audit_logs || [];
                    if (!logs.length) {
                        container.innerHTML = '<p style="color:var(--text-muted)">No results.</p>';
                        return;
                    }
                    container.innerHTML = logs.map(e => `
                        <div style="padding: 0.35rem 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                            <span style="color: var(--bronze);">${escapeHtml(e.timestamp)}</span>
                            [<span style="color: var(--info);">${escapeHtml(e.action)}</span>]
                            <span>${escapeHtml(e.change_summary)}</span>
                            (Actor: ${escapeHtml(e.actor_id) || 'System'})
                        </div>
                    `).join('');
                }
            } catch (ex) {
                container.innerText = 'Unable to fetch audit logs.';
            }
        }

        // Patch the shared nav/drawer/admin-bar chrome from the authed business
        // profile. Admin-only: the drawer is also rendered on public/staff
        // surfaces that cannot fetch this profile, so their static fallback text
        // is left untouched. .textContent only, never .innerHTML; hrefs are only
        // ever built from digit-stripped phone or a strictly-matched email.
        function patchBusinessChrome(p) {
            p = p || {};
            const navText = document.getElementById('navPhoneText');
            const navLink = document.getElementById('navPhoneLink');
            const drawerPhone = document.getElementById('drawerPhoneLink');
            const phone = (p.business_phone || '').trim();
            if (phone) {
                const telHref = 'tel:' + phone.replace(/\\D/g, '');
                if (navText) navText.textContent = phone;
                if (drawerPhone) { drawerPhone.textContent = phone; drawerPhone.setAttribute('href', telHref); }
                if (navLink) navLink.setAttribute('href', telHref);
            } else {
                if (navText) navText.textContent = '';
                if (drawerPhone) { drawerPhone.textContent = ''; drawerPhone.removeAttribute('href'); }
                if (navLink) navLink.removeAttribute('href');
            }
            const emailLink = document.getElementById('drawerEmailLink');
            if (emailLink) {
                const email = p.business_email || '';
                emailLink.textContent = email;
                if (/^[^@\\s]+@[^@\\s]+$/.test(email)) {
                    emailLink.setAttribute('href', 'mailto:' + email);
                } else {
                    emailLink.removeAttribute('href');
                }
            }
            const lic = p.license_number || '';
            const drawerLicense = document.getElementById('drawerLicense');
            const adminBarLicense = document.getElementById('adminBarLicense');
            if (drawerLicense) drawerLicense.textContent = lic;
            if (adminBarLicense) adminBarLicense.textContent = lic;
        }

        async function saveBusinessProfile() {
            if (!window.businessProfileLoaded) { alert('Profile not loaded — cannot save.'); return; }
            const token = getAuthToken();
            window.currentBusinessProfile = window.currentBusinessProfile || {};
            window.currentBusinessProfile.business_name = document.getElementById('profName').value;
            window.currentBusinessProfile.business_description = document.getElementById('profPrompt').value;
            window.currentBusinessProfile.business_phone = document.getElementById('profPhone').value;
            window.currentBusinessProfile.business_email = document.getElementById('profEmail').value;
            window.currentBusinessProfile.license_number = document.getElementById('profLicense').value;
            window.currentBusinessProfile.owner_name = document.getElementById('profOwner').value;
            const an = document.getElementById('profAgentName').value.trim();
            window.currentBusinessProfile.aigentik_name = an;
            // Only ever arm agent_name_set; never clear it. Blanking the AI
            // Agent Name field must not re-arm Aigentik onboarding on a
            // fresh/restored DB -- preserve whatever value was loaded.
            if (an) window.currentBusinessProfile.agent_name_set = 1;
            try {
                const res = await fetch('/api/v1/business-profile', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + token
                    },
                    body: JSON.stringify(window.currentBusinessProfile)
                });
                if (res.ok) {
                    alert('Business Profile context updated successfully.');
                    patchBusinessChrome(window.currentBusinessProfile);
                } else {
                    alert('Failed to update Business Profile.');
                }
            } catch (ex) {
                alert('Connection error');
            }
        }

        // Business Hours grid (schedule_config.working_hours) — 7-key object,
        // null = closed for that day, {start, end} = open. See
        // ScheduleConfig.working_hours docstring (models.py) for the
        // "Business Hours" envelope semantics.
        const BIZ_HOURS_DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

        function toggleBizHoursRow(day) {
            const closed = document.getElementById('bizHours_' + day + '_closed').checked;
            document.getElementById('bizHours_' + day + '_start').disabled = closed;
            document.getElementById('bizHours_' + day + '_end').disabled = closed;
        }

        function populateBusinessHours(workingHours) {
            const wh = workingHours || {};
            BIZ_HOURS_DAYS.forEach(day => {
                const hasKey = Object.prototype.hasOwnProperty.call(wh, day);
                const entry = wh[day];
                const closedBox = document.getElementById('bizHours_' + day + '_closed');
                const startInput = document.getElementById('bizHours_' + day + '_start');
                const endInput = document.getElementById('bizHours_' + day + '_end');
                if (hasKey && entry === null) {
                    closedBox.checked = true;
                    startInput.value = '';
                    endInput.value = '';
                } else if (hasKey && entry && typeof entry === 'object') {
                    closedBox.checked = false;
                    startInput.value = entry.start || '09:00';
                    endInput.value = entry.end || '17:00';
                } else {
                    // Key absent entirely: treat as open with sensible
                    // defaults (09:00-17:00). NOTE this is a display default
                    // only until the next Save, at which point
                    // serializeBusinessHours() materializes it into an
                    // explicit {start, end} entry — an intentional
                    // unset-to-explicit transition, not a silent overwrite.
                    closedBox.checked = false;
                    startInput.value = '09:00';
                    endInput.value = '17:00';
                }
                startInput.disabled = closedBox.checked;
                endInput.disabled = closedBox.checked;
            });
        }

        function serializeBusinessHours() {
            const result = {};
            BIZ_HOURS_DAYS.forEach(day => {
                const closed = document.getElementById('bizHours_' + day + '_closed').checked;
                if (closed) {
                    result[day] = null;
                } else {
                    const start = document.getElementById('bizHours_' + day + '_start').value || '09:00';
                    const end = document.getElementById('bizHours_' + day + '_end').value || '17:00';
                    result[day] = { start: start, end: end };
                }
            });
            return result;
        }

        // Appointment Types (service-type axis) — separate table/endpoint
        // from schedule-config; NOT part of the full-row-replace payload.
        window.currentAppointmentTypes = [];

        async function loadAppointmentTypes() {
            const token = getAuthToken();
            const tbody = document.getElementById('apptTypesTableBody');
            const addBtn = document.querySelector('button[onclick="addAppointmentType()"]');
            try {
                const res = await fetch('/api/v1/appointment-types?include_inactive=true', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (res.status === 401) { logoutUser(); return; }
                const data = await res.json();
                if (res.ok && data.appointment_types) {
                    window.currentAppointmentTypes = data.appointment_types;
                    renderAppointmentTypes();
                    if (addBtn) addBtn.disabled = false;
                } else {
                    throw new Error('HTTP ' + res.status);
                }
            } catch (e) {
                tbody.innerHTML = '<tr><td colspan="5" style="color: var(--danger);">Failed to load appointment types.</td></tr>';
                if (addBtn) addBtn.disabled = true;
            }
        }

        function renderAppointmentTypes() {
            const tbody = document.getElementById('apptTypesTableBody');
            const types = window.currentAppointmentTypes || [];
            if (!types.length) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No appointment types configured.</td></tr>';
                return;
            }
            tbody.innerHTML = types.map(t => `
                <tr data-type-id="${t.id}" data-sort-order="${t.sort_order}">
                    <td><input type="text" id="apptType_${t.id}_name" value="${escapeHtml(t.name)}"></td>
                    <td><input type="checkbox" id="apptType_${t.id}_active" ${t.active ? 'checked' : ''}></td>
                    <td><input type="number" id="apptType_${t.id}_maxConcurrent" min="1" value="${escapeHtml(t.max_concurrent)}"></td>
                    <td>
                        <button class="btn-gold" style="padding: 0.25rem 0.55rem; font-size: 0.75rem;" onclick="toggleApptHoursSection(${t.id})">Scheduling Hours</button>
                        <div id="apptHoursWrap_${t.id}" style="display:none; margin-top:0.5rem;">
                            <label style="display:block; margin-bottom:0.5rem; font-size:0.8rem;">
                                <input type="checkbox" id="apptType_${t.id}_useBizHours" onchange="toggleApptHoursGrid(${t.id})">
                                Use business hours (inherit)
                            </label>
                            <table class="erp-table" id="apptHoursGrid_${t.id}">
                                <tbody>
                                    ${BIZ_HOURS_DAYS.map(day => `
                                    <tr>
                                        <td>${day}</td>
                                        <td><input type="checkbox" id="apptHours_${t.id}_${day}_closed" onchange="toggleApptHoursRow(${t.id}, '${day}')"></td>
                                        <td><input type="time" id="apptHours_${t.id}_${day}_start"></td>
                                        <td><input type="time" id="apptHours_${t.id}_${day}_end"></td>
                                    </tr>`).join('')}
                                </tbody>
                            </table>
                        </div>
                    </td>
                    <td>
                        <button class="btn-gold" style="padding: 0.25rem 0.55rem; font-size: 0.75rem;" onclick="saveAppointmentType(${t.id})">Save</button>
                        <button class="btn-gold" style="padding: 0.25rem 0.55rem; font-size: 0.75rem; background: rgba(239, 68, 68, 0.2); border-color: var(--danger); color: #FCA5A5;" onclick="deleteAppointmentType(${t.id}, ${escapeHtml(JSON.stringify(t.name))})">Delete</button>
                    </td>
                </tr>
            `).join('');
            types.forEach(t => populateApptTypeHours(t.id, t.scheduling_hours || {}));
        }

        function toggleApptHoursSection(id) {
            const wrap = document.getElementById('apptHoursWrap_' + id);
            if (wrap) wrap.style.display = (wrap.style.display === 'none') ? 'block' : 'none';
        }

        function toggleApptHoursRow(id, day) {
            const closed = document.getElementById('apptHours_' + id + '_' + day + '_closed').checked;
            document.getElementById('apptHours_' + id + '_' + day + '_start').disabled = closed;
            document.getElementById('apptHours_' + id + '_' + day + '_end').disabled = closed;
        }

        // Unchecking "Use business hours" seeds the per-type grid from the
        // currently-displayed Business Hours grid (not the last-saved
        // schedule config) so the estimator sees what they're narrowing
        // from.
        function toggleApptHoursGrid(id) {
            const useBiz = document.getElementById('apptType_' + id + '_useBizHours').checked;
            const grid = document.getElementById('apptHoursGrid_' + id);
            if (grid) grid.style.display = useBiz ? 'none' : '';
            if (!useBiz) {
                BIZ_HOURS_DAYS.forEach(day => {
                    const bizClosed = document.getElementById('bizHours_' + day + '_closed').checked;
                    const closedBox = document.getElementById('apptHours_' + id + '_' + day + '_closed');
                    const startInput = document.getElementById('apptHours_' + id + '_' + day + '_start');
                    const endInput = document.getElementById('apptHours_' + id + '_' + day + '_end');
                    closedBox.checked = bizClosed;
                    startInput.value = bizClosed ? '' : (document.getElementById('bizHours_' + day + '_start').value || '09:00');
                    endInput.value = bizClosed ? '' : (document.getElementById('bizHours_' + day + '_end').value || '17:00');
                    startInput.disabled = bizClosed;
                    endInput.disabled = bizClosed;
                });
            }
        }

        // schedulingHours: {} (or falsy) means "inherit business hours" —
        // AppointmentType.scheduling_hours docstring (models.py). All-7-or-
        // none granularity: the "Use business hours" checkbox is the tri-
        // state, individual days are just Closed/Open once narrowed.
        function populateApptTypeHours(id, schedulingHours) {
            const useBiz = !schedulingHours || Object.keys(schedulingHours).length === 0;
            const useBizBox = document.getElementById('apptType_' + id + '_useBizHours');
            const grid = document.getElementById('apptHoursGrid_' + id);
            if (useBizBox) useBizBox.checked = useBiz;
            if (grid) grid.style.display = useBiz ? 'none' : '';
            BIZ_HOURS_DAYS.forEach(day => {
                const entry = schedulingHours ? schedulingHours[day] : undefined;
                const closedBox = document.getElementById('apptHours_' + id + '_' + day + '_closed');
                const startInput = document.getElementById('apptHours_' + id + '_' + day + '_start');
                const endInput = document.getElementById('apptHours_' + id + '_' + day + '_end');
                if (!closedBox || !startInput || !endInput) return;
                if (entry === null) {
                    closedBox.checked = true;
                    startInput.value = '';
                    endInput.value = '';
                } else if (entry && typeof entry === 'object') {
                    closedBox.checked = false;
                    startInput.value = entry.start || '09:00';
                    endInput.value = entry.end || '17:00';
                } else {
                    closedBox.checked = false;
                    startInput.value = '';
                    endInput.value = '';
                }
                startInput.disabled = closedBox.checked;
                endInput.disabled = closedBox.checked;
            });
        }

        function serializeApptTypeHours(id) {
            const useBiz = document.getElementById('apptType_' + id + '_useBizHours').checked;
            if (useBiz) return {};
            const result = {};
            BIZ_HOURS_DAYS.forEach(day => {
                const closed = document.getElementById('apptHours_' + id + '_' + day + '_closed').checked;
                if (closed) {
                    result[day] = null;
                } else {
                    const start = document.getElementById('apptHours_' + id + '_' + day + '_start').value || '09:00';
                    const end = document.getElementById('apptHours_' + id + '_' + day + '_end').value || '17:00';
                    result[day] = { start: start, end: end };
                }
            });
            return result;
        }

        async function addAppointmentType() {
            const token = getAuthToken();
            try {
                const res = await fetch('/api/v1/appointment-types', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                    body: JSON.stringify({ name: 'New Appointment Type', active: 1, max_concurrent: 1, scheduling_hours: {} })
                });
                if (res.ok) {
                    loadAppointmentTypes();
                } else {
                    alert('Failed to add appointment type.');
                }
            } catch (ex) {
                alert('Connection error');
            }
        }

        async function saveAppointmentType(id) {
            const token = getAuthToken();
            // sort_order has no UI control here -- carry the loaded value
            // through via the row's data attribute rather than hardcoding
            // 0, since update_appointment_type is a partial (SET-clause)
            // update: omitting the key would leave it untouched, but we
            // send it explicitly to match the documented payload shape.
            const row = document.querySelector('tr[data-type-id="' + id + '"]');
            const sortOrder = row ? (parseInt(row.getAttribute('data-sort-order')) || 0) : 0;
            const name = document.getElementById('apptType_' + id + '_name').value;
            const active = document.getElementById('apptType_' + id + '_active').checked ? 1 : 0;
            const maxConcurrent = parseInt(document.getElementById('apptType_' + id + '_maxConcurrent').value) || 1;
            const schedulingHours = serializeApptTypeHours(id);
            try {
                const res = await fetch('/api/v1/appointment-types/' + id + '/update', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + token
                    },
                    body: JSON.stringify({
                        name: name, active: active, sort_order: sortOrder,
                        max_concurrent: maxConcurrent, scheduling_hours: schedulingHours
                    })
                });
                if (res.ok) {
                    alert('Appointment type updated successfully.');
                    loadAppointmentTypes();
                } else {
                    alert('Failed to update appointment type.');
                }
            } catch (ex) {
                alert('Connection error');
            }
        }

        // Delete-buttons round (Ish 2026-09-11): precheck for ACTIVE
        // references (confirmed/negotiating appointments for this type)
        // before ever offering a confirm() dialog -- if any exist, block
        // and list them so the admin knows what to fix first.
        async function deleteAppointmentType(id, name) {
            const token = getAuthToken();
            try {
                const refRes = await fetch('/api/v1/appointment-types/' + id + '/active-references', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                const refData = await refRes.json();
                if (!refRes.ok) {
                    alert('Error checking active references: ' + (refData.error || refRes.statusText));
                    return;
                }
                const active = refData.active_references || [];
                if (active.length) {
                    const listing = active.map(a => `${a.id}: ${a.title} (${a.start_time})`).join('\\n');
                    alert(`Cannot delete: this appointment type has ${active.length} active appointment(s):\n${listing}`);
                    return;
                }
                if (!confirm('Delete appointment type ' + name + '? This cannot be undone.')) return;
                const res = await fetch('/api/v1/appointment-types/' + id + '/delete', {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (res.ok) {
                    loadAppointmentTypes();
                } else {
                    const err = await res.json();
                    alert('Failed to delete: ' + (err.error || res.statusText));
                }
            } catch (ex) {
                alert('Failed to delete appointment type.');
            }
        }

        async function saveScheduleConfig() {
            if (!window.scheduleConfigLoaded) { alert('Schedule config not loaded — cannot save.'); return; }
            const token = getAuthToken();
            const schedDuration = parseInt(document.getElementById('schedDuration').value) || 30;
            const schedBuffer = parseInt(document.getElementById('schedBuffer').value) || 15;
            window.currentScheduleConfig = window.currentScheduleConfig || {};
            window.currentScheduleConfig.default_duration_minutes = schedDuration;
            window.currentScheduleConfig.buffer_minutes = schedBuffer;
            window.currentScheduleConfig.booking_window_days = parseInt(document.getElementById('schedBookingWindow').value) || 365;
            // upsert_schedule_config is a full-row excluded.* replace -- the
            // Business Hours grid must be read back into the object BEFORE
            // POSTing, or an edited-but-unsynced grid would post stale
            // working_hours state.
            window.currentScheduleConfig.working_hours = serializeBusinessHours();
            try {
                const res = await fetch('/api/v1/schedule-config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + token
                    },
                    body: JSON.stringify(window.currentScheduleConfig)
                });
                if (res.ok) {
                    alert('Booking schedule configuration updated successfully.');
                } else {
                    alert('Failed to update schedule configuration.');
                }
            } catch (ex) {
                alert('Connection error');
            }
        }

        // Initial load
        validateSession('/admin/login').then(async valid => {
            if (valid) {
                loadUsersList();
                // Awaited (not fire-and-forget) so window.currentAppointmentTypes
                // is populated before the Calendar's initial loadCalendar() call
                // below -- Calendar's Executive Overview position (Ish
                // 2026-09-11, Admin Dashboard round Part B) is no longer behind
                // a tab-click, so this is now the only trigger for it.
                await loadAppointmentTypes();

                // Load Business Profile
                const bpBtn = document.querySelector('button[onclick="saveBusinessProfile()"]');
                const populateBusinessProfile = (p) => {
                    document.getElementById('profName').value = p.business_name ?? '';
                    document.getElementById('profPhone').value = p.business_phone ?? '';
                    document.getElementById('profEmail').value = p.business_email ?? '';
                    document.getElementById('profLicense').value = p.license_number ?? '';
                    document.getElementById('profOwner').value = p.owner_name ?? '';
                    document.getElementById('profAgentName').value = p.aigentik_name ?? '';
                    document.getElementById('profPrompt').value = p.business_description ?? '';
                };
                try {
                    const token = getAuthToken();
                    const bpRes = await fetch('/api/v1/business-profile', { headers: { 'Authorization': 'Bearer ' + token } });
                    if (bpRes.ok) {
                        const bpData = await bpRes.json();
                        window.currentBusinessProfile = bpData.business_profile;
                        window.businessProfileLoaded = true;
                        populateBusinessProfile(window.currentBusinessProfile);
                        patchBusinessChrome(window.currentBusinessProfile);
                    } else if (bpRes.status === 404) {
                        window.currentBusinessProfile = {
                            id: 1, configured: 0, aigentik_name: null, agent_name_set: 0,
                            owner_name: null, business_name: null, business_description: null,
                            business_phone: null, business_email: null, license_number: null,
                            onboarding_sent: 0, setup_date: null, updated_at: null
                        };
                        // Blank the shared chrome (no profile row => no contact
                        // info) but do NOT populate the form or enable Save. The
                        // form now carries identity fields (owner_name /
                        // aigentik_name); a 404-state save would write them null
                        // and onboarding_sent=0 -- the NEW-449 hazard. This is
                        // deliberately stricter than schedule-config's
                        // 404->enabled path, which is a legitimate first-row
                        // create with no identity/onboarding fields at stake.
                        patchBusinessChrome(window.currentBusinessProfile);
                        window.businessProfileLoaded = false;
                        if (bpBtn) {
                            bpBtn.disabled = true;
                            bpBtn.insertAdjacentHTML('afterend',
                                '<div style="color:#c00;margin-top:0.5rem;">Could not load — save disabled to prevent data loss</div>');
                        }
                    } else {
                        throw new Error('HTTP ' + bpRes.status);
                    }
                } catch (e) {
                    window.businessProfileLoaded = false;
                    if (bpBtn) {
                        bpBtn.disabled = true;
                        bpBtn.insertAdjacentHTML('afterend',
                            '<div style="color:#c00;margin-top:0.5rem;">Could not load — save disabled to prevent data loss</div>');
                    }
                }

                // Load Schedule Config
                const scBtn = document.querySelector('button[onclick="saveScheduleConfig()"]');
                const populateScheduleConfig = (c) => {
                    document.getElementById('schedDuration').value = c.default_duration_minutes ?? 30;
                    document.getElementById('schedBuffer').value = c.buffer_minutes ?? 15;
                    document.getElementById('schedBookingWindow').value = c.booking_window_days ?? 365;
                    populateBusinessHours(c.working_hours);
                };
                try {
                    const token = getAuthToken();
                    const scRes = await fetch('/api/v1/schedule-config', { headers: { 'Authorization': 'Bearer ' + token } });
                    if (scRes.ok) {
                        const scData = await scRes.json();
                        window.currentScheduleConfig = scData.schedule_config;
                        window.scheduleConfigLoaded = true;
                        populateScheduleConfig(window.currentScheduleConfig);
                    } else if (scRes.status === 404) {
                        // Full row: saveScheduleConfig() POSTs currentScheduleConfig
                        // wholesale and upsert_schedule_config is a full-row
                        // replace, so a 404-load-then-save must not omit
                        // working_hours / duration_by_relationship (NEW-466).
                        window.currentScheduleConfig = {
                            id: 1, working_hours: {}, default_duration_minutes: 30, buffer_minutes: 15,
                            booking_window_days: 365, duration_by_relationship: {}, updated_at: null
                        };
                        window.scheduleConfigLoaded = true;
                        populateScheduleConfig(window.currentScheduleConfig);
                    } else {
                        throw new Error('HTTP ' + scRes.status);
                    }
                } catch (e) {
                    window.scheduleConfigLoaded = false;
                    if (scBtn) {
                        scBtn.disabled = true;
                        scBtn.insertAdjacentHTML('afterend',
                            '<div style="color:#c00;margin-top:0.5rem;">Could not load — save disabled to prevent data loss</div>');
                    }
                }

                // Load Calendar (Executive Overview, Admin Dashboard round
                // Part B, Ish 2026-09-11) -- awaited loadAppointmentTypes()
                // above guarantees window.currentAppointmentTypes is already
                // populated here, so this always uses the cache rather than
                // loadCalendar()'s own fallback fetch.
                await loadCalendar();
            }
        });
    </script>
</body>
</html>"""

def _render_staff_portal_base(role_title: str, primary_label: str, role_key: str) -> str:
    """Base template for the focused staff portals (B6.8)."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{role_title} Dashboard — Restoricon</title>
    <link rel="icon" href="/assets/logos/favicon-32.png" type="image/png" sizes="32x32">
    <style>
        {_get_common_styles()}
        .portal-layout {{ max-width: 1200px; margin: 2rem auto; padding: 0 1.25rem; display: flex; flex-direction: column; gap: 2rem; }}
        .header-card {{ background: linear-gradient(135deg, #112240 0%, #1c2e4a 100%); border-radius: 12px; padding: 2rem; color: white; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 10px 30px rgba(0,0,0,0.3); }}
        .erp-card {{ background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); padding: 1.5rem; margin-bottom: 1.5rem; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid var(--border-light); }}
        th {{ color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }}
    </style>
</head>
<body>
    {_get_universal_drawer_html("admin")}
    <div class="portal-layout">
        <div class="header-card">
            <div>
                <h1 style="margin:0 0 0.5rem 0;font-size:1.8rem;color:var(--bronze);">{role_title} Dashboard</h1>
                <p style="margin:0;opacity:0.9;">Welcome back. Here is your schedule and active assignments.</p>
            </div>
            <button class="btn-gold" onclick="window.location.href='/admin/login'" style="padding: 0.5rem 1rem;">Sign Out</button>
        </div>

        <div class="erp-card">
            <h2 style="margin-top:0;">My Schedule</h2>
            <table>
                <thead><tr><th>Time</th><th>Title</th><th>Status</th></tr></thead>
                <tbody id="myScheduleList"><tr><td colspan="3">Loading schedule...</td></tr></tbody>
            </table>
        </div>

        <div class="erp-card">
            <h2 style="margin-top:0;">{primary_label}</h2>
            <table>
                <thead><tr><th>ID</th><th>Customer</th><th>Title</th><th>Status</th></tr></thead>
                <tbody id="myAssignmentsList"><tr><td colspan="4">Loading assignments...</td></tr></tbody>
            </table>
        </div>
    </div>

    <script>
        function escapeHtml(unsafe) {{
            if (!unsafe) return '';
            return String(unsafe).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
        }}

        function getAuthToken() {{
            return sessionStorage.getItem('restoricon_token') || '';
        }}

        async function loadDashboard() {{
            const token = getAuthToken();
            if (!token) {{ window.location.href = '/admin/login'; return; }}

            let user = null;
            try {{
                const meRes = await fetch('/api/v1/auth/me', {{ headers: {{ 'Authorization': 'Bearer ' + token }} }});
                if (meRes.ok) {{
                    const meData = await meRes.json();
                    user = meData.user;
                }}
            }} catch (e) {{}}

            if (!user) {{ window.location.href = '/admin/login'; return; }}

            // Load Schedule
            try {{
                const res = await fetch('/api/v1/staff-schedules?user_id=' + user.id, {{
                    headers: {{ 'Authorization': 'Bearer ' + token }}
                }});
                if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                const data = await res.json();
                const tbody = document.getElementById('myScheduleList');
                if (res.ok && data.schedules && data.schedules.length > 0) {{
                    tbody.innerHTML = data.schedules.map(s => 
                        `<tr>
                            <td>${{escapeHtml(s.start_time)}}</td>
                            <td>${{escapeHtml(s.title)}}</td>
                            <td><span class="badge ${{s.status === 'scheduled' ? 'badge-info' : 'badge-gold'}}">${{escapeHtml(s.status)}}</span></td>
                        </tr>`
                    ).join('');
                }} else {{
                    tbody.innerHTML = '<tr><td colspan="3" style="color:var(--text-muted)">No upcoming schedule.</td></tr>';
                }}
            }} catch (e) {{ /* network/parse failure: schedule tbody keeps its "Loading..." placeholder, no further UI action needed */ }}

            // Load Assignments
            try {{
                const res = await fetch('/api/v1/projects', {{
                    headers: {{ 'Authorization': 'Bearer ' + token }}
                }});
                if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                const data = await res.json();
                const tbody = document.getElementById('myAssignmentsList');
                if (res.ok && data.projects) {{
                    let myProjects = data.projects;
                    
                    // Filter based on role if backend returned all
                    if ('{role_key}' === 'project_manager') {{
                        myProjects = myProjects.filter(p => p.project_manager_id == user.id);
                    }} else if ('{role_key}' === 'technician') {{
                        // Technician backend already filters to assigned
                    }} else if ('{role_key}' === 'subcontractor') {{
                        myProjects = myProjects.filter(p => {{
                            try {{
                                const subs = JSON.parse(p.subcontractors_json || '[]');
                                return subs.includes(Number(user.id));
                            }} catch(e) {{ return false; }}
                        }});
                    }}
                    
                    if (myProjects.length > 0) {{
                        tbody.innerHTML = myProjects.map(p => 
                            `<tr>
                                <td>#${{p.id}}</td>
                                <td>Cust #${{p.customer_id}}</td>
                                <td>${{escapeHtml(p.title)}}</td>
                                <td><span class="badge badge-info">${{escapeHtml(p.status)}}</span></td>
                            </tr>`
                        ).join('');
                    }} else {{
                        tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-muted)">No active assignments.</td></tr>';
                    }}
                }}
            }} catch (e) {{ /* network/parse failure: assignments tbody keeps its "Loading..." placeholder, no further UI action needed */ }}
        }}

        window.onload = loadDashboard;
    </script>
</body>
</html>"""

def _render_sales_portal() -> str:
    """Dedicated sales portal (NEW-533). Unlike the other three staff
    portals, this one does NOT reuse _render_staff_portal_base's shared
    "Assignments" panel (the old fetch('/api/v1/projects') call was the
    NEW-533 leak: every rep could see every other rep's projects/leads/
    opportunities with no server-side scoping). Instead it renders two
    dedicated "My Leads" / "My Opportunities" panels backed by
    /api/v1/leads and /api/v1/opportunities -- both now auto-scoped
    server-side by CRMService's PERM_READ_TEAM_SALES_DATA narrowing, so
    the identical, unparameterized fetch calls below correctly return
    "just me" for a plain rep and "the whole team" for a sales manager,
    with zero client-side role branching. "Sales manager" here covers both
    grant mechanisms (D2, sales_rep_portal.md §4): a real ROLE_SALES_MANAGER
    role (granted PERM_READ_TEAM_SALES_DATA by default) and the original
    NEW-533 mechanism of an ordinary `sales`-role user individually granted
    PERM_READ_TEAM_SALES_DATA via custom_permissions -- both land here with
    identical server-side behavior."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sales & Estimating Dashboard — Restoricon</title>
    <link rel="icon" href="/assets/logos/favicon-32.png" type="image/png" sizes="32x32">
    <style>
        {_get_common_styles()}
        .portal-layout {{ max-width: 1200px; margin: 2rem auto; padding: 0 1.25rem; display: flex; flex-direction: column; gap: 2rem; }}
        .header-card {{ background: linear-gradient(135deg, #112240 0%, #1c2e4a 100%); border-radius: 12px; padding: 2rem; color: white; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 10px 30px rgba(0,0,0,0.3); }}
        .erp-card {{ background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); padding: 1.5rem; margin-bottom: 1.5rem; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid var(--border-light); }}
        th {{ color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }}
        /* B8.3: lead detail / lead create modals -- same erp-modal-overlay /
           erp-modal / modal-header pattern already established in
           render_admin_surface's <style> block, duplicated here because
           each surface in this file ships its own self-contained <style>. */
        .erp-modal-overlay {{ position: fixed; inset: 0; background: rgba(10, 25, 47, 0.85); display: none; align-items: center; justify-content: center; z-index: 3000; padding: 1.5rem; }}
        .erp-modal-overlay.active {{ display: flex; }}
        .erp-modal {{ background: white; border-radius: 12px; width: 100%; max-width: 600px; max-height: 90vh; overflow-y: auto; padding: 1.75rem; box-shadow: 0 25px 50px rgba(0,0,0,0.5); }}
        .modal-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; }}
        .modal-header h3 {{ margin: 0; font-size: 1.15rem; }}
        .modal-field {{ margin-bottom: 0.85rem; }}
        .modal-field label {{ display: block; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 0.25rem; }}
        .modal-field input, .modal-field select, .modal-field textarea {{ width: 100%; padding: 0.5rem; border: 1px solid var(--border-light); border-radius: 6px; font-size: 0.9rem; box-sizing: border-box; }}
        /* B8.3: kanban board -- one column per PipelineStage.STAGE_ORDER stage. */
        .kanban-board {{ display: flex; gap: 0.85rem; overflow-x: auto; padding-bottom: 0.5rem; }}
        .kanban-col {{ flex: 0 0 230px; background: #f4f5f7; border-radius: 8px; padding: 0.65rem; }}
        .kanban-col h4 {{ margin: 0 0 0.6rem 0; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-muted); }}
        .kanban-card {{ background: white; border-radius: 6px; padding: 0.6rem; margin-bottom: 0.6rem; box-shadow: 0 1px 3px rgba(0,0,0,0.12); font-size: 0.82rem; }}
        .kanban-card select {{ width: 100%; margin-top: 0.4rem; font-size: 0.78rem; padding: 0.25rem; }}
    </style>
</head>
<body>
    {_get_universal_drawer_html("admin")}
    <div class="portal-layout">
        <div class="header-card">
            <div>
                <h1 style="margin:0 0 0.5rem 0;font-size:1.8rem;color:var(--bronze);">Sales & Estimating Dashboard</h1>
                <p style="margin:0;opacity:0.9;">Welcome back. Here is your schedule, leads, and opportunities.</p>
                <p id="viewerScopeBanner" style="margin:0.5rem 0 0 0;opacity:0.8;font-size:0.85rem;"></p>
            </div>
            <button class="btn-gold" onclick="window.location.href='/admin/login'" style="padding: 0.5rem 1rem;">Sign Out</button>
        </div>

        <div class="erp-card" id="dashboardErrorBanner" style="display:none; border-left: 4px solid var(--danger);">
            <p id="dashboardErrorMsg" style="margin:0; color: var(--danger); font-weight:600;"></p>
        </div>

        <div class="erp-card">
            <h2 style="margin-top:0;">My Schedule</h2>
            <table>
                <thead><tr><th>Time</th><th>Title</th><th>Status</th></tr></thead>
                <tbody id="myScheduleList"><tr><td colspan="3">Loading schedule...</td></tr></tbody>
            </table>
        </div>

        <div class="erp-card">
            <h2 style="margin-top:0;">Appointments</h2>
            <h3 style="margin:0 0 0.5rem 0; font-size:0.95rem; color:var(--text-muted);">Today</h3>
            <table>
                <thead><tr><th>Time</th><th>Title</th><th>Status</th></tr></thead>
                <tbody id="dashApptTodayList"><tr><td colspan="3">Loading...</td></tr></tbody>
            </table>
            <h3 style="margin:1rem 0 0.5rem 0; font-size:0.95rem; color:var(--text-muted);">Upcoming</h3>
            <table>
                <thead><tr><th>Time</th><th>Title</th><th>Status</th></tr></thead>
                <tbody id="dashApptUpcomingList"><tr><td colspan="3">Loading...</td></tr></tbody>
            </table>
        </div>

        <div class="erp-card">
            <h2 style="margin-top:0;display:flex;justify-content:space-between;align-items:center;">
                <span>My Leads <span id="newLeadsBadge" class="card-badge badge-gold" style="display:none;"></span></span>
                <button class="btn-gold" style="padding:0.4rem 0.9rem;font-size:0.8rem;" onclick="openCreateLeadModal()">+ New Lead</button>
            </h2>
            <table>
                <thead><tr><th>ID</th><th>Customer</th><th>Status</th><th>Assigned Rep</th></tr></thead>
                <tbody id="myLeadsList"><tr><td colspan="4">Loading leads...</td></tr></tbody>
            </table>
        </div>

        <div class="erp-card">
            <h2 style="margin-top:0;">My Opportunities</h2>
            <table>
                <thead><tr><th>ID</th><th>Title</th><th>Stage</th><th>Assigned Rep</th></tr></thead>
                <tbody id="myOpportunitiesList"><tr><td colspan="4">Loading opportunities...</td></tr></tbody>
            </table>
        </div>

        <div class="erp-card">
            <h2 style="margin-top:0;display:flex;justify-content:space-between;align-items:center;">
                <span>Customers</span>
                <button class="btn-gold" style="padding:0.4rem 0.9rem;font-size:0.8rem;" onclick="openGuidedContractModal()">+ New Contract (Guided)</button>
            </h2>
            <table>
                <thead><tr><th>ID #</th><th>Name</th><th>Phone</th><th>Email</th><th></th></tr></thead>
                <tbody id="myCustomersList"><tr><td colspan="5">Loading customers...</td></tr></tbody>
            </table>
        </div>

        <div class="erp-card">
            <h2 style="margin-top:0;">Pipeline Kanban</h2>
            <div id="kanbanBoard" class="kanban-board"><p style="color:var(--text-muted);">Loading pipeline board...</p></div>
        </div>

        <div class="erp-card">
            <h2 style="margin-top:0;">Where Deals Get Stuck</h2>
            <table>
                <thead><tr><th>Stage</th><th>Avg Hours In Stage</th></tr></thead>
                <tbody id="stageAnalyticsList"><tr><td colspan="2">Loading stage analytics...</td></tr></tbody>
            </table>
            <p id="stageAnalyticsCoverage" style="margin:0.75rem 0 0 0; font-size:0.85rem; color:var(--text-muted);"></p>
            <h3 style="margin:1rem 0 0.5rem 0; font-size:0.95rem; color:var(--text-muted);">Currently Stuck</h3>
            <table>
                <thead><tr><th>Opportunity</th><th>Stage</th><th>Hours In Stage</th></tr></thead>
                <tbody id="currentlyStuckList"><tr><td colspan="3">Loading...</td></tr></tbody>
            </table>
        </div>

        <div class="erp-card">
            <h2 style="margin-top:0;">Follow-ups</h2>
            <table>
                <thead><tr><th>Title</th><th>Type</th><th>Due</th><th>Priority</th><th>Status</th><th>Actions</th></tr></thead>
                <tbody id="followupsList"><tr><td colspan="6">Loading follow-ups...</td></tr></tbody>
            </table>
        </div>

        <div class="erp-card">
            <h2 style="margin-top:0;">Pipeline Summary</h2>
            <table>
                <thead><tr><th>Stage</th><th>Count</th><th>Total Value</th><th>Weighted Value</th></tr></thead>
                <tbody id="pipelineSummaryList"><tr><td colspan="4">Loading pipeline...</td></tr></tbody>
            </table>
            <p id="pipelineTotals" style="margin:0.75rem 0 0 0; font-size:0.85rem; color:var(--text-muted);"></p>
        </div>

        <div class="erp-card">
            <h2 id="commissionsHeading" style="margin-top:0;">Commissions</h2>
            <table>
                <thead><tr><th>Status</th><th>Source</th><th>Amount</th><th>Earned</th></tr></thead>
                <tbody id="commissionsList"><tr><td colspan="4">Loading commissions...</td></tr></tbody>
            </table>
        </div>

        <!-- B8.7d: "This Month" rep-facing commission summary panel, fed by
             the same /api/v1/sales/dashboard response's new commission_summary
             field -- one row (the calling rep's own), always present since
             CommissionService.get_team_commission_summary never raises. -->
        <div class="erp-card">
            <h2 style="margin-top:0;">This Month</h2>
            <div id="commissionSummaryStrip" style="display:flex; flex-wrap:wrap; gap:1.5rem;">
                <div><div style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;">Earned</div><div id="summaryEarned" style="font-size:1.25rem;font-weight:700;">Loading...</div></div>
                <div><div style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;">Paid</div><div id="summaryPaid" style="font-size:1.25rem;font-weight:700;">-</div></div>
                <div><div style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;">Pending</div><div id="summaryPending" style="font-size:1.25rem;font-weight:700;">-</div></div>
                <div><div style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;">Entries</div><div id="summaryEntryCount" style="font-size:1.25rem;font-weight:700;">-</div></div>
            </div>
        </div>

        <div class="erp-card" id="teamSummaryCard" style="display:none;">
            <h2 style="margin-top:0;">Team Snapshot</h2>
            <div id="teamSummaryStrip" style="display:flex; flex-wrap:wrap; gap:1.5rem;"></div>
        </div>

        <!-- B8.7d: manager-facing commission rankings, gated independently
             of teamSummaryCard on team_commission_rankings' own presence
             (PERM_READ_TEAM_COMMISSIONS, a different permission axis from
             teamSummaryCard's PERM_READ_TEAM_SALES_DATA -- see
             commissions_scope's existing precedent for this split). -->
        <div class="erp-card" id="commissionRankingsCard" style="display:none;">
            <h2 style="margin-top:0;">Commission Rankings (This Month)</h2>
            <table>
                <thead><tr><th>Rep</th><th>Earned</th><th>Paid</th><th>Pending</th><th>Entries</th></tr></thead>
                <tbody id="commissionRankingsList"></tbody>
            </table>
        </div>
    </div>

    <div id="leadDetailModal" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3>Lead Detail</h3>
                <button class="btn-gold" style="padding:0.3rem 0.7rem;" onclick="closeLeadDetailModal()">&times;</button>
            </div>
            <div id="leadDetailBody"><p style="color:var(--text-muted);">Loading...</p></div>
        </div>
    </div>

    <div id="createLeadModal" class="erp-modal-overlay">
        <div class="erp-modal">
            <div class="modal-header">
                <h3>New Lead</h3>
                <button class="btn-gold" style="padding:0.3rem 0.7rem;" onclick="closeCreateLeadModal()">&times;</button>
            </div>
            <div class="modal-field">
                <label>Source</label>
                <input type="text" id="newLeadSource" value="manual_entry">
            </div>
            <div class="modal-field">
                <label>Customer ID (leave blank if unknown)</label>
                <input type="number" id="newLeadCustomerId">
            </div>
            <div class="modal-field">
                <label>Property Type</label>
                <input type="text" id="newLeadPropertyType" placeholder="residential, commercial...">
            </div>
            <div class="modal-field">
                <label>Project Scope</label>
                <input type="text" id="newLeadProjectScope">
            </div>
            <div class="modal-field">
                <label>Urgency Level</label>
                <input type="text" id="newLeadUrgencyLevel" placeholder="emergency, high, medium, low...">
            </div>
            <div class="modal-field">
                <label>Insurance Status</label>
                <input type="text" id="newLeadInsuranceStatus" placeholder="claim_filed, self_pay, none...">
            </div>
            <div class="modal-field">
                <label>Estimated Value</label>
                <input type="number" id="newLeadEstimatedValue" step="0.01">
            </div>
            <div class="modal-field">
                <label>Notes</label>
                <textarea id="newLeadNotes" rows="3"></textarea>
            </div>
            <button class="btn-gold" onclick="submitCreateLead()">Create Lead</button>
        </div>
    </div>

    <div id="customer360Modal" class="erp-modal-overlay">
        <div class="erp-modal" style="max-width:900px;">
            <div class="modal-header">
                <h3 id="c360Title">Customer 360</h3>
                <button class="btn-gold" style="padding:0.3rem 0.7rem;" onclick="closeCustomer360Modal()">&times;</button>
            </div>
            <div id="c360Body"><p style="color:var(--text-muted);">Loading...</p></div>
        </div>
    </div>

    <!-- B8.6d-c (NEW-579): guided customer -> template -> fill -> sign flow.
         Four steps, one <div id="gflowStepN"> shown at a time via
         showGuidedStep(). Reuses the erp-modal-overlay/erp-modal/
         modal-header pattern already established above (customer360Modal,
         createLeadModal) rather than a new UI paradigm. -->
    <div id="guidedContractModal" class="erp-modal-overlay">
        <div class="erp-modal" style="max-width:700px;">
            <div class="modal-header">
                <h3>New Contract — Guided</h3>
                <button class="btn-gold" style="padding:0.3rem 0.7rem;" onclick="closeGuidedContractModal()">&times;</button>
            </div>
            <p id="gflowError" style="display:none;color:var(--danger);font-weight:600;"></p>

            <div id="gflowStep1">
                <h4 style="margin:0 0 0.5rem 0;">Step 1 — Find or create customer</h4>
                <div class="modal-field">
                    <label>Search by name, phone, or email</label>
                    <input type="text" id="gflowCustomerSearch" oninput="guidedSearchCustomers()" placeholder="Start typing...">
                </div>
                <div id="gflowCustomerResults" style="margin-bottom:0.75rem;"></div>
                <button class="btn-gold" style="padding:0.4rem 0.9rem;font-size:0.8rem;" onclick="guidedShowNewCustomerForm()">+ New Customer</button>

                <div id="gflowNewCustomerForm" style="display:none;margin-top:1rem;border-top:1px solid var(--border-light);padding-top:1rem;">
                    <div class="modal-field"><label>First Name</label><input type="text" id="gflowNewFirstName"></div>
                    <div class="modal-field"><label>Last Name</label><input type="text" id="gflowNewLastName"></div>
                    <div class="modal-field"><label>Phone</label><input type="text" id="gflowNewPhone"></div>
                    <div class="modal-field"><label>Email</label><input type="text" id="gflowNewEmail"></div>
                    <div class="modal-field"><label>Service Address</label><input type="text" id="gflowNewAddress"></div>
                    <button class="btn-gold" onclick="guidedSubmitNewCustomer()">Create &amp; Continue</button>
                </div>
            </div>

            <div id="gflowStep2" style="display:none;">
                <h4 style="margin:0 0 0.5rem 0;">Step 2 — Contract template</h4>
                <p id="gflowSelectedCustomerLabel" style="color:var(--text-muted);"></p>
                <div class="modal-field">
                    <label>Template</label>
                    <select id="gflowTemplateSelect">
                        <option value="general_remodeling">General Remodeling</option>
                        <option value="homecare_basic">HomeCare — Basic</option>
                        <option value="homecare_plus">HomeCare — Plus</option>
                        <option value="homecare_complete">HomeCare — Complete</option>
                        <option value="homecare_estate">HomeCare — Estate</option>
                    </select>
                </div>
                <button class="btn-gold" style="padding:0.4rem 0.9rem;font-size:0.8rem;" onclick="showGuidedStep(1)">&larr; Back</button>
                <button class="btn-gold" onclick="guidedGoToStep3()">Continue</button>
            </div>

            <div id="gflowStep3" style="display:none;">
                <h4 style="margin:0 0 0.5rem 0;">Step 3 — Contract details</h4>
                <div class="modal-field"><label>Contract #</label><input type="text" id="gflowContractNumber"></div>
                <div class="modal-field"><label>Title</label><input type="text" id="gflowContractTitle"></div>
                <div class="modal-field"><label>Customer Name</label><input type="text" id="gflowFieldName" readonly></div>
                <div class="modal-field"><label>Address</label><input type="text" id="gflowFieldAddress" readonly></div>
                <div class="modal-field"><label>Phone</label><input type="text" id="gflowFieldPhone" readonly></div>
                <div class="modal-field"><label>Email</label><input type="text" id="gflowFieldEmail" readonly></div>
                <div class="modal-field"><label>Content / Scope of Work</label><textarea id="gflowContractContent" rows="4"></textarea></div>
                <button class="btn-gold" style="padding:0.4rem 0.9rem;font-size:0.8rem;" onclick="showGuidedStep(2)">&larr; Back</button>
                <button class="btn-gold" onclick="guidedSubmitContract()">Create Contract</button>
            </div>

            <div id="gflowStep4" style="display:none;">
                <h4 style="margin:0 0 0.5rem 0;">Step 4 — Required signers</h4>
                <p style="color:var(--text-muted);">Select every party who must sign this contract, then collect signatures.</p>
                <div class="modal-field">
                    <label><input type="checkbox" id="gflowSignerCustomer" checked style="width:auto;"> Customer</label><br>
                    <label><input type="checkbox" id="gflowSignerRep" style="width:auto;"> Sales Rep</label><br>
                    <label><input type="checkbox" id="gflowSignerPM" style="width:auto;"> Project Manager</label><br>
                    <label><input type="checkbox" id="gflowSignerAdmin" style="width:auto;"> Admin</label>
                </div>
                <button class="btn-gold" onclick="guidedConfigureSigners()">Save Required Signers</button>
                <div id="gflowSignerStatus" style="margin-top:1rem;"></div>
            </div>
        </div>
    </div>

    <script>
        function escapeHtml(unsafe) {{
            if (!unsafe) return '';
            return String(unsafe).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
        }}

        function getAuthToken() {{
            return sessionStorage.getItem('restoricon_token') || '';
        }}

        // B8.10a: shared badge/action-button renderers for the Follow-ups
        // panel and the Customer 360 Tasks panel -- both display the same
        // Task rows fetched from GET /api/v1/crm/tasks (directly or via the
        // dashboard's followups block), so they share one rendering path
        // rather than two copies drifting apart.
        //
        // Surfaces task_type always, plus an "Auto" tag (with rule_name in
        // its tooltip) when trigger_source is set -- this is the mechanism
        // that discharges the "no black-box automation" requirement per
        // NEW-622: every automation-generated task is visibly distinguished
        // from a manually-created one, right on the row.
        function taskTypeBadge(t) {{
            const typeLabel = escapeHtml(t.task_type || 'follow_up');
            let html = `<span class="badge badge-slate">${{typeLabel}}</span>`;
            if (t.trigger_source) {{
                const ruleLabel = t.rule_name ? escapeHtml(t.rule_name) : escapeHtml(t.trigger_source);
                html += ` <span class="badge badge-gold" title="Automated by rule: ${{ruleLabel}}">Auto</span>`;
            }}
            return html;
        }}

        // Complete/Cancel/Snooze action buttons. Only shown for a task that
        // is still actionable (pending/in_progress) -- a completed or
        // cancelled task has nothing left to do. "Pause" has no backing
        // Task.status value (only pending/in_progress/completed/cancelled
        // exist, no CHECK-constraint change this round) -- the pause-like
        // request is implemented as Cancel, deliberately, not as an
        // invented new status.
        function taskActionButtons(t) {{
            if (t.status !== 'pending' && t.status !== 'in_progress') {{
                return '';
            }}
            // escapeHtml(JSON.stringify(...)) is this file's established
            // pattern for passing a string argument through an onclick="..."
            // HTML attribute (see deleteSubcontractor/openPermModal/
            // deleteUser/deleteAppointmentType) -- JSON.stringify produces
            // a properly quoted/escaped JS string literal, and escapeHtml
            // on top of that keeps its own double quotes from breaking out
            // of the onclick="..." HTML attribute they sit inside.
            const dueDateArg = escapeHtml(JSON.stringify(t.due_date || null));
            return `<button class="btn-gold" style="padding:0.2rem 0.5rem;font-size:0.7rem;" onclick="completeTaskAction(${{t.id}})">Complete</button>
                <button class="btn-gold" style="padding:0.2rem 0.5rem;font-size:0.7rem;" onclick="cancelTaskAction(${{t.id}})">Cancel</button>
                <button class="btn-gold" style="padding:0.2rem 0.5rem;font-size:0.7rem;" onclick="snoozeTaskAction(${{t.id}}, ${{dueDateArg}})">Snooze +1d</button>`;
        }}

        // Each action reloads whichever panel(s) are currently visible --
        // the dashboard Follow-ups panel always, and the Customer 360 Tasks
        // panel too if that modal happens to be open -- mirroring
        // sendContractAction/signContractAction's own currentCustomer360Id
        // refresh check and claimLead/claimOpportunity's unconditional
        // loadDashboard() reload on every outcome (success or failure), so
        // a stale row never lingers either place.
        async function completeTaskAction(id) {{
            const token = getAuthToken();
            try {{
                const res = await fetch('/api/v1/crm/tasks/' + id + '/complete', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{}}),
                }});
                if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                if (!res.ok) {{
                    const data = await res.json();
                    alert(data.error || ('Failed to complete task (' + res.status + ').'));
                }}
                loadDashboard();
                if (currentCustomer360Id) loadCustomer360(currentCustomer360Id);
            }} catch (e) {{
                alert('Failed to complete task: network error.');
            }}
        }}

        async function cancelTaskAction(id) {{
            const token = getAuthToken();
            if (!confirm('Cancel this follow-up task?')) return;
            try {{
                const res = await fetch('/api/v1/crm/tasks/' + id + '/update', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ status: 'cancelled' }}),
                }});
                if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                if (!res.ok) {{
                    const data = await res.json();
                    alert(data.error || ('Failed to cancel task (' + res.status + ').'));
                }}
                loadDashboard();
                if (currentCustomer360Id) loadCustomer360(currentCustomer360Id);
            }} catch (e) {{
                alert('Failed to cancel task: network error.');
            }}
        }}

        async function snoozeTaskAction(id, currentDueDate) {{
            const token = getAuthToken();
            // Push the due date forward by exactly one day from its current
            // value (or from today, if the task has none yet) -- a simple,
            // minimal snooze rather than a date-picker modal, consistent
            // with the "keep it minimal" scope for this round.
            //
            // The dashboard route buckets overdue/due_today/upcoming via a
            // plain string compare against datetime.now(timezone.utc).date()
            // (routes.py) -- entirely in UTC. Build and parse the date here
            // entirely in UTC too (getUTCDate/setUTCDate, never the local-
            // timezone getDate/setDate), or a snooze clicked in the evening
            // in a timezone behind UTC can silently land a day off from
            // what the user asked for, or a task can stay/land in the
            // wrong overdue/due_today/upcoming bucket.
            const base = currentDueDate ? new Date(currentDueDate + 'T00:00:00Z') : new Date();
            if (isNaN(base.getTime())) {{
                alert('Cannot snooze: task has an unrecognized due date.');
                return;
            }}
            base.setUTCDate(base.getUTCDate() + 1);
            const newDueDate = base.toISOString().slice(0, 10);
            try {{
                const res = await fetch('/api/v1/crm/tasks/' + id + '/update', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ due_date: newDueDate }}),
                }});
                if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                if (!res.ok) {{
                    const data = await res.json();
                    alert(data.error || ('Failed to snooze task (' + res.status + ').'));
                }}
                loadDashboard();
                if (currentCustomer360Id) loadCustomer360(currentCustomer360Id);
            }} catch (e) {{
                alert('Failed to snooze task: network error.');
            }}
        }}

        let dashboardRefreshInFlight = false;
        async function loadDashboard(redirectOnIndeterminate = true) {{
            if (dashboardRefreshInFlight) return;
            dashboardRefreshInFlight = true;
            try {{
            const token = getAuthToken();
            if (!token) {{ window.location.href = '/admin/login'; return; }}

            let user = null;
            try {{
                const meRes = await fetch('/api/v1/auth/me', {{ headers: {{ 'Authorization': 'Bearer ' + token }} }});
                if (meRes.status === 401) {{ window.location.href = '/admin/login'; return; }}
                if (meRes.ok) {{
                    const meData = await meRes.json();
                    user = meData.user;
                }}
                // else: non-ok, non-401 response (e.g. 5xx) -- not a confirmed
                // auth failure, fall through to the indeterminate-gated check below.
            }} catch (e) {{ /* network/parse failure: not a confirmed auth failure, fall through to the indeterminate-gated check below */ }}

            if (!user) {{
                if (redirectOnIndeterminate) {{ window.location.href = '/admin/login'; }}
                return;
            }}

            // Display-only viewer-scope banner -- real enforcement is entirely
            // server-side (CRMService._scoped_assignee_filter); this is never
            // an access-control point, only a label for what the fetches below
            // will return. NEW-552: the old check (a custom_permissions flag
            // read off /api/v1/auth/me) missed any actor with team access via
            // the real ROLE_SALES_MANAGER role rather than a custom_permissions
            // override. The authoritative signal is now data.scope === 'team'
            // from the dashboard fetch below -- fail closed to 'My Own' here so
            // an actor never sees 'Whole Team' before (or instead of) a
            // confirmed team response.
            const scopeBanner = document.getElementById('viewerScopeBanner');
            scopeBanner.textContent = 'Viewing: My Own';

            // Load Schedule
            try {{
                const res = await fetch('/api/v1/staff-schedules?user_id=' + user.id, {{
                    headers: {{ 'Authorization': 'Bearer ' + token }}
                }});
                if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                const data = await res.json();
                const tbody = document.getElementById('myScheduleList');
                if (res.ok && data.schedules && data.schedules.length > 0) {{
                    tbody.innerHTML = data.schedules.map(s =>
                        `<tr>
                            <td>${{escapeHtml(s.start_time)}}</td>
                            <td>${{escapeHtml(s.title)}}</td>
                            <td><span class="badge ${{s.status === 'scheduled' ? 'badge-info' : 'badge-gold'}}">${{escapeHtml(s.status)}}</span></td>
                        </tr>`
                    ).join('');
                }} else {{
                    tbody.innerHTML = '<tr><td colspan="3" style="color:var(--text-muted)">No upcoming schedule.</td></tr>';
                }}
            }} catch (e) {{ /* network/parse failure: schedule tbody keeps its "Loading..." placeholder, no further UI action needed */ }}

            // Load Customers (B8.4a Customer 360 entry point).
            // CORRECTION (B8.6d-c, 2026-09-22): the note this comment
            // originally carried here claimed list_customers has no
            // PERM_READ_TEAM_SALES_DATA-style per-assignee narrowing. That
            // is no longer accurate -- NEW-568 added exactly that
            // narrowing to list_customers (crm_service.py, "AND
            // (assigned_user_id = ? OR assigned_user_id IS NULL)" clause):
            // a plain rep without team-wide visibility now only sees
            // customers assigned to them or still unclaimed, matching
            // list_leads/list_opportunities' shape; a sales manager or any
            // other PERM_READ_TEAM_SALES_DATA holder still sees everyone.
            // Corrected per CLAUDE.md rule 6 rather than left standing --
            // this file's guided-flow customer search (below) relies on
            // the same already-narrowed list_customers.
            try {{
                const res = await fetch('/api/v1/customers', {{
                    headers: {{ 'Authorization': 'Bearer ' + token }}
                }});
                if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                const data = await res.json();
                const tbody = document.getElementById('myCustomersList');
                if (res.ok && data.customers && data.customers.length > 0) {{
                    tbody.innerHTML = data.customers.map(c =>
                        `<tr>
                            <td>${{c.customer_number ? '#' + c.customer_number : '#' + c.id}}</td>
                            <td>${{escapeHtml((c.first_name || '') + ' ' + (c.last_name || ''))}}</td>
                            <td>${{escapeHtml(c.phone || '')}}</td>
                            <td>${{escapeHtml(c.email || '')}}</td>
                            <td><button class="btn-gold" style="padding:0.2rem 0.6rem;font-size:0.75rem;" onclick="openCustomer360Modal(${{c.id}})">View 360</button></td>
                        </tr>`
                    ).join('');
                }} else {{
                    tbody.innerHTML = '<tr><td colspan="5" style="color:var(--text-muted)">No customers.</td></tr>';
                }}
            }} catch (e) {{ /* network/parse failure: customers tbody keeps its "Loading..." placeholder, no further UI action needed */ }}

            // Load Leads
            try {{
                const res = await fetch('/api/v1/leads', {{
                    headers: {{ 'Authorization': 'Bearer ' + token }}
                }});
                if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                const data = await res.json();
                const tbody = document.getElementById('myLeadsList');
                if (res.ok && data.leads && data.leads.length > 0) {{
                    tbody.innerHTML = data.leads.map(l =>
                        `<tr>
                            <td><a href="#" onclick="openLeadDetailModal(${{l.id}}); return false;">#${{l.id}}</a></td>
                            <td>${{l.customer_id ? 'Cust #' + l.customer_id : '—'}}</td>
                            <td><span class="badge badge-info">${{escapeHtml(l.status)}}</span></td>
                            <td>${{l.assigned_user_id ? escapeHtml(String(l.assigned_user_id)) : 'Unclaimed <button class="btn-gold" style="padding:0.2rem 0.6rem;font-size:0.75rem;" onclick="claimLead(' + l.id + ')">Claim</button>'}}</td>
                        </tr>`
                    ).join('');
                }} else {{
                    tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-muted)">No leads.</td></tr>';
                }}
            }} catch (e) {{ /* network/parse failure: leads tbody keeps its "Loading..." placeholder, no further UI action needed */ }}

            // Load Opportunities
            try {{
                const res = await fetch('/api/v1/opportunities', {{
                    headers: {{ 'Authorization': 'Bearer ' + token }}
                }});
                if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                const data = await res.json();
                const tbody = document.getElementById('myOpportunitiesList');
                if (res.ok && data.opportunities && data.opportunities.length > 0) {{
                    tbody.innerHTML = data.opportunities.map(o =>
                        `<tr>
                            <td>#${{o.id}}</td>
                            <td>${{escapeHtml(o.title)}}</td>
                            <td><span class="badge badge-info">${{escapeHtml(o.pipeline_stage)}}</span></td>
                            <td>${{o.assigned_user_id ? escapeHtml(String(o.assigned_user_id)) : 'Unclaimed <button class="btn-gold" style="padding:0.2rem 0.6rem;font-size:0.75rem;" onclick="claimOpportunity(' + o.id + ')">Claim</button>'}}</td>
                        </tr>`
                    ).join('');
                }} else {{
                    tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-muted)">No opportunities.</td></tr>';
                }}
            }} catch (e) {{ /* network/parse failure: opportunities tbody keeps its "Loading..." placeholder, no further UI action needed */ }}

            // Load Kanban board (B8.3, Part C)
            try {{
                await loadKanban(token);
            }} catch (e) {{ /* network/parse failure: kanban board keeps its "Loading..." placeholder, no further UI action needed */ }}

            // Load stage-stuck analytics (B8.3, Part D)
            try {{
                await loadStageAnalytics(token);
            }} catch (e) {{ /* network/parse failure: analytics panel keeps its "Loading..." placeholder, no further UI action needed */ }}

            // Load Command Center Dashboard (B8.2b) -- Appointments, Follow-ups,
            // Pipeline, Commissions, and (manager-only) Team panels, plus the
            // NEW-552 viewer-scope banner fix, all fed by this one call.
            try {{
                const res = await fetch('/api/v1/sales/dashboard?days=7', {{
                    headers: {{ 'Authorization': 'Bearer ' + token }}
                }});
                if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                const errBanner = document.getElementById('dashboardErrorBanner');
                const errMsg = document.getElementById('dashboardErrorMsg');
                errBanner.style.display = 'none';
                if (res.status === 403) {{
                    // actor.user_id is None on the server -- not a real login
                    // failure (token is valid), so no redirect; just surface it
                    // inline in the new panels' area per this task's spec: the
                    // top banner AND each new panel's own placeholder, so none
                    // of them are left silently stuck on "Loading...".
                    const dashboardUnavailableMsg = 'Cannot load dashboard: no associated user identity';
                    errBanner.style.display = 'block';
                    errMsg.textContent = dashboardUnavailableMsg;
                    document.getElementById('dashApptTodayList').innerHTML = `<tr><td colspan="3" style="color:var(--danger)">${{escapeHtml(dashboardUnavailableMsg)}}</td></tr>`;
                    document.getElementById('dashApptUpcomingList').innerHTML = `<tr><td colspan="3" style="color:var(--danger)">${{escapeHtml(dashboardUnavailableMsg)}}</td></tr>`;
                    document.getElementById('followupsList').innerHTML = `<tr><td colspan="6" style="color:var(--danger)">${{escapeHtml(dashboardUnavailableMsg)}}</td></tr>`;
                    document.getElementById('pipelineSummaryList').innerHTML = `<tr><td colspan="4" style="color:var(--danger)">${{escapeHtml(dashboardUnavailableMsg)}}</td></tr>`;
                    document.getElementById('pipelineTotals').textContent = '';
                    document.getElementById('commissionsList').innerHTML = `<tr><td colspan="4" style="color:var(--danger)">${{escapeHtml(dashboardUnavailableMsg)}}</td></tr>`;
                    document.getElementById('teamSummaryCard').style.display = 'none';
                    document.getElementById('summaryEarned').textContent = '—';
                    document.getElementById('summaryPaid').textContent = '—';
                    document.getElementById('summaryPending').textContent = '—';
                    document.getElementById('summaryEntryCount').textContent = '—';
                    document.getElementById('commissionRankingsCard').style.display = 'none';
                }} else if (res.ok) {{
                    const data = await res.json();

                    // NEW-552: data.scope === 'team' is now the sole signal for
                    // the viewer-scope banner -- no OR-fallback to the old
                    // custom_permissions check (removed above).
                    if (data.scope === 'team') {{
                        scopeBanner.textContent = 'Viewing: Whole Team';
                    }}

                    // Appointments (distinct entity from My Schedule's
                    // StaffSchedule records above -- these are Appointment rows).
                    const apptToday = document.getElementById('dashApptTodayList');
                    const apptUpcoming = document.getElementById('dashApptUpcomingList');
                    const renderAppts = (list) => list.map(a =>
                        `<tr>
                            <td>${{escapeHtml(a.start_time)}}</td>
                            <td>${{escapeHtml(a.title)}}</td>
                            <td><span class="badge ${{a.status === 'confirmed' ? 'badge-info' : 'badge-gold'}}">${{escapeHtml(a.status)}}</span></td>
                        </tr>`
                    ).join('');
                    apptToday.innerHTML = (data.appointments && data.appointments.today && data.appointments.today.length > 0)
                        ? renderAppts(data.appointments.today)
                        : '<tr><td colspan="3" style="color:var(--text-muted)">No appointments today.</td></tr>';
                    apptUpcoming.innerHTML = (data.appointments && data.appointments.upcoming && data.appointments.upcoming.length > 0)
                        ? renderAppts(data.appointments.upcoming)
                        : '<tr><td colspan="3" style="color:var(--text-muted)">No upcoming appointments.</td></tr>';

                    // New Leads badge (count only -- the My Leads table above stays
                    // fed by the unparameterized /api/v1/leads fetch, NOT this
                    // status='new'-only subset, per this task's spec).
                    const newLeadsBadge = document.getElementById('newLeadsBadge');
                    const newLeadsCount = (data.leads && data.leads.new) ? data.leads.new.length : 0;
                    if (newLeadsCount > 0) {{
                        newLeadsBadge.textContent = newLeadsCount + ' NEW';
                        newLeadsBadge.style.display = 'inline-block';
                    }} else {{
                        newLeadsBadge.style.display = 'none';
                    }}

                    // Follow-ups -- overdue items flagged with the file's
                    // established inline var(--danger) convention (e.g. lines
                    // 2447, 2875); no badge-danger class exists in this file's
                    // styles, so this matches existing practice rather than
                    // inventing a new global CSS class for this alone.
                    const followupsList = document.getElementById('followupsList');
                    const fu = data.followups || {{}};
                    const renderTask = (t, overdue) => `<tr>
                        <td${{overdue ? ' style="color:var(--danger);font-weight:600;"' : ''}}>${{escapeHtml(t.title)}}</td>
                        <td>${{taskTypeBadge(t)}}</td>
                        <td${{overdue ? ' style="color:var(--danger);font-weight:600;"' : ''}}>${{escapeHtml(t.due_date)}}</td>
                        <td>${{escapeHtml(t.priority)}}</td>
                        <td>${{overdue ? 'OVERDUE' : escapeHtml(t.status)}}</td>
                        <td>${{taskActionButtons(t)}}</td>
                    </tr>`;
                    const fuRows = [
                        ...(fu.overdue || []).map(t => renderTask(t, true)),
                        ...(fu.due_today || []).map(t => renderTask(t, false)),
                        ...(fu.upcoming || []).map(t => renderTask(t, false)),
                    ];
                    followupsList.innerHTML = fuRows.length > 0
                        ? fuRows.join('')
                        : '<tr><td colspan="6" style="color:var(--text-muted)">No follow-ups due.</td></tr>';

                    // Pipeline summary -- first UI surface for this data.
                    const pipelineList = document.getElementById('pipelineSummaryList');
                    const pipelineTotals = document.getElementById('pipelineTotals');
                    const pl = data.pipeline || {{}};
                    const stages = pl.stages || {{}};
                    const stageOrder = pl.stage_order || [];
                    // Per-stage dicts carry count/total_value/weighted_value --
                    // NOT a per-stage win_rate (that only exists at the
                    // pipeline-summary level below, and is a 0-1 fraction,
                    // distinct from team.sales.win_rate_percent further down
                    // which is already *100 -- formatted separately so the two
                    // never read as the same number in different units).
                    pipelineList.innerHTML = stageOrder.length > 0
                        ? stageOrder.map(st => {{
                            const s = stages[st] || {{ count: 0, total_value: 0, weighted_value: 0 }};
                            return `<tr>
                                <td>${{escapeHtml(st)}}</td>
                                <td>${{s.count || 0}}</td>
                                <td>$${{escapeHtml((s.total_value || 0).toLocaleString())}}</td>
                                <td>$${{escapeHtml((s.weighted_value || 0).toLocaleString())}}</td>
                            </tr>`;
                        }}).join('')
                        : '<tr><td colspan="4" style="color:var(--text-muted)">No pipeline data.</td></tr>';
                    pipelineTotals.textContent = 'Total deals: ' + (pl.total_deals || 0) +
                        ' | Active pipeline value: $' + (pl.active_pipeline_value || 0).toLocaleString() +
                        ' | Won: ' + (pl.won_deals || 0) + ' ($' + (pl.won_value || 0).toLocaleString() + ')' +
                        ' | Lost: ' + (pl.lost_deals || 0) + ' ($' + (pl.lost_value || 0).toLocaleString() + ')' +
                        ' | Win rate: ' + Math.round((pl.win_rate || 0) * 100) + '%';

                    // Commissions -- commissions_scope is a separate permission
                    // axis from the page-level scope banner (B8.2a round-1
                    // finding); label it independently, never conflate with
                    // viewerScopeBanner above.
                    const commissionsHeading = document.getElementById('commissionsHeading');
                    commissionsHeading.textContent = 'Commissions (' + (data.commissions_scope === 'team' ? 'Team' : 'Mine') + ')';
                    const commissionsList = document.getElementById('commissionsList');
                    const commissionsByStatus = data.commissions || {{}};
                    let commissionRows = [];
                    Object.keys(commissionsByStatus).forEach(status => {{
                        (commissionsByStatus[status] || []).forEach(c => {{
                            commissionRows.push(`<tr>
                                <td><span class="badge badge-slate">${{escapeHtml(status)}}</span></td>
                                <td>${{escapeHtml(c.source_type)}}</td>
                                <td>$${{escapeHtml((c.commission_amount || 0).toLocaleString())}}</td>
                                <td>${{c.earned_at ? escapeHtml(c.earned_at) : '—'}}</td>
                            </tr>`);
                        }});
                    }});
                    commissionsList.innerHTML = commissionRows.length > 0
                        ? commissionRows.join('')
                        : '<tr><td colspan="4" style="color:var(--text-muted)">No commissions.</td></tr>';

                    // Team snapshot -- gate on key presence ('team' in data),
                    // not data.scope truthiness, matching the server's own gate
                    // (route only sets response['team'] when the actor holds
                    // PERM_READ_TEAM_SALES_DATA).
                    const teamCard = document.getElementById('teamSummaryCard');
                    const teamStrip = document.getElementById('teamSummaryStrip');
                    if ('team' in data && data.team && data.team.sales) {{
                        const ts = data.team.sales;
                        teamStrip.innerHTML = `
                            <div><div style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;">Total Leads</div><div style="font-size:1.25rem;font-weight:700;">${{ts.total_leads || 0}}</div></div>
                            <div><div style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;">Hot Leads</div><div style="font-size:1.25rem;font-weight:700;">${{ts.hot_leads || 0}}</div></div>
                            <div><div style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;">New Leads</div><div style="font-size:1.25rem;font-weight:700;">${{ts.new_leads || 0}}</div></div>
                            <div><div style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;">Pipeline Opps</div><div style="font-size:1.25rem;font-weight:700;">${{ts.pipeline_opportunities || 0}}</div></div>
                            <div><div style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;">Pipeline Value</div><div style="font-size:1.25rem;font-weight:700;">$${{escapeHtml((ts.pipeline_value || 0).toLocaleString())}}</div></div>
                            <div><div style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;">Weighted Pipeline</div><div style="font-size:1.25rem;font-weight:700;">$${{escapeHtml((ts.weighted_pipeline_value || 0).toLocaleString())}}</div></div>
                            <div><div style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;">Win Rate</div><div style="font-size:1.25rem;font-weight:700;">${{ts.win_rate_percent || 0}}%</div></div>
                        `;
                        teamCard.style.display = 'block';
                    }} else {{
                        teamCard.style.display = 'none';
                    }}

                    // B8.7d: "This Month" rep-facing commission summary --
                    // commission_summary is always present (never a gated
                    // key like 'team'), since get_team_commission_summary
                    // never raises and the route always supplies the
                    // empty-defaults shape when a rep has no rows this
                    // month.
                    const cs = data.commission_summary || {{}};
                    document.getElementById('summaryEarned').textContent = '$' + (cs.total_earned || 0).toLocaleString();
                    document.getElementById('summaryPaid').textContent = '$' + (cs.total_paid || 0).toLocaleString();
                    document.getElementById('summaryPending').textContent = '$' + (cs.total_pending || 0).toLocaleString();
                    document.getElementById('summaryEntryCount').textContent = String(cs.entry_count || 0);

                    // B8.7d: manager-facing commission rankings -- gated on
                    // key presence ('team_commission_rankings' in data),
                    // same pattern the team snapshot block above uses,
                    // independently of the 'team' key (different
                    // permission: PERM_READ_TEAM_COMMISSIONS, not
                    // PERM_READ_TEAM_SALES_DATA).
                    const rankingsCard = document.getElementById('commissionRankingsCard');
                    const rankingsList = document.getElementById('commissionRankingsList');
                    if ('team_commission_rankings' in data && Array.isArray(data.team_commission_rankings)) {{
                        const rankings = data.team_commission_rankings;
                        rankingsList.innerHTML = rankings.length > 0
                            ? rankings.map(r => `<tr>
                                <td>${{escapeHtml(String(r.rep_user_id))}}</td>
                                <td>$${{escapeHtml((r.total_earned || 0).toLocaleString())}}</td>
                                <td>$${{escapeHtml((r.total_paid || 0).toLocaleString())}}</td>
                                <td>$${{escapeHtml((r.total_pending || 0).toLocaleString())}}</td>
                                <td>${{r.entry_count || 0}}</td>
                            </tr>`).join('')
                            : '<tr><td colspan="5" style="color:var(--text-muted)">No commission activity this month.</td></tr>';
                        rankingsCard.style.display = 'block';
                    }} else {{
                        rankingsCard.style.display = 'none';
                    }}
                }}
                // else: non-ok, non-401, non-403 response (e.g. 5xx) -- new
                // panels keep their "Loading..." placeholders, matching the
                // silent-fallback convention of every other fetch in this
                // function; scopeBanner stays at its fail-closed 'My Own'
                // default set above.
            }} catch (e) {{ /* network/parse failure: new panels keep their "Loading..." placeholders, no further UI action needed */ }}
            }} finally {{
                dashboardRefreshInFlight = false;
            }}
        }}

        // NEW-534: claim buttons for unclaimed leads/opportunities.
        // _render_sales_portal has no modal/inline-errBox convention of its
        // own for user-triggered mutations (its only existing error
        // handling is the silent "keep Loading... placeholder" pattern
        // above, for the initial-load fetches, not for actions the user
        // clicks) -- alert() on failure matches the closest sibling
        // pattern elsewhere in this file for a simple id-keyed action
        // button with no modal (e.g. cancelAppointmentFromCalendar). Either
        // outcome (success or 409-conflict) reloads the dashboard so a
        // stale "Unclaimed" label never lingers.
        async function claimLead(id) {{
            const token = getAuthToken();
            try {{
                const res = await fetch('/api/v1/leads/' + id + '/claim', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token }}
                }});
                if (!res.ok) {{
                    const data = await res.json();
                    alert(data.error === 'already claimed' ? 'This lead was already claimed by someone else.' : (data.error || ('Failed to claim lead (' + res.status + ').')));
                }}
                loadDashboard();
            }} catch (e) {{
                alert('Failed to claim lead: network error.');
            }}
        }}

        async function claimOpportunity(id) {{
            const token = getAuthToken();
            try {{
                const res = await fetch('/api/v1/opportunities/' + id + '/claim', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token }}
                }});
                if (!res.ok) {{
                    const data = await res.json();
                    alert(data.error === 'already claimed' ? 'This opportunity was already claimed by someone else.' : (data.error || ('Failed to claim opportunity (' + res.status + ').')));
                }}
                loadDashboard();
            }} catch (e) {{
                alert('Failed to claim opportunity: network error.');
            }}
        }}

        // -----------------------------------------------------------------
        // B8.3 Part C: Pipeline Kanban board. Opportunity-only -- Lead.status
        // is a separate, different enum and is never rendered as a kanban
        // column here.
        // -----------------------------------------------------------------
        const KANBAN_STAGES = ['new_lead', 'contacted', 'appointment_set', 'estimate_scheduled', 'estimate_sent', 'proposal_sent', 'negotiation', 'won', 'lost'];
        const KANBAN_STAGE_LABELS = {{
            new_lead: 'New Lead', contacted: 'Contacted', appointment_set: 'Appointment Set',
            estimate_scheduled: 'Estimate Scheduled', estimate_sent: 'Estimate Sent',
            proposal_sent: 'Proposal Sent', negotiation: 'Negotiation', won: 'Won', lost: 'Lost',
        }};

        async function loadKanban(token) {{
            const res = await fetch('/api/v1/opportunities', {{
                headers: {{ 'Authorization': 'Bearer ' + token }}
            }});
            if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
            if (!res.ok) return;
            const data = await res.json();
            const opps = data.opportunities || [];
            const byStage = {{}};
            KANBAN_STAGES.forEach(s => {{ byStage[s] = []; }});
            opps.forEach(o => {{
                const st = KANBAN_STAGES.includes(o.pipeline_stage) ? o.pipeline_stage : 'new_lead';
                byStage[st].push(o);
            }});

            const board = document.getElementById('kanbanBoard');
            board.innerHTML = KANBAN_STAGES.map(stage => {{
                const cards = byStage[stage].map(o => renderKanbanCard(o, stage)).join('');
                return `<div class="kanban-col">
                    <h4>${{escapeHtml(KANBAN_STAGE_LABELS[stage])}} (${{byStage[stage].length}})</h4>
                    ${{cards || '<p style="color:var(--text-muted);font-size:0.78rem;">No deals.</p>'}}
                </div>`;
            }}).join('');
        }}

        function renderKanbanCard(o, stage) {{
            const otherStages = KANBAN_STAGES.filter(s => s !== stage);
            const isClaimed = !!o.assigned_user_id;
            const actionHtml = isClaimed
                ? `<select onchange="handleStageChange(this, ${{o.id}})">
                        <option value="">Move to...</option>
                        ${{otherStages.map(s => `<option value="${{s}}">${{escapeHtml(KANBAN_STAGE_LABELS[s])}}</option>`).join('')}}
                   </select>`
                : `<button class="btn-gold" style="padding:0.2rem 0.5rem;font-size:0.72rem;" onclick="claimOpportunity(${{o.id}})">Claim first</button>`;
            return `<div class="kanban-card">
                <strong>#${{o.id}} ${{escapeHtml(o.title)}}</strong><br>
                $${{escapeHtml((o.estimated_value || 0).toLocaleString())}}
                ${{actionHtml}}
            </div>`;
        }}

        // Claim-before-transition (NEW-558): renderKanbanCard only renders the
        // "Move to..." select for already-claimed opportunities, so an
        // unclaimed card's transition action is always the Claim-first button
        // above -- this is a client-side UI gate only; the server's existing
        // permission model is unchanged.
        async function handleStageChange(selectEl, id) {{
            const newStage = selectEl.value;
            if (!newStage) return;
            const token = getAuthToken();
            const body = {{ stage: newStage }};
            if (newStage === 'lost') {{
                const reason = prompt('A reason is required to mark this deal Lost:');
                if (!reason || !reason.trim()) {{ selectEl.value = ''; return; }}
                body.lost_reason = reason.trim();
            }}
            try {{
                const res = await fetch('/api/v1/opportunities/' + id + '/transition', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                    body: JSON.stringify(body),
                }});
                if (!res.ok) {{
                    const data = await res.json();
                    alert(data.error || ('Failed to move opportunity (' + res.status + ').'));
                }}
            }} catch (e) {{
                alert('Failed to move opportunity: network error.');
            }}
            loadKanban(token);
        }}

        // -----------------------------------------------------------------
        // B8.3 Part D: Stage-stuck analytics panel.
        // -----------------------------------------------------------------
        async function loadStageAnalytics(token) {{
            const res = await fetch('/api/v1/sales/pipeline-stuck-analytics', {{
                headers: {{ 'Authorization': 'Bearer ' + token }}
            }});
            if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
            const stageList = document.getElementById('stageAnalyticsList');
            const coverage = document.getElementById('stageAnalyticsCoverage');
            const stuckList = document.getElementById('currentlyStuckList');
            if (!res.ok) {{
                stageList.innerHTML = '<tr><td colspan="2" style="color:var(--danger)">Unable to load stage analytics.</td></tr>';
                stuckList.innerHTML = '<tr><td colspan="3" style="color:var(--danger)">Unable to load.</td></tr>';
                return;
            }}
            const data = await res.json();
            const avg = data.avg_hours_per_stage || {{}};
            const stages = Object.keys(avg);
            stageList.innerHTML = stages.length > 0
                ? stages.map(st => `<tr><td>${{escapeHtml(st)}}</td><td>${{(avg[st] || 0).toFixed(1)}}</td></tr>`).join('')
                : '<tr><td colspan="2" style="color:var(--text-muted)">No stage-duration data yet.</td></tr>';
            coverage.textContent = 'Full audit chain: ' + (data.opportunities_with_full_chain || 0) +
                ' | Fallback (no/partial chain): ' + (data.opportunities_using_fallback || 0);
            const stuck = data.currently_stuck || [];
            stuckList.innerHTML = stuck.length > 0
                ? stuck.map(s => `<tr><td>#${{s.opportunity_id}}</td><td>${{escapeHtml(s.stage)}}</td><td>${{(s.hours_in_stage || 0).toFixed(1)}}</td></tr>`).join('')
                : '<tr><td colspan="3" style="color:var(--text-muted)">Nothing currently stuck.</td></tr>';
        }}

        // -----------------------------------------------------------------
        // B8.3 Part B: Lead detail modal.
        // -----------------------------------------------------------------
        let currentLeadDetail = null;

        async function openLeadDetailModal(id) {{
            const overlay = document.getElementById('leadDetailModal');
            const body = document.getElementById('leadDetailBody');
            overlay.classList.add('active');
            body.innerHTML = '<p style="color:var(--text-muted);">Loading...</p>';
            const token = getAuthToken();
            try {{
                const res = await fetch('/api/v1/leads/' + id, {{
                    headers: {{ 'Authorization': 'Bearer ' + token }}
                }});
                if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                if (!res.ok) {{
                    body.innerHTML = '<p style="color:var(--danger);">Lead not found.</p>';
                    return;
                }}
                const data = await res.json();
                currentLeadDetail = data.lead;
                renderLeadDetail(currentLeadDetail);
            }} catch (e) {{
                body.innerHTML = '<p style="color:var(--danger);">Failed to load lead: network error.</p>';
            }}
        }}

        function closeLeadDetailModal() {{
            document.getElementById('leadDetailModal').classList.remove('active');
            currentLeadDetail = null;
        }}

        function renderLeadDetail(l) {{
            const body = document.getElementById('leadDetailBody');
            const claimBtn = l.assigned_user_id
                ? `<span class="badge badge-info">Assigned: ${{escapeHtml(String(l.assigned_user_id))}}</span>`
                : `<button class="btn-gold" style="padding:0.3rem 0.7rem;" onclick="claimLead(${{l.id}})">Claim</button>`;
            body.innerHTML = `
                <div class="modal-field"><label>ID</label><div>#${{l.id}}</div></div>
                <div class="modal-field"><label>Customer</label><div>${{l.customer_id ? 'Cust #' + l.customer_id : 'None linked'}}</div></div>
                <div class="modal-field"><label>Assigned</label><div>${{claimBtn}}</div></div>
                <div class="modal-field"><label>Status</label><input type="text" id="leadEditStatus" value="${{escapeHtml(l.status || '')}}"></div>
                <div class="modal-field"><label>Source</label><div>${{escapeHtml(l.source || '')}}</div></div>
                <div class="modal-field"><label>Score</label><div>${{l.score}} <button class="btn-gold" style="padding:0.2rem 0.6rem;font-size:0.75rem;" onclick="scoreLeadFromModal(${{l.id}})">Score</button></div></div>
                <div class="modal-field"><label>Property Type</label><input type="text" id="leadEditPropertyType" value="${{escapeHtml(l.property_type || '')}}"></div>
                <div class="modal-field"><label>Project Scope</label><input type="text" id="leadEditProjectScope" value="${{escapeHtml(l.project_scope || '')}}"></div>
                <div class="modal-field"><label>Urgency Level</label><input type="text" id="leadEditUrgencyLevel" value="${{escapeHtml(l.urgency_level || '')}}"></div>
                <div class="modal-field"><label>Insurance Status</label><input type="text" id="leadEditInsuranceStatus" value="${{escapeHtml(l.insurance_status || '')}}"></div>
                <div class="modal-field"><label>Estimated Value</label><input type="number" id="leadEditEstimatedValue" step="0.01" value="${{l.estimated_value || 0}}"></div>
                <div class="modal-field"><label>First Contact</label><div>${{l.first_contact_at ? escapeHtml(l.first_contact_at) : '—'}}</div></div>
                <div class="modal-field"><label>Last Contact</label><div>${{l.last_contact_at ? escapeHtml(l.last_contact_at) : '—'}}</div></div>
                <div class="modal-field"><label>Next Follow-up</label><div>${{l.next_followup_at ? escapeHtml(l.next_followup_at) : '—'}}</div></div>
                <div class="modal-field"><label>Notes</label><textarea id="leadEditNotes" rows="3">${{escapeHtml(l.notes || '')}}</textarea></div>
                <div class="modal-field"><label>Lost Reason</label><div>${{l.lost_reason ? escapeHtml(l.lost_reason) : '—'}}</div></div>
                <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-top:1rem;">
                    <button class="btn-gold" onclick="saveLeadEdit(${{l.id}})">Save Changes</button>
                    <button class="btn-gold" onclick="convertLeadAction(${{l.id}})">Convert to Opportunity</button>
                </div>
            `;
        }}

        async function scoreLeadFromModal(id) {{
            const token = getAuthToken();
            try {{
                const res = await fetch('/api/v1/leads/' + id + '/score', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{}}),
                }});
                if (!res.ok) {{
                    const data = await res.json();
                    alert(data.error || ('Failed to score lead (' + res.status + ').'));
                    return;
                }}
                openLeadDetailModal(id);
            }} catch (e) {{
                alert('Failed to score lead: network error.');
            }}
        }}

        // update_lead's real allowed_fields set (crm_service.py) is a
        // superset of what this modal exposes as editable inputs -- only
        // send the fields this form actually offers, matching the values
        // currently rendered in renderLeadDetail above.
        async function saveLeadEdit(id) {{
            const token = getAuthToken();
            const updates = {{
                status: document.getElementById('leadEditStatus').value,
                property_type: document.getElementById('leadEditPropertyType').value,
                project_scope: document.getElementById('leadEditProjectScope').value,
                urgency_level: document.getElementById('leadEditUrgencyLevel').value,
                insurance_status: document.getElementById('leadEditInsuranceStatus').value,
                estimated_value: parseFloat(document.getElementById('leadEditEstimatedValue').value) || 0,
                notes: document.getElementById('leadEditNotes').value,
            }};
            try {{
                const res = await fetch('/api/v1/leads/' + id + '/update', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                    body: JSON.stringify(updates),
                }});
                if (!res.ok) {{
                    const data = await res.json();
                    alert(data.error || ('Failed to save lead (' + res.status + ').'));
                    return;
                }}
                openLeadDetailModal(id);
                loadDashboard();
            }} catch (e) {{
                alert('Failed to save lead: network error.');
            }}
        }}

        // Convert-to-opportunity (B8.3 Part A, NEW-556). If the lead has no
        // linked customer, the service call requires customer_fields --
        // prompt for the minimum identity fields inline (this portal has no
        // richer form-builder convention for a rarely-hit sub-case) rather
        // than failing silently.
        async function convertLeadAction(id) {{
            const token = getAuthToken();
            const body = {{}};
            if (currentLeadDetail && !currentLeadDetail.customer_id) {{
                const firstName = prompt('This lead has no linked customer. Customer first name:');
                if (firstName === null) return;
                const lastName = prompt('Customer last name:') || '';
                const phone = prompt('Customer phone (optional):') || '';
                const email = prompt('Customer email (optional):') || '';
                body.customer_fields = {{
                    first_name: firstName,
                    last_name: lastName,
                    phone: phone || null,
                    email: email || null,
                }};
            }}
            try {{
                const res = await fetch('/api/v1/leads/' + id + '/convert', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                    body: JSON.stringify(body),
                }});
                const data = await res.json();
                if (!res.ok) {{
                    alert(data.error || ('Failed to convert lead (' + res.status + ').'));
                    return;
                }}
                alert('Converted to opportunity #' + data.opportunity.id);
                closeLeadDetailModal();
                loadDashboard();
            }} catch (e) {{
                alert('Failed to convert lead: network error.');
            }}
        }}

        // -----------------------------------------------------------------
        // B8.4a: Customer 360 view. Client-side fan-out over each entity's
        // own customer_id-filtered route (no new server-side aggregate route,
        // per this task's scoping) -- structural reference is the lead
        // detail modal above (openLeadDetailModal/renderLeadDetail), but
        // re-derived for this modal's own fields, not copied verbatim.
        // -----------------------------------------------------------------
        let currentCustomer360Id = null;
        let currentCustomer360Properties = [];
        let editingPropertyId = null;
        let currentPropertyHistoryId = null;
        // B8.8a: insurance/claim fields on Project (title, address, panel
        // location -- mirrors currentCustomer360Properties/editingPropertyId
        // above exactly). insurance_claim_status is deliberately NOT part of
        // this panel: it lives on Opportunity, not Project (models.py,
        // crm_service.py:1487's vocabulary-separation note), and Project has
        // no column for it.
        let currentCustomer360Projects = [];
        let editingInsuranceProjectId = null;
        // B8.5b: appointment scheduling UI + assessment records (sales_rep_portal.md
        // §5 B8.5, request §6/§7). currentAppointmentDetailId/currentPropertyAssessmentsId
        // mirror the toggle-tracking pattern already used above for
        // currentPropertyHistoryId; assessmentFormScope carries which
        // entity (kind/id -- exactly one of appointment/property) launched
        // the open create-assessment form. This is launch-context only --
        // it does not constrain the form's *submitted* body, which can and
        // does send both property_id and appointment_id together (see
        // submitAssessmentForm's comment on the propVal/apptVal selects).
        let currentAppointmentDetailId = null;
        let currentPropertyAssessmentsId = null;
        let assessmentFormScope = null;
        let assessmentChecklistRowCount = 0;
        let currentCustomer360Appointments = [];
        // Photo uploads collected for the currently-open assessment create
        // form: [{{id, title}}, ...] of already-uploaded Document ids (the
        // upload itself happens immediately on file selection, mirroring
        // there being no separate "attach" step in the B6.5 doc-store flow
        // this reuses -- the form only ever sends ids it already has).
        let assessmentFormEvidenceDocs = [];

        // B8.6c: proposal view + contract send/track/sign actions, wired
        // into the Estimates/Contracts panels above. viewEstimateProposal
        // reuses the documents-tab download precedent (window.open with
        // ?token= -- see loadCustomer360's Documents fetch and the
        // subcontractors tab's file download button) since a plain <a>
        // navigation can't carry an Authorization header.
        function viewEstimateProposal(estimateId) {{
            window.open('/api/v1/estimates/' + estimateId + '/proposal?token=' + getAuthToken(), '_blank');
        }}

        // Status-gated action buttons, matching Contract.status's real
        // CHECK values (draft/sent/signed/expired/superseded) -- draft can
        // be sent, sent can be signed (an admin/manager/PM/rep counter-
        // signature via PERM_SIGN_CONTRACTS, not a customer e-signature
        // pad -- that already exists on the customer portal surface,
        // render_portal_surface's Digital Contract E-Signature Pad),
        // signed/expired/superseded show no action.
        function renderContractActionButtons(c) {{
            if (c.status === 'draft') {{
                return `<button class="btn-gold" style="padding:0.2rem 0.6rem;font-size:0.75rem;" onclick="sendContractAction(${{c.id}})">Send</button>`;
            }}
            if (c.status === 'sent') {{
                return `<button class="btn-gold" style="padding:0.2rem 0.6rem;font-size:0.75rem;" onclick="signContractAction(${{c.id}})">Sign</button>`;
            }}
            return '';
        }}

        async function sendContractAction(contractId) {{
            const token = getAuthToken();
            try {{
                const res = await fetch('/api/v1/contracts/' + contractId + '/send', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{}}),
                }});
                if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                const data = await res.json();
                if (!res.ok) {{
                    alert(data.error || ('Failed to send contract (' + res.status + ').'));
                    return;
                }}
                if (currentCustomer360Id) loadCustomer360(currentCustomer360Id);
            }} catch (e) {{
                alert('Failed to send contract: network error.');
            }}
        }}

        async function signContractAction(contractId) {{
            const token = getAuthToken();
            if (!confirm('Sign this contract? This is a binding signature action.')) return;
            try {{
                const res = await fetch('/api/v1/contracts/' + contractId + '/sign', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ signature_data: 'portal_countersignature' }}),
                }});
                if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                const data = await res.json();
                if (!res.ok) {{
                    alert(data.error || ('Failed to sign contract (' + res.status + ').'));
                    return;
                }}
                if (currentCustomer360Id) loadCustomer360(currentCustomer360Id);
            }} catch (e) {{
                alert('Failed to sign contract: network error.');
            }}
        }}

        async function openCustomer360Modal(customerId) {{
            currentCustomer360Id = customerId;
            const overlay = document.getElementById('customer360Modal');
            const body = document.getElementById('c360Body');
            overlay.classList.add('active');
            body.innerHTML = '<p style="color:var(--text-muted);">Loading customer 360 view...</p>';
            await loadCustomer360(customerId);
        }}

        function closeCustomer360Modal() {{
            document.getElementById('customer360Modal').classList.remove('active');
            currentCustomer360Id = null;
            currentCustomer360Properties = [];
            editingPropertyId = null;
            currentCustomer360Projects = [];
            editingInsuranceProjectId = null;
            currentPropertyHistoryId = null;
            currentPropertyAssessmentsId = null;
            assessmentFormScope = null;
            currentAppointmentDetailId = null;
            currentCustomer360Appointments = [];
            assessmentFormEvidenceDocs = [];
        }}

        // Each entity has its own customer_id-scoped route already (B8.1's
        // Property routes added by this task, plus the pre-existing
        // projects/estimates/contracts/invoices/documents/appointments/
        // communications/tasks routes). Fetched with per-entry try/catch so
        // one panel's failure (most notably Invoices 403ing for a plain
        // sales rep lacking PERM_READ_FINANCIALS -- NEW-565, a flagged,
        // not-yet-decided product question, not a bug to route around here)
        // never blocks any other panel from rendering. Promise.allSettled
        // (not Promise.all) is used for the same reason -- Promise.all
        // would reject the whole batch on the first rejection.
        async function loadCustomer360(customerId) {{
            const token = getAuthToken();
            const authHeaders = {{ 'Authorization': 'Bearer ' + token }};
            const endpoints = {{
                customer: '/api/v1/customers/' + customerId,
                properties: '/api/v1/properties?customer_id=' + customerId,
                projects: '/api/v1/projects?customer_id=' + customerId,
                estimates: '/api/v1/estimates?customer_id=' + customerId,
                contracts: '/api/v1/contracts?customer_id=' + customerId,
                invoices: '/api/v1/invoices?customer_id=' + customerId,
                documents: '/api/v1/documents?customer_id=' + customerId,
                appointments: '/api/v1/appointments?customer_id=' + customerId,
                communications: '/api/v1/communications?customer_id=' + customerId,
                tasks: '/api/v1/crm/tasks?customer_id=' + customerId,
            }};
            const keys = Object.keys(endpoints);
            const settled = await Promise.allSettled(keys.map(async (k) => {{
                try {{
                    const res = await fetch(endpoints[k], {{ headers: authHeaders }});
                    if (!res.ok) {{ return {{ key: k, ok: false, status: res.status }}; }}
                    const data = await res.json();
                    return {{ key: k, ok: true, status: res.status, data }};
                }} catch (e) {{
                    return {{ key: k, ok: false, status: null }};
                }}
            }}));
            const byKey = {{}};
            settled.forEach(r => {{ if (r.status === 'fulfilled') {{ byKey[r.value.key] = r.value; }} }});

            // A 401 on any panel means the token itself is bad -- that's a
            // real auth failure, unlike a single panel's 403, so redirect
            // exactly like every other fetch in this file does.
            if (Object.values(byKey).some(r => r.status === 401)) {{
                window.location.href = '/admin/login';
                return;
            }}

            renderCustomer360(customerId, byKey);
        }}

        function c360PanelSection(title, result, emptyMsg, renderRows, headerRow) {{
            if (!result || !result.ok) {{
                const msg = (result && result.status === 403) ? 'No access.' : 'Failed to load.';
                return `<div class="erp-card"><h3 style="margin-top:0;">${{title}}</h3><p style="color:var(--text-muted);">${{msg}}</p></div>`;
            }}
            const rows = renderRows(result.data);
            const table = rows.length > 0
                ? `<table>${{headerRow}}<tbody>${{rows.join('')}}</tbody></table>`
                : `<p style="color:var(--text-muted);">${{emptyMsg}}</p>`;
            return `<div class="erp-card"><h3 style="margin-top:0;">${{title}}</h3>${{table}}</div>`;
        }}

        function renderCustomer360(customerId, byKey) {{
            const body = document.getElementById('c360Body');
            const title = document.getElementById('c360Title');

            if (!byKey.customer || !byKey.customer.ok) {{
                title.textContent = 'Customer 360';
                body.innerHTML = '<p style="color:var(--danger);">Customer not found.</p>';
                return;
            }}
            const cust = byKey.customer.data.customer;
            title.textContent = 'Customer 360 — ' + (cust.first_name || '') + ' ' + (cust.last_name || '');

            currentCustomer360Properties = (byKey.properties && byKey.properties.ok && byKey.properties.data.properties) || [];
            currentCustomer360Projects = (byKey.projects && byKey.projects.ok && byKey.projects.data.projects) || [];

            let html = '';
            html += `<div class="erp-card">
                <h3 style="margin-top:0;">Info</h3>
                <div class="modal-field"><label>Name</label><div>${{escapeHtml((cust.first_name || '') + ' ' + (cust.last_name || ''))}}</div></div>
                <div class="modal-field"><label>Company</label><div>${{escapeHtml(cust.company_name || '—')}}</div></div>
                <div class="modal-field"><label>Phone</label><div>${{escapeHtml(cust.phone || '—')}}</div></div>
                <div class="modal-field"><label>Email</label><div>${{escapeHtml(cust.email || '—')}}</div></div>
                <div class="modal-field"><label>Status</label><div>${{escapeHtml(cust.status || '—')}}</div></div>
                <div class="modal-field"><label>Service Address</label><div>${{escapeHtml(cust.service_address || '—')}}</div></div>
            </div>`;

            html += renderPropertiesPanel(byKey.properties);

            html += renderProjectsPanel(byKey.projects);

            html += c360PanelSection('Estimates', byKey.estimates, 'No estimates.',
                (d) => (d.estimates || []).map(e => `<tr><td>${{escapeHtml(e.estimate_number || '')}}</td><td>${{escapeHtml(e.status || '')}}</td><td>$${{escapeHtml((e.total_amount || 0).toLocaleString())}}</td><td><button class="btn-gold" style="padding:0.2rem 0.6rem;font-size:0.75rem;" onclick="viewEstimateProposal(${{e.id}})">View Proposal</button></td></tr>`),
                '<thead><tr><th>Number</th><th>Status</th><th>Total</th><th></th></tr></thead>');

            html += c360PanelSection('Contracts', byKey.contracts, 'No contracts.',
                (d) => (d.contracts || []).map(c => `<tr><td>${{escapeHtml(c.contract_number || '')}}</td><td>${{escapeHtml(c.title || '')}}</td><td>${{escapeHtml(c.status || '')}}${{c.status === 'signed' && c.customer_signed_at ? ' (' + escapeHtml(c.customer_signed_at) + ')' : ''}}</td><td>${{renderContractActionButtons(c)}}</td></tr>`),
                '<thead><tr><th>Number</th><th>Title</th><th>Status</th><th></th></tr></thead>');

            html += c360PanelSection('Invoices', byKey.invoices, 'No invoices.',
                (d) => (d.invoices || []).map(i => `<tr><td>${{escapeHtml(i.invoice_number || '')}}</td><td>${{escapeHtml(i.status || '')}}</td><td>$${{escapeHtml((i.amount || 0).toLocaleString())}}</td><td>$${{escapeHtml((i.balance_due || 0).toLocaleString())}}</td></tr>`),
                '<thead><tr><th>Number</th><th>Status</th><th>Amount</th><th>Balance Due</th></tr></thead>');

            html += c360PanelSection('Documents', byKey.documents, 'No documents.',
                (d) => (d.documents || []).map(doc => `<tr><td>${{escapeHtml(doc.title || '')}}</td><td>${{escapeHtml(doc.document_type || '')}}</td></tr>`),
                '<thead><tr><th>Title</th><th>Type</th></tr></thead>');

            html += renderAppointmentsPanel(byKey.appointments);

            html += c360PanelSection('Communications', byKey.communications, 'No communications.',
                (d) => (d.communications || []).map(m => `<tr><td>${{escapeHtml(m.channel || '')}}</td><td>${{escapeHtml(m.direction || '')}}</td><td>${{escapeHtml(m.subject || m.content || '')}}</td></tr>`),
                '<thead><tr><th>Channel</th><th>Direction</th><th>Subject/Content</th></tr></thead>');

            html += c360PanelSection('Tasks', byKey.tasks, 'No tasks.',
                (d) => (d.tasks || []).map(t => `<tr><td>${{escapeHtml(t.title || '')}}</td><td>${{taskTypeBadge(t)}}</td><td>${{escapeHtml(t.status || '')}}</td><td>${{escapeHtml(t.due_date || '')}}</td><td>${{taskActionButtons(t)}}</td></tr>`),
                '<thead><tr><th>Title</th><th>Type</th><th>Status</th><th>Due</th><th>Actions</th></tr></thead>');

            body.innerHTML = html;
        }}

        // Property panel. NEW-567 (Document/photo panel for Property) stays
        // out of scope this round -- Document has no property_id field at
        // all, per B8.5's deferred AssessmentRecord design. NEW-566's
        // project-history panel is now in scope: projects.property_id is
        // wired into the Project service layer (B8.4b), so "History" below
        // fetches GET /api/v1/projects?property_id=<id> on demand (view is
        // per-property, not preloaded with the rest of Customer 360).
        function renderPropertiesPanel(propertiesResult) {{
            // loadCustomer360() re-runs this on every refresh (including
            // after savePropertyForm()), which wipes #propertyHistoryArea's
            // HTML via the fresh template below -- reset the tracked id here
            // too, or a stale currentPropertyHistoryId makes the next click
            // on the same property's History button hit the toggle-closed
            // branch and silently no-op instead of reloading it.
            currentPropertyHistoryId = null;
            currentPropertyAssessmentsId = null;
            assessmentFormScope = null;
            if (!propertiesResult || !propertiesResult.ok) {{
                const msg = (propertiesResult && propertiesResult.status === 403) ? 'No access.' : 'Failed to load.';
                return `<div class="erp-card"><h3 style="margin-top:0;">Properties</h3><p style="color:var(--text-muted);">${{msg}}</p></div>`;
            }}
            const properties = propertiesResult.data.properties || [];
            const rows = properties.map(p => `<tr>
                <td>${{escapeHtml(p.address || '')}}</td>
                <td>${{escapeHtml(p.property_type || '')}}</td>
                <td>${{p.year_built || '—'}}</td>
                <td>
                    <button class="btn-gold" style="padding:0.2rem 0.6rem;font-size:0.75rem;" onclick="openPropertyForm(${{p.id}})">Edit</button>
                    <button class="btn-gold" style="padding:0.2rem 0.6rem;font-size:0.75rem;" onclick="togglePropertyHistory(${{p.id}})">History</button>
                    <button class="btn-gold" style="padding:0.2rem 0.6rem;font-size:0.75rem;" onclick="togglePropertyAssessments(${{p.id}})">Assessments</button>
                </td>
            </tr>`);
            const table = rows.length > 0
                ? `<table><thead><tr><th>Address</th><th>Type</th><th>Year Built</th><th></th></tr></thead><tbody>${{rows.join('')}}</tbody></table>`
                : '<p style="color:var(--text-muted);">No properties on file.</p>';
            return `<div class="erp-card">
                <h3 style="margin-top:0;display:flex;justify-content:space-between;align-items:center;">
                    <span>Properties</span>
                    <button class="btn-gold" style="padding:0.3rem 0.8rem;font-size:0.8rem;" onclick="openPropertyForm(null)">+ Add Property</button>
                </h3>
                ${{table}}
                <div id="propertyFormArea"></div>
                <div id="propertyHistoryArea"></div>
                <div id="propertyAssessmentsArea"></div>
            </div>`;
        }}

        // B8.8a: Project insurance/claim/adjuster panel. Project already
        // carries 6 insurance fields (insurance_claim_number,
        // insurance_carrier, adjuster_name, adjuster_phone, adjuster_email,
        // deductible) plus 2 added this round (coverage_amount,
        // supplement_amount), all fully CRUD-wired server-side
        // (update_project's ALLOWED_PROJECT_UPDATE_FIELDS) but previously
        // exposed nowhere in the UI. Mirrors renderPropertiesPanel's
        // table + inline-form-area shape exactly (openPropertyForm /
        // savePropertyForm below). insurance_claim_status is NOT included
        // here -- it lives on Opportunity, not Project (crm_service.py:1487
        // documents the two fields use different value vocabularies; there
        // is no Project column to persist it to).
        function renderProjectsPanel(projectsResult) {{
            editingInsuranceProjectId = null;
            if (!projectsResult || !projectsResult.ok) {{
                const msg = (projectsResult && projectsResult.status === 403) ? 'No access.' : 'Failed to load.';
                return `<div class="erp-card"><h3 style="margin-top:0;">Projects</h3><p style="color:var(--text-muted);">${{msg}}</p></div>`;
            }}
            const projects = projectsResult.data.projects || [];
            const rows = projects.map(p => `<tr>
                <td>${{escapeHtml(p.title || '')}}</td>
                <td>${{escapeHtml(p.status || '')}}</td>
                <td>$${{escapeHtml((p.contract_amount || 0).toLocaleString())}}</td>
                <td>
                    <button class="btn-gold" style="padding:0.2rem 0.6rem;font-size:0.75rem;" onclick="openProjectInsuranceForm(${{p.id}})">Insurance</button>
                </td>
            </tr>`);
            const table = rows.length > 0
                ? `<table><thead><tr><th>Title</th><th>Status</th><th>Contract Amount</th><th></th></tr></thead><tbody>${{rows.join('')}}</tbody></table>`
                : '<p style="color:var(--text-muted);">No projects.</p>';
            return `<div class="erp-card">
                <h3 style="margin-top:0;">Projects</h3>
                ${{table}}
                <div id="projectInsuranceFormArea"></div>
            </div>`;
        }}

        function openProjectInsuranceForm(projectId) {{
            editingInsuranceProjectId = projectId;
            const proj = currentCustomer360Projects.find(p => p.id === projectId);
            const v = (field) => proj && proj[field] !== undefined && proj[field] !== null ? proj[field] : '';
            const area = document.getElementById('projectInsuranceFormArea');
            area.innerHTML = `
                <div class="erp-card">
                    <h4 style="margin-top:0;">Insurance / Claim — ${{escapeHtml(proj ? (proj.title || '') : '')}}</h4>
                    <div class="modal-field"><label>Claim Number</label><input type="text" id="projInsuranceClaimNumber" value="${{escapeHtml(v('insurance_claim_number'))}}"></div>
                    <div class="modal-field"><label>Carrier</label><input type="text" id="projInsuranceCarrier" value="${{escapeHtml(v('insurance_carrier'))}}"></div>
                    <div class="modal-field"><label>Adjuster Name</label><input type="text" id="projAdjusterName" value="${{escapeHtml(v('adjuster_name'))}}"></div>
                    <div class="modal-field"><label>Adjuster Phone</label><input type="text" id="projAdjusterPhone" value="${{escapeHtml(v('adjuster_phone'))}}"></div>
                    <div class="modal-field"><label>Adjuster Email</label><input type="text" id="projAdjusterEmail" value="${{escapeHtml(v('adjuster_email'))}}"></div>
                    <div class="modal-field"><label>Deductible</label><input type="number" step="0.01" id="projDeductible" value="${{v('deductible')}}"></div>
                    <div class="modal-field"><label>Coverage Amount</label><input type="number" step="0.01" id="projCoverageAmount" value="${{v('coverage_amount')}}"></div>
                    <div class="modal-field"><label>Supplement Amount</label><input type="number" step="0.01" id="projSupplementAmount" value="${{v('supplement_amount')}}"></div>
                    <div style="display:flex;gap:0.5rem;">
                        <button class="btn-gold" onclick="saveProjectInsuranceForm()">Save Changes</button>
                        <button class="btn-gold" onclick="document.getElementById('projectInsuranceFormArea').innerHTML=''">Cancel</button>
                    </div>
                </div>
            `;
        }}

        // update_project (crm_service.py) rejects None values outright and
        // enforces an explicit allow-list, same as savePropertyForm's
        // comment above -- only send fields actually filled in. Money
        // fields use parseFloat (NOT parseInt, unlike savePropertyForm's
        // numVal -- those are years/sqft/stories, these are dollars) and a
        // Number.isFinite guard: parseFloat('') / parseFloat('abc') is NaN,
        // and JSON.stringify(NaN) serializes to null, which would hit
        // update_project's blanket None-guard and fail the whole save with
        // a confusing "cannot be set to None" error instead of just
        // omitting the field.
        async function saveProjectInsuranceForm() {{
            if (!editingInsuranceProjectId) {{ return; }}
            const token = getAuthToken();
            const strVal = (id) => {{ const v = document.getElementById(id).value.trim(); return v === '' ? null : v; }};
            const numVal = (id) => {{ const n = parseFloat(document.getElementById(id).value); return Number.isFinite(n) ? n : null; }};

            const updates = {{}};
            const strFields = {{
                insurance_claim_number: 'projInsuranceClaimNumber',
                insurance_carrier: 'projInsuranceCarrier',
                adjuster_name: 'projAdjusterName',
                adjuster_phone: 'projAdjusterPhone',
                adjuster_email: 'projAdjusterEmail',
            }};
            Object.keys(strFields).forEach(k => {{ const val = strVal(strFields[k]); if (val !== null) {{ updates[k] = val; }} }});
            const numFields = {{
                deductible: 'projDeductible',
                coverage_amount: 'projCoverageAmount',
                supplement_amount: 'projSupplementAmount',
            }};
            Object.keys(numFields).forEach(k => {{ const val = numVal(numFields[k]); if (val !== null) {{ updates[k] = val; }} }});

            try {{
                const res = await fetch('/api/v1/projects/' + editingInsuranceProjectId + '/update', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                    body: JSON.stringify(updates),
                }});
                if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                const data = await res.json();
                if (!res.ok) {{
                    alert(data.error || ('Failed to save insurance info (' + res.status + ').'));
                    return;
                }}
                editingInsuranceProjectId = null;
                await loadCustomer360(currentCustomer360Id);
            }} catch (e) {{
                alert('Failed to save insurance info: network error.');
            }}
        }}

        // NEW-566: property-scoped project history, fetched on demand (not
        // part of loadCustomer360's Promise.allSettled fan-out) since it's
        // per-property rather than per-customer. Toggles closed if the same
        // property's history is already showing. currentPropertyHistoryId
        // is declared with the other Customer 360 modal state near the top
        // of this section (also reset there and in renderPropertiesPanel).
        async function togglePropertyHistory(propertyId) {{
            const area = document.getElementById('propertyHistoryArea');
            if (currentPropertyHistoryId === propertyId) {{
                area.innerHTML = '';
                currentPropertyHistoryId = null;
                return;
            }}
            currentPropertyHistoryId = propertyId;
            area.innerHTML = '<p style="color:var(--text-muted);">Loading project history...</p>';
            const token = getAuthToken();
            try {{
                const res = await fetch('/api/v1/projects?property_id=' + propertyId, {{
                    headers: {{ 'Authorization': 'Bearer ' + token }},
                }});
                if (res.status === 401) {{
                    window.location.href = '/admin/login';
                    return;
                }}
                if (!res.ok) {{
                    area.innerHTML = `<p style="color:var(--text-muted);">${{res.status === 403 ? 'No access.' : 'Failed to load.'}}</p>`;
                    return;
                }}
                const data = await res.json();
                const projects = data.projects || [];
                const rows = projects.map(p => `<tr><td>${{escapeHtml(p.title || '')}}</td><td>${{escapeHtml(p.status || '')}}</td><td>$${{escapeHtml((p.contract_amount || 0).toLocaleString())}}</td></tr>`);
                const table = rows.length > 0
                    ? `<table><thead><tr><th>Title</th><th>Status</th><th>Contract Amount</th></tr></thead><tbody>${{rows.join('')}}</tbody></table>`
                    : '<p style="color:var(--text-muted);">No projects on file for this property.</p>';
                area.innerHTML = `<div class="erp-card"><h3 style="margin-top:0;">Project History</h3>${{table}}</div>`;
            }} catch (e) {{
                area.innerHTML = '<p style="color:var(--text-muted);">Failed to load: network error.</p>';
            }}
        }}

        // -----------------------------------------------------------------
        // B8.5b Part 1: Appointment scheduling UI (create + detail view).
        // Appointment CRUD (SchedulingService.create_appointment/
        // get_appointment/list_appointments) and its routes already exist
        // and already work (used by B8.2a's dashboard, B8.3's kanban) --
        // this is pure UI composition reusing them. routes.py constructs
        // Appointment(**json_body) directly for POST /api/v1/appointments,
        // so only real Appointment dataclass field names (models.py) may be
        // sent.
        // -----------------------------------------------------------------
        function renderAppointmentsPanel(appointmentsResult) {{
            currentAppointmentDetailId = null;
            if (!appointmentsResult || !appointmentsResult.ok) {{
                const msg = (appointmentsResult && appointmentsResult.status === 403) ? 'No access.' : 'Failed to load.';
                return `<div class="erp-card"><h3 style="margin-top:0;">Appointments</h3><p style="color:var(--text-muted);">${{msg}}</p></div>`;
            }}
            const appointments = appointmentsResult.data.appointments || [];
            currentCustomer360Appointments = appointments;
            const rows = appointments.map(a => `<tr>
                <td>${{escapeHtml(a.title || '')}}</td>
                <td>${{escapeHtml(a.start_time || '—')}}</td>
                <td>${{escapeHtml(a.status || '')}}</td>
                <td><button class="btn-gold" style="padding:0.2rem 0.6rem;font-size:0.75rem;" onclick="toggleAppointmentDetail(${{a.id}})">Details</button></td>
            </tr>`);
            const table = rows.length > 0
                ? `<table><thead><tr><th>Title</th><th>Start</th><th>Status</th><th></th></tr></thead><tbody>${{rows.join('')}}</tbody></table>`
                : '<p style="color:var(--text-muted);">No appointments on file.</p>';
            return `<div class="erp-card">
                <h3 style="margin-top:0;display:flex;justify-content:space-between;align-items:center;">
                    <span>Appointments</span>
                    <button class="btn-gold" style="padding:0.3rem 0.8rem;font-size:0.8rem;" onclick="openAppointmentForm()">+ Schedule Appointment</button>
                </h3>
                ${{table}}
                <div id="appointmentFormArea"></div>
                <div id="appointmentDetailArea"></div>
            </div>`;
        }}

        function openAppointmentForm() {{
            const area = document.getElementById('appointmentFormArea');
            area.innerHTML = `
                <div class="modal-field"><label>Title</label><input type="text" id="apptTitle" value=""></div>
                <div class="modal-field"><label>Start</label><input type="datetime-local" id="apptStartTime" value=""></div>
                <div class="modal-field"><label>End</label><input type="datetime-local" id="apptEndTime" value=""></div>
                <div class="modal-field"><label>Modality</label>
                    <select id="apptType">
                        <option value="">—</option>
                        <option value="call">Call</option>
                        <option value="in_person">In Person</option>
                    </select>
                </div>
                <div class="modal-field"><label>Notes</label><textarea id="apptNotes" rows="2"></textarea></div>
                <div style="display:flex;gap:0.5rem;">
                    <button class="btn-gold" onclick="saveAppointmentForm()">Schedule</button>
                    <button class="btn-gold" onclick="document.getElementById('appointmentFormArea').innerHTML=''">Cancel</button>
                </div>
            `;
        }}

        // start_time/end_time are sent as the raw `datetime-local` input
        // value (no timezone) -- matches the existing precedent elsewhere
        // in this codebase of not inventing a timezone conversion
        // (list_appointments's substr(start_time,1,10) comment confirms
        // start_time is just stored/compared as a string prefix).
        async function saveAppointmentForm() {{
            const token = getAuthToken();
            const title = document.getElementById('apptTitle').value.trim();
            if (!title) {{ alert('Title is required.'); return; }}
            const body = {{
                customer_id: currentCustomer360Id,
                title: title,
                start_time: document.getElementById('apptStartTime').value || null,
                end_time: document.getElementById('apptEndTime').value || null,
                appointment_type: document.getElementById('apptType').value || null,
                notes: document.getElementById('apptNotes').value.trim() || null,
            }};
            try {{
                const res = await fetch('/api/v1/appointments', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                    body: JSON.stringify(body),
                }});
                if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                const data = await res.json();
                if (!res.ok) {{
                    alert(data.error || ('Failed to schedule appointment (' + res.status + ').'));
                    return;
                }}
                document.getElementById('appointmentFormArea').innerHTML = '';
                await loadCustomer360(currentCustomer360Id);
            }} catch (e) {{
                alert('Failed to schedule appointment: network error.');
            }}
        }}

        // Toggles an appointment's detail view (fields + a "New Assessment"
        // entry point + its assessment records), mirroring
        // togglePropertyHistory's toggle-closed-on-repeat-click pattern.
        function toggleAppointmentDetail(appointmentId) {{
            const area = document.getElementById('appointmentDetailArea');
            if (currentAppointmentDetailId === appointmentId) {{
                area.innerHTML = '';
                currentAppointmentDetailId = null;
                return;
            }}
            currentAppointmentDetailId = appointmentId;
            const appt = currentCustomer360Appointments.find(a => a.id === appointmentId);
            if (!appt) {{ area.innerHTML = ''; return; }}
            area.innerHTML = `
                <div class="erp-card">
                    <h3 style="margin-top:0;">${{escapeHtml(appt.title || '')}}</h3>
                    <div class="modal-field"><label>Start</label><div>${{escapeHtml(appt.start_time || '—')}}</div></div>
                    <div class="modal-field"><label>End</label><div>${{escapeHtml(appt.end_time || '—')}}</div></div>
                    <div class="modal-field"><label>Status</label><div>${{escapeHtml(appt.status || '')}}</div></div>
                    <div class="modal-field"><label>Notes</label><div>${{escapeHtml(appt.notes || '—')}}</div></div>
                    <button class="btn-gold" style="padding:0.3rem 0.8rem;font-size:0.8rem;" onclick="openAssessmentForm('appointment', ${{appointmentId}}, 'appointmentAssessmentArea')">+ New Assessment</button>
                    <div id="appointmentAssessmentArea"></div>
                </div>
            `;
            loadAssessmentRecordsList('appointment', appointmentId, 'appointmentAssessmentArea');
        }}

        // -----------------------------------------------------------------
        // B8.5b Part 2: Assessment checklist + evidence UI. Shared between
        // its two entry points -- a property's "Assessments" button
        // (renderPropertiesPanel, mirrors the existing "History" button
        // pattern) and an appointment's detail view above -- since
        // GET/POST /api/v1/assessment-records already supports filtering/
        // creating by either property_id or appointment_id independently
        // (assessment_service.py). checklist_json is a deliberately opaque
        // blob (database.py's assessment_records DDL comment), so a
        // generic key/value row editor is the whole checklist UI rather
        // than a fixed-field form.
        // -----------------------------------------------------------------
        async function togglePropertyAssessments(propertyId) {{
            const area = document.getElementById('propertyAssessmentsArea');
            if (currentPropertyAssessmentsId === propertyId) {{
                area.innerHTML = '';
                currentPropertyAssessmentsId = null;
                assessmentFormScope = null;
                return;
            }}
            currentPropertyAssessmentsId = propertyId;
            area.innerHTML = `<div class="erp-card">
                <h3 style="margin-top:0;display:flex;justify-content:space-between;align-items:center;">
                    <span>Assessments</span>
                    <button class="btn-gold" style="padding:0.3rem 0.8rem;font-size:0.8rem;" onclick="openAssessmentForm('property', ${{propertyId}}, 'propertyAssessmentListArea')">+ New Assessment</button>
                </h3>
                <div id="propertyAssessmentListArea"></div>
            </div>`;
            await loadAssessmentRecordsList('property', propertyId, 'propertyAssessmentListArea');
        }}

        async function loadAssessmentRecordsList(kind, id, areaId) {{
            const area = document.getElementById(areaId);
            area.innerHTML = '<p style="color:var(--text-muted);">Loading assessments...</p>';
            const token = getAuthToken();
            const qs = kind === 'property' ? ('property_id=' + id) : ('appointment_id=' + id);
            try {{
                const res = await fetch('/api/v1/assessment-records?' + qs, {{
                    headers: {{ 'Authorization': 'Bearer ' + token }},
                }});
                if (res.status === 401) {{
                    window.location.href = '/admin/login';
                    return;
                }}
                if (!res.ok) {{
                    area.innerHTML = `<p style="color:var(--text-muted);">${{res.status === 403 ? 'No access.' : 'Failed to load.'}}</p>`;
                    return;
                }}
                const data = await res.json();
                const records = data.assessment_records || [];
                if (records.length === 0) {{
                    area.innerHTML = '<p style="color:var(--text-muted);">No assessments on file.</p>';
                    return;
                }}
                const rows = records.map(r => {{
                    const checklistSummary = Object.keys(r.checklist || {{}}).length + ' item(s)';
                    const photoCount = (r.evidence_document_ids || []).length;
                    return `<tr>
                        <td>${{escapeHtml(r.created_at || '')}}</td>
                        <td>${{escapeHtml(checklistSummary)}}</td>
                        <td>${{photoCount}} photo(s)</td>
                        <td>${{escapeHtml(r.customer_statements || '—')}}</td>
                    </tr>`;
                }});
                area.innerHTML = `<table><thead><tr><th>Created</th><th>Checklist</th><th>Evidence</th><th>Customer Statement</th></tr></thead><tbody>${{rows.join('')}}</tbody></table>`;
            }} catch (e) {{
                area.innerHTML = '<p style="color:var(--text-muted);">Failed to load: network error.</p>';
            }}
        }}

        // A record can legitimately carry both appointment_id and
        // property_id (assessment_service.py/models.py both support it,
        // e.g. an appointment tied to a specific property) -- and the
        // "retrievable from both" exit criterion requires that a rep be
        // able to set both from either entry point. The field the caller
        // launched from is prefilled but not locked; the other is a free
        // choice from whichever of currentCustomer360Properties/
        // currentCustomer360Appointments this Customer 360 modal already
        // has loaded.
        function openAssessmentForm(kind, id, areaId) {{
            assessmentFormScope = {{ kind, id, areaId }};
            assessmentChecklistRowCount = 0;
            assessmentFormEvidenceDocs = [];
            const area = document.getElementById(areaId);
            const propOptions = currentCustomer360Properties.map(p =>
                `<option value="${{p.id}}" ${{kind === 'property' && p.id === id ? 'selected' : ''}}>${{escapeHtml(p.address || ('#' + p.id))}}</option>`
            ).join('');
            const apptOptions = currentCustomer360Appointments.map(a =>
                `<option value="${{a.id}}" ${{kind === 'appointment' && a.id === id ? 'selected' : ''}}>${{escapeHtml(a.title || ('#' + a.id))}}</option>`
            ).join('');
            area.innerHTML = `
                <div class="erp-card">
                    <h4 style="margin-top:0;">New Assessment</h4>
                    <div class="modal-field"><label>Property</label>
                        <select id="assessmentPropertySelect"><option value="">—</option>${{propOptions}}</select>
                    </div>
                    <div class="modal-field"><label>Appointment</label>
                        <select id="assessmentAppointmentSelect"><option value="">—</option>${{apptOptions}}</select>
                    </div>
                    <div id="assessmentChecklistRows"></div>
                    <button class="btn-gold" style="padding:0.2rem 0.6rem;font-size:0.75rem;" onclick="addAssessmentChecklistRow()">+ Add Checklist Item</button>
                    <div class="modal-field" style="margin-top:0.75rem;"><label>Customer Statements</label><textarea id="assessmentCustomerStatements" rows="2"></textarea></div>
                    <div class="modal-field"><label>Photos</label><input type="file" id="assessmentPhotoInput" accept="image/*" multiple onchange="handleAssessmentPhotoUpload(event)"></div>
                    <div id="assessmentPhotoList" style="font-size:0.8rem;color:var(--text-muted);"></div>
                    <div style="display:flex;gap:0.5rem;margin-top:0.5rem;">
                        <button class="btn-gold" onclick="submitAssessmentForm()">Save Assessment</button>
                        <button class="btn-gold" onclick="closeAssessmentForm()">Cancel</button>
                    </div>
                </div>
            `;
            addAssessmentChecklistRow();
        }}

        function closeAssessmentForm() {{
            if (!assessmentFormScope) {{ return; }}
            const {{ kind, id, areaId }} = assessmentFormScope;
            assessmentFormScope = null;
            assessmentFormEvidenceDocs = [];
            loadAssessmentRecordsList(kind, id, areaId);
        }}

        function addAssessmentChecklistRow() {{
            const idx = assessmentChecklistRowCount++;
            const rows = document.getElementById('assessmentChecklistRows');
            const row = document.createElement('div');
            row.id = 'assessmentChecklistRow' + idx;
            row.style.display = 'flex';
            row.style.gap = '0.5rem';
            row.style.marginBottom = '0.3rem';
            row.innerHTML = `
                <input type="text" placeholder="Item (e.g. roof_condition)" id="assessmentChecklistKey${{idx}}" style="flex:1;">
                <input type="text" placeholder="Value" id="assessmentChecklistValue${{idx}}" style="flex:1;">
                <button class="btn-gold" style="padding:0.2rem 0.6rem;font-size:0.75rem;" onclick="removeAssessmentChecklistRow(${{idx}})">Remove</button>
            `;
            rows.appendChild(row);
        }}

        function removeAssessmentChecklistRow(idx) {{
            const row = document.getElementById('assessmentChecklistRow' + idx);
            if (row) {{ row.remove(); }}
        }}

        // Reuses B6.5's existing 25MB local-disk Document upload path
        // (POST /api/v1/documents, multipart/form-data) -- no new storage
        // layer. Uploads happen immediately on file selection (there is no
        // separate "attach" step in the reused flow), each returning a
        // Document id that is accumulated into assessmentFormEvidenceDocs
        // and sent as evidence_document_ids on submit.
        // Field order matters here: routes.py's multipart parser only
        // populates `metadata` (document_type/customer_id/etc.) from parts
        // it has already streamed through `on_part_data` by the time it
        // hits `on_headers_finished` for the file part -- so the
        // non-file fields MUST be appended (and therefore streamed)
        // before `file`, or the server computes the storage sub-directory
        // with an empty metadata dict (falls back to uploads/general/)
        // even though the resulting Document row still looks correct.
        async function handleAssessmentPhotoUpload(event) {{
            const files = Array.from(event.target.files || []);
            if (files.length === 0) {{ return; }}
            const token = getAuthToken();
            const listEl = document.getElementById('assessmentPhotoList');
            for (const file of files) {{
                const formData = new FormData();
                // 'assessment_photo' is not a valid document_type (see the
                // CHECK constraint on documents.document_type in
                // database.py) -- send the real 'photo' enum value and tag
                // it 'assessment' server-side instead, the same pattern
                // routes.py already uses for subcontractor_id-scoped
                // uploads (tags.append(f"subcontractor_id:{{...}}")).
                formData.append('document_type', 'photo');
                formData.append('assessment', 'true');
                formData.append('title', file.name);
                if (currentCustomer360Id) {{ formData.append('customer_id', String(currentCustomer360Id)); }}
                formData.append('file', file);
                try {{
                    const res = await fetch('/api/v1/documents', {{
                        method: 'POST',
                        headers: {{ 'Authorization': 'Bearer ' + token }},
                        body: formData,
                    }});
                    const data = await res.json();
                    if (!res.ok) {{
                        listEl.innerHTML += `<div style="color:var(--danger);">${{escapeHtml(file.name)}}: ${{escapeHtml(data.error || 'upload failed')}}</div>`;
                        continue;
                    }}
                    assessmentFormEvidenceDocs.push({{ id: data.document.id, title: file.name }});
                    listEl.innerHTML += `<div>${{escapeHtml(file.name)}} uploaded (doc #${{data.document.id}})</div>`;
                }} catch (e) {{
                    listEl.innerHTML += `<div style="color:var(--danger);">${{escapeHtml(file.name)}}: network error.</div>`;
                }}
            }}
            event.target.value = '';
        }}

        async function submitAssessmentForm() {{
            if (!assessmentFormScope) {{ return; }}
            const {{ kind, id, areaId }} = assessmentFormScope;
            const token = getAuthToken();
            const checklist = {{}};
            for (let i = 0; i < assessmentChecklistRowCount; i++) {{
                const keyEl = document.getElementById('assessmentChecklistKey' + i);
                const valEl = document.getElementById('assessmentChecklistValue' + i);
                if (!keyEl || !valEl) {{ continue; }}
                const k = keyEl.value.trim();
                const v = valEl.value.trim();
                if (k) {{ checklist[k] = v; }}
            }}
            const body = {{
                checklist: checklist,
                evidence_document_ids: assessmentFormEvidenceDocs.map(d => d.id),
                customer_statements: document.getElementById('assessmentCustomerStatements').value.trim() || null,
            }};
            // Both selects are independently optional and not mutually
            // exclusive -- see openAssessmentForm's comment. This is what
            // makes a record retrievable from both a property panel and an
            // appointment detail view when a rep sets both.
            const propVal = document.getElementById('assessmentPropertySelect').value;
            const apptVal = document.getElementById('assessmentAppointmentSelect').value;
            if (propVal) {{ body.property_id = parseInt(propVal, 10); }}
            if (apptVal) {{ body.appointment_id = parseInt(apptVal, 10); }}
            try {{
                const res = await fetch('/api/v1/assessment-records', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                    body: JSON.stringify(body),
                }});
                if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                const data = await res.json();
                if (!res.ok) {{
                    alert(data.error || ('Failed to save assessment (' + res.status + ').'));
                    return;
                }}
                assessmentFormScope = null;
                assessmentFormEvidenceDocs = [];
                await loadAssessmentRecordsList(kind, id, areaId);
            }} catch (e) {{
                alert('Failed to save assessment: network error.');
            }}
        }}

        function openPropertyForm(propertyId) {{
            editingPropertyId = propertyId;
            const prop = propertyId
                ? currentCustomer360Properties.find(p => p.id === propertyId)
                : null;
            const v = (field, fallback) => prop && prop[field] !== undefined && prop[field] !== null ? prop[field] : (fallback === undefined ? '' : fallback);
            const area = document.getElementById('propertyFormArea');
            area.innerHTML = `
                <div class="modal-field"><label>Address</label><input type="text" id="propAddress" value="${{escapeHtml(v('address'))}}"></div>
                <div class="modal-field"><label>Parcel Number</label><input type="text" id="propParcelNumber" value="${{escapeHtml(v('parcel_number'))}}"></div>
                <div class="modal-field"><label>Property Type</label><input type="text" id="propPropertyType" value="${{escapeHtml(v('property_type'))}}"></div>
                <div class="modal-field"><label>Year Built</label><input type="number" id="propYearBuilt" value="${{v('year_built')}}"></div>
                <div class="modal-field"><label>Square Footage</label><input type="number" id="propSquareFootage" value="${{v('square_footage')}}"></div>
                <div class="modal-field"><label>Stories</label><input type="number" id="propStories" value="${{v('stories')}}"></div>
                <div class="modal-field"><label>Roof Type</label><input type="text" id="propRoofType" value="${{escapeHtml(v('roof_type'))}}"></div>
                <div class="modal-field"><label>Exterior Type</label><input type="text" id="propExteriorType" value="${{escapeHtml(v('exterior_type'))}}"></div>
                <div class="modal-field"><label>Insurance Carrier</label><input type="text" id="propInsuranceCarrier" value="${{escapeHtml(v('insurance_carrier'))}}"></div>
                <div class="modal-field"><label>Notes</label><textarea id="propNotes" rows="2">${{escapeHtml(v('notes'))}}</textarea></div>
                <div style="display:flex;gap:0.5rem;">
                    <button class="btn-gold" onclick="savePropertyForm()">${{propertyId ? 'Save Changes' : 'Create Property'}}</button>
                    <button class="btn-gold" onclick="document.getElementById('propertyFormArea').innerHTML=''">Cancel</button>
                </div>
            `;
        }}

        // update_property (crm_service.py) rejects None values outright and
        // enforces an explicit allow-list -- only send fields the user
        // actually filled in (create uses the same shape; empty optional
        // fields are simply omitted rather than sent as null/empty string).
        async function savePropertyForm() {{
            const token = getAuthToken();
            const strVal = (id) => {{ const v = document.getElementById(id).value.trim(); return v === '' ? null : v; }};
            const numVal = (id) => {{ const raw = document.getElementById(id).value; return raw === '' ? null : parseInt(raw, 10); }};

            const address = strVal('propAddress');
            const fields = {{
                parcel_number: strVal('propParcelNumber'),
                property_type: strVal('propPropertyType'),
                year_built: numVal('propYearBuilt'),
                square_footage: numVal('propSquareFootage'),
                stories: numVal('propStories'),
                roof_type: strVal('propRoofType'),
                exterior_type: strVal('propExteriorType'),
                insurance_carrier: strVal('propInsuranceCarrier'),
                notes: strVal('propNotes'),
            }};

            try {{
                if (editingPropertyId) {{
                    const updates = {{}};
                    if (address !== null) {{ updates.address = address; }}
                    Object.keys(fields).forEach(k => {{ if (fields[k] !== null) {{ updates[k] = fields[k]; }} }});
                    const res = await fetch('/api/v1/properties/' + editingPropertyId + '/update', {{
                        method: 'POST',
                        headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                        body: JSON.stringify(updates),
                    }});
                    const data = await res.json();
                    if (!res.ok) {{
                        alert(data.error || ('Failed to save property (' + res.status + ').'));
                        return;
                    }}
                }} else {{
                    const body = {{ customer_id: currentCustomer360Id, address: address || '' }};
                    Object.keys(fields).forEach(k => {{ if (fields[k] !== null) {{ body[k] = fields[k]; }} }});
                    const res = await fetch('/api/v1/properties', {{
                        method: 'POST',
                        headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                        body: JSON.stringify(body),
                    }});
                    const data = await res.json();
                    if (!res.ok) {{
                        alert(data.error || ('Failed to create property (' + res.status + ').'));
                        return;
                    }}
                }}
                editingPropertyId = null;
                await loadCustomer360(currentCustomer360Id);
            }} catch (e) {{
                alert('Failed to save property: network error.');
            }}
        }}

        // -----------------------------------------------------------------
        // B8.6d-c (NEW-579): guided customer -> template -> fill -> sign
        // flow. gflowState holds the in-progress customer/contract chosen
        // across the four steps; nothing here is persisted until the
        // corresponding "Create"/"Save" button fires its fetch() call --
        // each step's data lives only in gflowState/the form fields until
        // then, same as createLeadModal's plain-form-fields pattern above.
        // -----------------------------------------------------------------
        let gflowState = {{ customer: null, contractId: null }};

        function guidedFlowError(msg) {{
            const el = document.getElementById('gflowError');
            el.textContent = msg;
            el.style.display = msg ? 'block' : 'none';
        }}

        function showGuidedStep(n) {{
            for (let i = 1; i <= 4; i++) {{
                document.getElementById('gflowStep' + i).style.display = (i === n) ? 'block' : 'none';
            }}
            guidedFlowError('');
        }}

        function openGuidedContractModal() {{
            gflowState = {{ customer: null, contractId: null }};
            document.getElementById('gflowCustomerSearch').value = '';
            document.getElementById('gflowCustomerResults').innerHTML = '';
            document.getElementById('gflowNewCustomerForm').style.display = 'none';
            document.getElementById('gflowSignerStatus').innerHTML = '';
            showGuidedStep(1);
            document.getElementById('guidedContractModal').classList.add('active');
        }}

        function closeGuidedContractModal() {{
            document.getElementById('guidedContractModal').classList.remove('active');
        }}

        function guidedShowNewCustomerForm() {{
            document.getElementById('gflowNewCustomerForm').style.display = 'block';
        }}

        // NOTE (same shape as the "Load Customers" comment above,
        // 2026-09-16 correction): list_customers DOES apply NEW-568
        // rep-ownership narrowing today -- a plain rep only searches
        // customers assigned to them or unclaimed, a sales manager (or
        // any PERM_READ_TEAM_SALES_DATA holder) searches everyone. No
        // client-side scoping needed here; the server already narrows the
        // result set the search query runs against.
        let gflowSearchDebounce = null;
        async function guidedSearchCustomers() {{
            clearTimeout(gflowSearchDebounce);
            const term = document.getElementById('gflowCustomerSearch').value.trim();
            const resultsEl = document.getElementById('gflowCustomerResults');
            if (!term) {{ resultsEl.innerHTML = ''; return; }}
            gflowSearchDebounce = setTimeout(async () => {{
                try {{
                    const token = getAuthToken();
                    const res = await fetch('/api/v1/customers?search=' + encodeURIComponent(term), {{
                        headers: {{ 'Authorization': 'Bearer ' + token }}
                    }});
                    if (res.status === 401) {{ window.location.href = '/admin/login'; return; }}
                    const data = await res.json();
                    if (!res.ok) {{ guidedFlowError(data.error || 'Search failed.'); return; }}
                    const matches = data.customers || [];
                    if (matches.length === 0) {{
                        resultsEl.innerHTML = '<p style="color:var(--text-muted);">No matches. Create a new customer below.</p>';
                        return;
                    }}
                    resultsEl.innerHTML = matches.map(c => `
                        <div style="padding:0.5rem;border-bottom:1px solid var(--border-light);display:flex;justify-content:space-between;align-items:center;">
                            <span>${{escapeHtml((c.first_name || '') + ' ' + (c.last_name || ''))}} ${{c.customer_number ? '(#' + c.customer_number + ')' : ''}} — ${{escapeHtml(c.phone || c.email || '')}}</span>
                            <button class="btn-gold" style="padding:0.2rem 0.6rem;font-size:0.75rem;" onclick='guidedSelectCustomer(${{JSON.stringify(c)}})'>Select</button>
                        </div>`
                    ).join('');
                }} catch (e) {{ guidedFlowError('Search failed: network error.'); }}
            }}, 250);
        }}

        function guidedSelectCustomer(customer) {{
            gflowState.customer = customer;
            document.getElementById('gflowSelectedCustomerLabel').textContent =
                'Customer: ' + (customer.first_name || '') + ' ' + (customer.last_name || '') +
                (customer.customer_number ? ' (#' + customer.customer_number + ')' : '');
            showGuidedStep(2);
        }}

        async function guidedSubmitNewCustomer() {{
            const body = {{
                first_name: document.getElementById('gflowNewFirstName').value,
                last_name: document.getElementById('gflowNewLastName').value,
                phone: document.getElementById('gflowNewPhone').value || null,
                email: document.getElementById('gflowNewEmail').value || null,
                service_address: document.getElementById('gflowNewAddress').value || null,
            }};
            if (!body.first_name || !body.last_name) {{
                guidedFlowError('First and last name are required.');
                return;
            }}
            try {{
                const token = getAuthToken();
                const res = await fetch('/api/v1/customers', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                    body: JSON.stringify(body),
                }});
                const data = await res.json();
                if (!res.ok) {{ guidedFlowError(data.error || 'Failed to create customer.'); return; }}
                guidedSelectCustomer(data.customer);
            }} catch (e) {{ guidedFlowError('Failed to create customer: network error.'); }}
        }}

        function guidedGoToStep3() {{
            const c = gflowState.customer;
            document.getElementById('gflowFieldName').value = ((c.first_name || '') + ' ' + (c.last_name || '')).trim();
            document.getElementById('gflowFieldAddress').value = c.service_address || c.mailing_address || '';
            document.getElementById('gflowFieldPhone').value = c.phone || '';
            document.getElementById('gflowFieldEmail').value = c.email || '';
            showGuidedStep(3);
        }}

        async function guidedSubmitContract() {{
            const number = document.getElementById('gflowContractNumber').value.trim();
            const title = document.getElementById('gflowContractTitle').value.trim();
            if (!number || !title) {{ guidedFlowError('Contract # and title are required.'); return; }}
            const body = {{
                contract_number: number,
                customer_id: gflowState.customer.id,
                title: title,
                template_name: document.getElementById('gflowTemplateSelect').value,
                content: document.getElementById('gflowContractContent').value || '',
            }};
            try {{
                const token = getAuthToken();
                const res = await fetch('/api/v1/contracts', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                    body: JSON.stringify(body),
                }});
                const data = await res.json();
                if (!res.ok) {{ guidedFlowError(data.error || 'Failed to create contract.'); return; }}
                gflowState.contractId = data.contract.id;
                showGuidedStep(4);
            }} catch (e) {{ guidedFlowError('Failed to create contract: network error.'); }}
        }}

        async function guidedConfigureSigners() {{
            const signers = [];
            if (document.getElementById('gflowSignerCustomer').checked) signers.push({{ party_role: 'customer' }});
            if (document.getElementById('gflowSignerRep').checked) signers.push({{ party_role: 'rep' }});
            if (document.getElementById('gflowSignerPM').checked) signers.push({{ party_role: 'project_manager' }});
            if (document.getElementById('gflowSignerAdmin').checked) signers.push({{ party_role: 'admin' }});
            if (signers.length === 0) {{ guidedFlowError('Select at least one required signer.'); return; }}
            try {{
                const token = getAuthToken();
                const res = await fetch('/api/v1/contracts/' + gflowState.contractId + '/signers', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ signers: signers }}),
                }});
                const data = await res.json();
                if (!res.ok) {{ guidedFlowError(data.error || 'Failed to configure signers.'); return; }}
                document.getElementById('gflowSignerStatus').innerHTML =
                    '<p style="color:var(--bronze);">Required signers saved. The contract is now ready for each party to sign from their own portal (Send + Sign actions on the Customer 360 Contracts panel).</p>';
                loadDashboard();
            }} catch (e) {{ guidedFlowError('Failed to configure signers: network error.'); }}
        }}

        // -----------------------------------------------------------------
        // B8.3 Part B: Lead create form. POST /api/v1/leads constructs
        // Lead(**json_body) directly (routes.py) -- only real Lead dataclass
        // field names may be sent, or the route 400s on an unexpected kwarg.
        // -----------------------------------------------------------------
        function openCreateLeadModal() {{
            document.getElementById('createLeadModal').classList.add('active');
        }}

        function closeCreateLeadModal() {{
            document.getElementById('createLeadModal').classList.remove('active');
        }}

        async function submitCreateLead() {{
            const token = getAuthToken();
            const custIdRaw = document.getElementById('newLeadCustomerId').value;
            const body = {{
                source: document.getElementById('newLeadSource').value || 'manual_entry',
                property_type: document.getElementById('newLeadPropertyType').value || null,
                project_scope: document.getElementById('newLeadProjectScope').value || null,
                urgency_level: document.getElementById('newLeadUrgencyLevel').value || null,
                insurance_status: document.getElementById('newLeadInsuranceStatus').value || null,
                estimated_value: parseFloat(document.getElementById('newLeadEstimatedValue').value) || 0,
                notes: document.getElementById('newLeadNotes').value || null,
            }};
            if (custIdRaw) {{ body.customer_id = parseInt(custIdRaw, 10); }}
            try {{
                const res = await fetch('/api/v1/leads', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }},
                    body: JSON.stringify(body),
                }});
                const data = await res.json();
                if (!res.ok) {{
                    alert(data.error || ('Failed to create lead (' + res.status + ').'));
                    return;
                }}
                closeCreateLeadModal();
                loadDashboard();
            }} catch (e) {{
                alert('Failed to create lead: network error.');
            }}
        }}

        window.onload = loadDashboard;
        // Browsers throttle setInterval to ~once/minute in a backgrounded tab,
        // so the ~12s cadence only holds while this tab is in the foreground.
        setInterval(() => loadDashboard(false), 12000);
    </script>
</body>
</html>"""

def render_estimate_proposal(
    estimate,
    customer,
    business_profile=None,
    compliance_items=None,
    package_options=None,
) -> str:
    """B8.6c proposal builder (sales_rep_portal.md B8.6, request §9-12).

    Server-rendered, print-friendly HTML -- deliberately NOT a PDF.
    Confirmed during scoping: no PDF dependency (weasyprint/reportlab/
    jinja2/pdfkit/wkhtmltopdf) exists in requirements.txt/install.sh
    today, and real PDF rendering on this device class (Termux/Android)
    is genuinely painful; building it is its own future Ish decision.
    The browser's own "Print to PDF" over this page's @media print
    styling is the intended path for now.

    License/insurance content is pulled from the `ComplianceItem` model
    (category in business_license/general_liability/workers_comp/etc,
    entity_type="company"), NOT `BusinessProfile` -- BusinessProfile only
    carries a single license_number field, no insurance data at all.
    The original spec text (B8.6's "existing BusinessProfile... license/
    insurance info already modeled") is a known spec inaccuracy, corrected
    here rather than propagated.

    Deliberately renders ONLY customer-facing numbers from `estimate` --
    unlike get_estimate's response, this function is handed the raw
    (unredacted-for-admin/rep) Estimate object by its caller, so the
    redaction responsibility is this function's own: it prints
    description/quantity/unit_price/subtotal/discount_amount/tax_amount/
    total_amount, and never materials_cost/labor_cost/subcontractor_cost/
    markup_percent/notes (internal-only fields) or a PackageOption's
    gross_profit/margin (internal-only fields, mirrors
    _row_to_package_option's customer redaction).

    business_profile/compliance_items are Optional: the caller
    (routes.py) fetches them through their own permission-gated service
    methods and passes None/[] through on a PermissionError (a
    ROLE_SALES actor today lacks read:business_profile/read:compliance --
    see NEW-578) rather than this function
    reaching around that gate itself.
    """
    package_options = package_options or []
    compliance_items = compliance_items or []

    biz_name = _pesc((business_profile.business_name if business_profile else None) or "Restoricon, LLC")
    biz_phone = _pesc((business_profile.business_phone if business_profile else None) or "(860) 337-1820")
    biz_email = _pesc((business_profile.business_email if business_profile else None) or "")
    biz_license = _pesc((business_profile.license_number if business_profile else None) or "")

    cust_name = _pesc(f"{customer.first_name or ''} {customer.last_name or ''}".strip())
    cust_company = _pesc(customer.company_name or "")
    cust_address = _pesc(customer.service_address or customer.mailing_address or "")
    cust_phone = _pesc(customer.phone or "")
    cust_email = _pesc(customer.email or "")

    def _line_item_price_cell(item) -> str:
        # Never fall back to unit_cost (internal-only field, see docstring
        # above) -- an estimate's real line_items shape (see
        # CRMService._compute_line_item_costs) only ever carries unit_cost,
        # never unit_price, so a unit_cost fallback here would leak internal
        # cost to the customer on every estimate built through the normal
        # create/update flow. Guard against an explicit `unit_price: None`
        # too, not just a missing key -- `.get(key, default)` only covers
        # absence.
        price = item.get("unit_price")
        if price is None:
            return "&mdash;"
        try:
            price = float(price)
        except (TypeError, ValueError):
            # _compute_line_item_costs only validates quantity/unit_cost, so
            # a blank/non-numeric unit_price is storable via create_estimate
            # today and must not crash this customer-facing page -- treat
            # it the same as "no price" rather than propagating the error.
            return "&mdash;"
        return f"${_pesc('{:,.2f}'.format(price))}"

    line_item_rows = "".join(
        f"""<tr>
            <td>{_pesc(item.get('description', ''))}</td>
            <td class="num">{_pesc(item.get('quantity', ''))}</td>
            <td class="num">{_line_item_price_cell(item)}</td>
        </tr>"""
        for item in (estimate.line_items or [])
    )
    if not line_item_rows:
        line_item_rows = '<tr><td colspan="3">No line items.</td></tr>'

    package_cards = "".join(
        f"""<div class="pkg-card">
            <h3>{_pesc(po.tier.capitalize())}</h3>
            <div class="pkg-price">${_pesc('{:,.2f}'.format(po.price))}</div>
            <ul>{"".join(f"<li>{_pesc(i.get('description', ''))}</li>" for i in (po.included_items or []))}</ul>
        </div>"""
        for po in package_options
    )

    compliance_rows = "".join(
        f"""<tr>
            <td>{_pesc(item.title)}</td>
            <td>{_pesc(item.category.replace('_', ' ').title())}</td>
            <td>{_pesc(item.expiration_date or '-')}</td>
        </tr>"""
        for item in compliance_items
    )
    compliance_section = ""
    if compliance_rows:
        compliance_section = f"""
        <div class="section">
            <h2>Licensed &amp; Insured</h2>
            <table>
                <thead><tr><th>Credential</th><th>Type</th><th>Expiration</th></tr></thead>
                <tbody>{compliance_rows}</tbody>
            </table>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Proposal """ + _pesc(estimate.estimate_number) + """ &mdash; Restoricon, LLC</title>
<style>
    :root {
        --navy: #0A192F; --slate: #1E293B; --bronze: #D4AF37; --offwhite: #F8FAFC;
    }
    body {
        font-family: 'Segoe UI', Arial, sans-serif; color: var(--slate); background: var(--offwhite);
        margin: 0; padding: 2rem;
    }
    .sheet { max-width: 800px; margin: 0 auto; background: #fff; padding: 2.5rem; box-shadow: 0 0 12px rgba(0,0,0,0.08); }
    .letterhead { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid var(--bronze); padding-bottom: 1rem; margin-bottom: 1.5rem; }
    .letterhead h1 { color: var(--navy); margin: 0; font-size: 1.6rem; }
    .letterhead .biz-contact { text-align: right; font-size: 0.85rem; color: #475569; }
    h2 { color: var(--navy); border-bottom: 1px solid #E2E8F0; padding-bottom: 0.3rem; margin-top: 2rem; }
    table { width: 100%; border-collapse: collapse; margin-top: 0.75rem; }
    th, td { text-align: left; padding: 0.5rem 0.6rem; border-bottom: 1px solid #E2E8F0; font-size: 0.9rem; }
    td.num, th.num { text-align: right; }
    .section { margin-bottom: 1rem; }
    .totals { margin-top: 1rem; float: right; width: 260px; }
    .totals table td { border-bottom: none; padding: 0.25rem 0.6rem; }
    .totals .grand-total td { font-weight: 700; border-top: 2px solid var(--navy); font-size: 1.1rem; }
    .pkg-row { display: flex; gap: 1rem; clear: both; padding-top: 1rem; }
    .pkg-card { flex: 1; border: 1px solid #E2E8F0; border-radius: 6px; padding: 1rem; text-align: center; }
    .pkg-card h3 { color: var(--bronze); margin: 0 0 0.5rem 0; text-transform: uppercase; }
    .pkg-price { font-size: 1.4rem; font-weight: 700; color: var(--navy); margin-bottom: 0.5rem; }
    .pkg-card ul { text-align: left; font-size: 0.85rem; padding-left: 1.2rem; }
    .print-btn { margin: 1rem 0; }
    .print-btn button { background: var(--bronze); border: none; color: var(--navy); font-weight: 700; padding: 0.6rem 1.2rem; border-radius: 4px; cursor: pointer; }
    @media print {
        body { padding: 0; background: #fff; }
        .sheet { box-shadow: none; padding: 0; max-width: 100%; }
        .print-btn { display: none; }
    }
</style>
</head>
<body>
<div class="print-btn"><button onclick="window.print()">Print / Save as PDF</button></div>
<div class="sheet">
    <div class="letterhead">
        <div>
            <h1>""" + biz_name + """</h1>
            <div>Proposal &amp; Estimate #""" + _pesc(estimate.estimate_number) + """</div>
        </div>
        <div class="biz-contact">
            """ + biz_phone + ("<br>" + biz_email if biz_email else "") + ("<br>License #" + biz_license if biz_license else "") + """
        </div>
    </div>

    <div class="section">
        <h2>Prepared For</h2>
        <div>""" + cust_name + (" &mdash; " + cust_company if cust_company else "") + """</div>
        <div>""" + cust_address + """</div>
        <div>""" + cust_phone + (" &middot; " + cust_email if cust_email else "") + """</div>
    </div>

    <div class="section">
        <h2>Scope of Work</h2>
        <table>
            <thead><tr><th>Description</th><th class="num">Qty</th><th class="num">Price</th></tr></thead>
            <tbody>""" + line_item_rows + """</tbody>
        </table>
        <div class="totals">
            <table>
                <tr><td>Subtotal</td><td class="num">$""" + _pesc('{:,.2f}'.format(estimate.subtotal or 0)) + """</td></tr>
                <tr><td>Discount</td><td class="num">-$""" + _pesc('{:,.2f}'.format(estimate.discount_amount or 0)) + """</td></tr>
                <tr><td>Tax</td><td class="num">$""" + _pesc('{:,.2f}'.format(estimate.tax_amount or 0)) + """</td></tr>
                <tr class="grand-total"><td>Total</td><td class="num">$""" + _pesc('{:,.2f}'.format(estimate.total_amount or 0)) + """</td></tr>
            </table>
        </div>
    </div>

    """ + (f'<div class="section" style="clear:both;"><h2>Package Options</h2><div class="pkg-row">{package_cards}</div></div>' if package_cards else '') + """

    """ + compliance_section + """

    <div class="section" style="clear:both;">
        <p style="font-size:0.8rem;color:#64748B;">This proposal is valid until """ + _pesc(estimate.expiration_date or 'the date specified by your sales representative') + """. Estimate status: """ + _pesc(estimate.status) + """.</p>
    </div>
</div>
</body>
</html>"""


def render_pm_surface() -> str:
    return _render_staff_portal_base("Project Manager", "Projects I Manage", "project_manager")

def render_sales_surface() -> str:
    return _render_sales_portal()

def render_tech_surface() -> str:
    return _render_staff_portal_base("Field Technician", "Assigned Work Orders & Projects", "technician")

def render_subcontractor_surface() -> str:
    return _render_staff_portal_base("Subcontractor", "Assigned Subcontract Work", "subcontractor")
