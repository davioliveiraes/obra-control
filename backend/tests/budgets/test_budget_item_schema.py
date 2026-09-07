from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema


def test_budget_schema_is_nested_decimal_flat_and_has_read_only_total():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    validate_schema(schema)
    listing = schema["paths"]["/api/v1/projects/{project_id}/budget/items/"]
    detail = schema["paths"]["/api/v1/projects/{project_id}/budget/items/{id}/"]
    assert set(listing) == {"get", "post"}
    assert set(detail) == {"get", "patch", "delete"}
    for operation in [*listing.values(), *detail.values()]:
        assert operation["security"] == [{"cookieAuth": []}]
        assert "403" in operation["responses"] and "404" in operation["responses"]
        assert any(
            p["name"] == "project_id" and p["in"] == "path" and p["required"]
            for p in operation["parameters"]
        )
    for operation in [listing["post"], detail["patch"], detail["delete"]]:
        assert any(
            p["name"] == "X-CSRFToken" and p["required"]
            for p in operation["parameters"]
        )
    assert (
        "400" in listing["post"]["responses"] and "400" in detail["patch"]["responses"]
    )
    assert "204" in detail["delete"]["responses"]
    assert (
        listing["get"]["responses"]["200"]["content"]["application/json"]["schema"][
            "type"
        ]
        == "array"
    )
    assert not any(
        p["name"] in ["page", "page_size"] for p in listing["get"]["parameters"]
    )

    def request_schema(operation):
        reference = operation["requestBody"]["content"]["application/json"]["schema"][
            "$ref"
        ]
        return schema["components"]["schemas"][reference.rsplit("/", 1)[1]]

    create = request_schema(listing["post"])
    patch = request_schema(detail["patch"])
    writable = {"stage_id", "description", "unit", "quantity", "unit_price"}
    assert writable <= set(create["required"])
    for contract in [create, patch]:
        assert set(contract["properties"]) == writable | {
            "id",
            "total",
            "created_at",
            "updated_at",
        }
        assert {
            name
            for name, field in contract["properties"].items()
            if not field.get("readOnly", False)
        } == writable
        assert contract["properties"]["total"]["readOnly"] is True
        for name in ["quantity", "unit_price", "total"]:
            assert contract["properties"][name]["type"] == "string"
            assert contract["properties"][name]["format"] == "decimal"
    assert "enum" not in create["properties"]["unit"]
