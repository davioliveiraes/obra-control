from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema


def test_progress_schema_describes_nested_paginated_decimal_crud():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    validate_schema(schema)
    prefix = "/api/v1/projects/{project_id}/stages/{stage_id}/progress/"
    listing = schema["paths"][prefix]
    detail = schema["paths"][prefix + "{id}/"]
    assert set(listing) == {"get", "post"}
    assert set(detail) == {"get", "patch", "delete"}
    for operation in [*listing.values(), *detail.values()]:
        assert operation["security"] == [{"cookieAuth": []}]
        assert {"403", "404"} <= set(operation["responses"])
        assert {"project_id", "stage_id"} <= {
            p["name"]
            for p in operation["parameters"]
            if p["in"] == "path" and p["required"]
        }
    components = schema["components"]["schemas"]
    for operation in [listing["post"], detail["patch"], detail["delete"]]:
        assert any(
            p["name"] == "X-CSRFToken" and p["required"]
            for p in operation["parameters"]
        )
    for operation in [listing["post"], detail["patch"]]:
        assert "400" in operation["responses"]
        ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        contract = components[ref.rsplit("/", 1)[1]]
        fields = contract["properties"]
        assert set(fields) == {
            "id",
            "progress_date",
            "progress_percentage",
            "notes",
            "created_at",
            "updated_at",
        }
        assert fields["progress_date"]["format"] == "date"
        assert fields["progress_percentage"]["type"] == "string"
        assert fields["progress_percentage"]["format"] == "decimal"
        for name in ["id", "created_at", "updated_at"]:
            assert fields[name]["readOnly"] is True
        if operation is listing["post"]:
            assert {"progress_date", "progress_percentage"} <= set(contract["required"])
        else:
            assert not contract.get("required")
    ref = listing["get"]["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    assert set(components[ref.rsplit("/", 1)[1]]["properties"]) == {
        "count",
        "next",
        "previous",
        "results",
    }
    for path in [
        "/api/v1/projects/{id}/",
        "/api/v1/projects/{project_id}/stages/{id}/",
    ]:
        assert "409" in schema["paths"][path]["delete"]["responses"]
