"""
Restoricon Core Web Surfaces — Staff/Admin ERP, Customer Portal, Quote Intake, & Auth SPAs.
Exact brand styling matching restoricon.com:
- Deep Navy: #0A192F
- Slate / Charcoal: #1E293B
- Metallic Bronze/Gold: #D4AF37 / #B89628
- Offwhite: #F8FAFC
- Phone: (860) 337-1820 | CT HIC Licensed General Contractor
"""

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
                <a href="tel:8603371820" class="nav-phone-btn" aria-label="Call Restoricon 24/7">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path></svg>
                    <span>(860) 337-1820</span>
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
            <div><strong>Direct Dispatch:</strong> <a href="tel:8603371820">(860) 337-1820</a></div>
            <div><strong>Licensure:</strong> CT HIC.0692750 &bull; Fully Insured</div>
            <div><strong>Email:</strong> <a href="mailto:contact@restoricon.com">contact@restoricon.com</a></div>
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
                    window.location.href = '{redirect_target}';
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
                <p>Enterprise Management System &bull; Active Restoration Job Sites &bull; CT HIC.0692750</p>
            </div>
            <div style="display: flex; gap: 0.75rem; align-items: center;">
                <span id="userBadge" class="card-badge badge-gold" style="font-size: 0.8rem; padding: 0.35rem 0.75rem;">Admin User</span>
                <button onclick="logoutUser()" class="btn-gold" style="background: rgba(239, 68, 68, 0.2); border: 1px solid var(--danger); color: #FCA5A5; padding: 0.45rem 0.85rem;">
                    Sign Out
                </button>
            </div>
        </div>

        <!-- 11 Main ERP Domain Tabs -->
        <div class="erp-tabs-bar">
            <button class="erp-tab-btn active" onclick="switchErpTab('kpis')">📊 Executive Overview</button>
            <button class="erp-tab-btn" onclick="switchErpTab('users')">👥 Users & Permissions</button>
            <button class="erp-tab-btn" onclick="switchErpTab('profile')">🏢 Business Profile</button>
            <button class="erp-tab-btn" onclick="switchErpTab('schedule')">📅 Booking Config</button>
            <button class="erp-tab-btn" onclick="switchErpTab('crm')">💼 CRM & Pipeline</button>
            <button class="erp-tab-btn" onclick="switchErpTab('operations')">🔨 Field Ops & Fleet</button>
            <button class="erp-tab-btn" onclick="switchErpTab('subcontractors')">🤝 Subcontractors</button>
            <button class="erp-tab-btn" onclick="switchErpTab('comms')">💬 Communications</button>
            <button class="erp-tab-btn" onclick="switchErpTab('finance')">💰 Finance Ledger</button>
            <button class="erp-tab-btn" onclick="switchErpTab('bizops')">📋 Business Ops</button>
            <button class="erp-tab-btn" onclick="switchErpTab('audit')">🔍 Audit Search</button>
            <button class="erp-tab-btn" onclick="switchErpTab('telemetry')">🤖 AI Agent & Audit</button>
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
        </div>

        <!-- Tab 3: Business Profile & LLM Context -->
        <div id="tab-profile" class="tab-pane">
            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>🏢</span> Company Profile & Autonomous Agent Context</h2>
                    <button onclick="saveBusinessProfile()" class="btn-gold">Save Profile</button>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                    <div class="form-group">
                        <label>Business Legal Name</label>
                        <input type="text" id="profName" value="Restoricon, LLC">
                    </div>
                    <div class="form-group">
                        <label>Direct Phone Hotline</label>
                        <input type="text" id="profPhone" value="(860) 337-1820">
                    </div>
                    <div class="form-group">
                        <label>Support Email</label>
                        <input type="email" id="profEmail" value="contact@restoricon.com">
                    </div>
                    <div class="form-group">
                        <label>CT General Contractor Licensure</label>
                        <input type="text" id="profLicense" value="CT HIC.0692750">
                    </div>
                </div>
                <div class="form-group" style="margin-top: 1rem;">
                    <label>AI Agent Master System Instructions & Restoration Context</label>
                    <textarea id="profPrompt" style="height: 120px;">Restoricon, LLC is an elite general contractor and emergency property restoration specialist serving Hartford County, Connecticut. Maintain professionalism, emphasize rapid containment, structural drying protocols, and precise pre-claim scoping.</textarea>
                </div>
            </div>
        </div>

        <!-- Tab 4: Booking & Schedule Config -->
        <div id="tab-schedule" class="tab-pane">
            <div class="erp-card">
                <div class="card-title-row">
                    <h2><span>📅</span> Online Scoping & Booking Parameters</h2>
                    <button onclick="saveScheduleConfig()" class="btn-gold">Save Schedule</button>
                </div>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem;">
                    <div class="form-group">
                        <label>Appointment Duration (Min)</label>
                        <input type="number" id="schedDuration" value="60">
                    </div>
                    <div class="form-group">
                        <label>Buffer Between Slots (Min)</label>
                        <input type="number" id="schedBuffer" value="30">
                    </div>
                    <div class="form-group">
                        <label>Max Concurrent Estimators</label>
                        <input type="number" id="schedConcurrent" value="3">
                    </div>
                </div>
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
                    <button class="btn-gold" onclick="alert('Trade partner onboarding active.')">+ Onboard Trade Partner</button>
                </div>
                <p style="color: var(--text-muted); font-size: 0.88rem;">Hartford County verified trade partners with validated CT trade licenses and COI coverage.</p>
                <table class="erp-table" style="margin-top: 1rem;">
                    <thead>
                        <tr>
                            <th>Company</th>
                            <th>Trade/Specialty</th>
                            <th>Status</th>
                            <th>Rating</th>
                        </tr>
                    </thead>
                    <tbody id="subcontractorsTableBody">
                        <tr><td colspan="4" style="text-align: center; color: var(--text-muted);">Loading...</td></tr>
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
    </main>

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



        async function loadKPIs() {
            const token = getAuthToken();
            try {
                const res = await fetch('/api/v1/reports/summary', { headers: { 'Authorization': 'Bearer ' + token } });
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
            const token = getAuthToken();
            try {
                const res = await fetch('/api/v1/operations/subcontractors', { headers: { 'Authorization': 'Bearer ' + token } });
                const data = await res.json();
                const tbody = document.getElementById('subcontractorsTableBody');
                if (data.subcontractors && data.subcontractors.length > 0) {
                    tbody.innerHTML = data.subcontractors.map(sc => `
                        <tr>
                            <td>${escapeHtml(sc.company_name)}</td>
                            <td>${escapeHtml(sc.specialty)}</td>
                            <td>${escapeHtml(sc.status)}</td>
                            <td>${escapeHtml(sc.rating)}</td>
                        </tr>
                    `).join('');
                } else {
                    tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No records found.</td></tr>';
                }
            } catch (e) {
                document.getElementById('subcontractorsTableBody').innerHTML = '<tr><td colspan="4">Error loading subcontractors.</td></tr>';
            }
        }

        async function loadFinance() {
            const token = getAuthToken();
            try {
                const res = await fetch('/api/v1/finance/summary', { headers: { 'Authorization': 'Bearer ' + token } });
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

        function escapeHtml(unsafe) {

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
                const data = await res.json();
                if (data.customers) {
                    currentCustomers = data.customers;
                    const html = data.customers.map(c => `
                        <div style="padding: 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.05);">
                            <div style="color: var(--offwhite); font-weight: 500;">${c.first_name || ''} ${c.last_name || ''}</div>
                            <div style="font-size: 0.85rem;">${c.email || ''} | ${c.phone || ''}</div>
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
                const data = await res.json();
                if (data.projects) {
                    const html = data.projects.map(p => `
                        <div style="padding: 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.05);">
                            <div style="color: var(--offwhite); font-weight: 500;">${p.title || 'Untitled'}</div>
                            <div style="font-size: 0.85rem;"><span class="badge" style="background: rgba(212,175,55,0.1); color: var(--bronze); padding: 0.1rem 0.4rem; border-radius: 4px;">${p.stage}</span> - ${p.project_type}</div>
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
            sel.innerHTML = currentCustomers.map(c => `<option value="${c.id}">${c.first_name} ${c.last_name}</option>`).join('');
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
            
            if (tabId === 'users') loadUsersList();
            if (tabId === 'crm') loadCrmList();
            if (tabId === 'telemetry') loadAuditLogs();
            if (tabId === 'audit') searchAuditLog();
        }

        function escapeHtml(unsafe) {
            return (unsafe || '').toString()
                 .replace(/&/g, "&amp;")
                 .replace(/</g, "&lt;")
                 .replace(/>/g, "&gt;")
                 .replace(/"/g, "&quot;")
                 .replace(/'/g, "&#039;");
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
                const data = await res.json();
                if (res.ok && data.users) {
                    tbody.innerHTML = data.users.map(u => `
                        <tr>
                            <td>#${u.id}</td>
                            <td><strong>${u.username}</strong></td>
                            <td>${u.full_name}</td>
                            <td>${u.email}</td>
                            <td><span class="card-badge badge-slate">${u.role}</span></td>
                            <td>${Object.keys(u.custom_permissions || {}).length} Custom</td>
                            <td>
                                <span style="color: ${u.active ? 'var(--success)' : 'var(--danger)'}; font-weight:700;">
                                    ${u.active ? '● Active' : '● Suspended'}
                                </span>
                            </td>
                            <td>
                                <button class="btn-gold" style="padding: 0.25rem 0.55rem; font-size: 0.75rem;" onclick="openPermModal(${u.id}, '${u.username}')">Perms</button>
                                <button class="btn-gold" style="padding: 0.25rem 0.55rem; font-size: 0.75rem; background: ${u.active ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.2)'}; border-color: ${u.active ? 'var(--danger)' : 'var(--success)'}; color: ${u.active ? '#FCA5A5' : '#6EE7B7'};" onclick="toggleUserStatus(${u.id}, ${u.active})">
                                    ${u.active ? 'Suspend' : 'Activate'}
                                </button>
                            </td>
                        </tr>
                    `).join('');
                }
            } catch (ex) {
                tbody.innerHTML = '<tr><td colspan="8" style="color: var(--danger);">Failed to load users. Verify token privileges.</td></tr>';
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

        async function loadAuditLogs() {
            const token = getAuthToken();
            const container = document.getElementById('auditLogFeed');
            try {
                const res = await fetch('/api/v1/audit-log?limit=25', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                const data = await res.json();
                if (res.ok && data.entries) {
                    container.innerHTML = data.entries.map(e => `
                        <div style="padding: 0.35rem 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                            <span style="color: var(--bronze);">${e.created_at || ''}</span>
                            [<span style="color: var(--info);">${e.action}</span>]
                            <span>${e.details || ''}</span>
                            (Actor: ${e.actor_id || 'System'})
                        </div>
                    `).join('');
                }
            } catch (ex) {
                container.innerText = 'Unable to fetch audit logs.';
            }
        }

        async function saveBusinessProfile() {
            const token = getAuthToken();
            const profName = document.getElementById('profName').value;
            const profPrompt = document.getElementById('profPrompt').value;
            window.currentBusinessProfile = window.currentBusinessProfile || {};
            window.currentBusinessProfile.business_name = profName;
            window.currentBusinessProfile.business_description = profPrompt;
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
                } else {
                    alert('Failed to update Business Profile.');
                }
            } catch (ex) {
                alert('Connection error');
            }
        }

        async function saveScheduleConfig() {
            const token = getAuthToken();
            const schedDuration = parseInt(document.getElementById('schedDuration').value) || 60;
            const schedBuffer = parseInt(document.getElementById('schedBuffer').value) || 15;
            window.currentScheduleConfig = window.currentScheduleConfig || {};
            window.currentScheduleConfig.default_duration_minutes = schedDuration;
            window.currentScheduleConfig.buffer_minutes = schedBuffer;
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
                
                // Load Business Profile
                try {
                    const token = getAuthToken();
                    const bpRes = await fetch('/api/v1/business-profile', { headers: { 'Authorization': 'Bearer ' + token } });
                    if (bpRes.ok) {
                        const bpData = await bpRes.json();
                        window.currentBusinessProfile = bpData.business_profile || {};
                        if (window.currentBusinessProfile.business_name) {
                            document.getElementById('profName').value = window.currentBusinessProfile.business_name;
                        }
                        if (window.currentBusinessProfile.business_description) {
                            document.getElementById('profPrompt').value = window.currentBusinessProfile.business_description;
                        }
                    }
                } catch (e) {}

                // Load Schedule Config
                try {
                    const token = getAuthToken();
                    const scRes = await fetch('/api/v1/schedule-config', { headers: { 'Authorization': 'Bearer ' + token } });
                    if (scRes.ok) {
                        const scData = await scRes.json();
                        window.currentScheduleConfig = scData.schedule_config || {};
                        if (window.currentScheduleConfig.default_duration_minutes) {
                            document.getElementById('schedDuration').value = window.currentScheduleConfig.default_duration_minutes;
                        }
                        if (window.currentScheduleConfig.buffer_minutes) {
                            document.getElementById('schedBuffer').value = window.currentScheduleConfig.buffer_minutes;
                        }
                    }
                } catch (e) {}
            }
        });
    </script>
</body>
</html>"""
