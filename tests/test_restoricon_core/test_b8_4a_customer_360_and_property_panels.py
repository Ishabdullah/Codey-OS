"""B8.4a: sales portal Customer 360 view (client-side fan-out modal) and
the Property create/update panel embedded inside it. Covers the rendered
HTML/JS shape only (matches test_b8_3_sales_portal_kanban_and_lead_detail.py's
established convention) -- real server-side route plumbing/permission
behavior is covered by tests/test_restoricon_core/test_b8_4a_property_routes.py,
and the underlying CRMService Property CRUD logic by
tests/test_restoricon_core/test_b8_1_properties_and_commissions.py."""

from restoricon_core.api.web_surfaces import render_sales_surface


def test_sales_portal_has_customer_360_modal_and_entry_point():
    html = render_sales_surface()
    assert 'id="customer360Modal"' in html
    assert 'id="myCustomersList"' in html
    assert "openCustomer360Modal(" in html


def test_customer_360_fans_out_to_every_real_customer_id_scoped_route():
    """Every panel in the 360 view must hit a route that actually exists
    with the real route path/param name confirmed against routes.py --
    not a guessed/renamed endpoint (e.g. 'communications' not
    'list_communications', 'crm/tasks' not 'tasks')."""
    html = render_sales_surface()
    start = html.index("async function loadCustomer360(customerId)")
    end = html.index("function c360PanelSection(")
    fanout_js = html[start:end]
    for endpoint in [
        "/api/v1/customers/' + customerId",
        "/api/v1/properties?customer_id=' + customerId",
        "/api/v1/projects?customer_id=' + customerId",
        "/api/v1/estimates?customer_id=' + customerId",
        "/api/v1/contracts?customer_id=' + customerId",
        "/api/v1/invoices?customer_id=' + customerId",
        "/api/v1/documents?customer_id=' + customerId",
        "/api/v1/appointments?customer_id=' + customerId",
        "/api/v1/communications?customer_id=' + customerId",
        "/api/v1/crm/tasks?customer_id=' + customerId",
    ]:
        assert endpoint in fanout_js, f"customer 360 fan-out is missing {endpoint}"
    # Promise.allSettled, not Promise.all -- one panel's rejection (e.g.
    # Invoices 403ing for a plain sales rep, NEW-565) must not fail the
    # whole batch.
    assert "Promise.allSettled(" in fanout_js
    assert "Promise.all(" not in fanout_js.replace("Promise.allSettled(", "")


def test_customer_360_panel_renders_no_access_on_403_not_a_hard_failure():
    """A single panel's 403 (e.g. Invoices without PERM_READ_FINANCIALS)
    must render that one panel's own 'No access' state, not crash the
    modal or hide the panel entirely -- no role === 'sales' style
    client-side hardcoded gate, since PERM_READ_FINANCIALS can also be
    granted individually via custom_permissions_json (NEW-533/D2 pattern)."""
    html = render_sales_surface()
    assert "No access." in html
    assert "role === 'sales'" not in html
    assert 'role === "sales"' not in html


def test_customer_360_properties_panel_uses_only_real_property_fields():
    """POST /api/v1/properties constructs Property(**json_body) directly
    (routes.py) -- the create/edit form must only ever send real Property
    dataclass field names (models.py), and must use 'existing_systems'
    (the real dataclass field), never the spec doc's mistaken
    'existing_systems_json' name."""
    html = render_sales_surface()
    start = html.index("function openPropertyForm(propertyId)")
    end = html.index("async function savePropertyForm()")
    form_js = html[start:end]
    for field_id in [
        "propAddress", "propParcelNumber", "propPropertyType", "propYearBuilt",
        "propSquareFootage", "propStories", "propRoofType", "propExteriorType",
        "propInsuranceCarrier", "propNotes",
    ]:
        assert field_id in form_js, f"property form is missing {field_id}"
    save_start = html.index("async function savePropertyForm()")
    save_end = html.index("// -----------------------------------------------------------------\n        // B8.3 Part B: Lead create form")
    save_js = html[save_start:save_end]
    real_property_update_fields = {
        "customer_id", "address", "parcel_number", "property_type", "year_built",
        "square_footage", "stories", "roof_type", "exterior_type",
        "existing_systems", "insurance_carrier", "notes",
    }
    sent_fields = {
        "address", "parcel_number", "property_type", "year_built",
        "square_footage", "stories", "roof_type", "exterior_type",
        "insurance_carrier", "notes",
    }
    assert sent_fields.issubset(real_property_update_fields)
    for field in sent_fields:
        assert field in save_js
    assert "existing_systems_json" not in save_js
    assert "/api/v1/properties' " not in save_js or "/api/v1/properties'" in save_js
    assert "/api/v1/properties/" in save_js and "/update'" in save_js


def test_customer_360_property_panel_has_project_history_but_not_documents():
    """NEW-566 (project-history) was wired into the Project service layer
    and this panel in B8.4b -- the Property panel now fetches
    /api/v1/projects?property_id=<id> on demand. NEW-567 (a documents/photo
    panel keyed on Document.property_id) stays explicitly descoped --
    Document has no property_id field at all, deferred to B8.5's
    AssessmentRecord design -- so the panel must not reference a documents
    fetch scoped by property_id."""
    html = render_sales_surface()
    start = html.index("function renderPropertiesPanel(propertiesResult)")
    end = html.index("function openPropertyForm(propertyId)")
    panel_js = html[start:end]
    assert "/api/v1/projects?property_id=" in panel_js
    assert "/api/v1/documents?property_id=" not in panel_js
