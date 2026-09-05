from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema


def test_organization_schema_describes_session_context_and_csrf():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    validate_schema(schema)
    paths = schema["paths"]
    listing = paths["/api/v1/organizations/"]
    current = paths["/api/v1/organizations/current/"]
    assert set(listing) == {"get"}
    assert set(current) == {"get", "put", "delete"}
    for operation in [listing["get"], *current.values()]:
        assert operation["security"] == [{"cookieAuth": []}]
    for method in ["put", "delete"]:
        assert any(
            parameter["name"] == "X-CSRFToken" and parameter["required"]
            for parameter in current[method]["parameters"]
        )
    assert "404" in current["get"]["responses"]
    assert "403" in current["put"]["responses"]
    assert "204" in current["delete"]["responses"]
    schemas = schema["components"]["schemas"]
    assert set(schemas["AccessibleOrganization"]["properties"]) == {
        "id",
        "name",
        "role",
    }
    assert schemas["SelectOrganization"]["required"] == ["organization_id"]
