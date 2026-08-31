import pytest
from restoricon_core.api.server import RestoriconAPIServer
from restoricon_core.api.web_surfaces import render_quote_surface, render_admin_surface, render_portal_surface


def test_render_quote_surface_contains_key_elements():
    html = render_quote_surface()
    assert "Request a Restoration Quote" in html
    assert "Emergency Service" in html
    assert "/api/v1/public/leads" in html


def test_subdomain_routing_matches_subdomains():
    server = RestoriconAPIServer(db_path=":memory:", port=0)
    try:
        # Test quote.restoricon.com
        status, headers, body = server.router.handle_request(
            "GET", "/", {"host": "quote.restoricon.com"}, b""
        )
        assert status == 200
        assert "Request a Restoration Quote" in body
        
        # Test admin.restoricon.com
        status, headers, body = server.router.handle_request(
            "GET", "/", {"host": "admin.restoricon.com"}, b""
        )
        assert status == 200
        assert "Staff & Admin Operations" in body or "Staff Admin" in body or "admin" in body.lower()
        
        # Test portal.restoricon.com
        status, headers, body = server.router.handle_request(
            "GET", "/", {"host": "portal.restoricon.com"}, b""
        )
        assert status == 200
        assert "Restoration Portal" in body or "portal" in body.lower()
    finally:
        server.stop()
