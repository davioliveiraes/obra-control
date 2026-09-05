from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema


def test_auth_schema_describes_session_csrf_and_identity_contracts():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    validate_schema(schema)
    paths = schema["paths"]
    assert set(paths) == {
        "/api/v1/auth/csrf/",
        "/api/v1/auth/login/",
        "/api/v1/auth/logout/",
        "/api/v1/auth/me/",
    }
    assert set(paths["/api/v1/auth/login/"]) == {"post"}
    assert set(paths["/api/v1/auth/logout/"]) == {"post"}
    assert not paths["/api/v1/auth/csrf/"]["get"].get("security")
    assert not paths["/api/v1/auth/login/"]["post"].get("security")
    for endpoint, method in [("me", "get"), ("logout", "post")]:
        assert paths[f"/api/v1/auth/{endpoint}/"][method]["security"] == [
            {"cookieAuth": []}
        ]
    for endpoint in ["login", "logout"]:
        assert any(
            parameter["name"] == "X-CSRFToken" and parameter["required"]
            for parameter in paths[f"/api/v1/auth/{endpoint}/"]["post"]["parameters"]
        )
    schemas = schema["components"]["schemas"]
    assert schemas["Login"]["properties"]["password"]["writeOnly"] is True
    assert set(schemas["UserIdentity"]["properties"]) == {
        "id",
        "email",
        "first_name",
        "last_name",
    }
