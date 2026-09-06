from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema


def test_stage_schema_is_nested_flat_unpaginated_and_has_no_project_payload():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    validate_schema(schema)
    listing = schema["paths"]["/api/v1/projects/{project_id}/stages/"]
    detail = schema["paths"]["/api/v1/projects/{project_id}/stages/{id}/"]
    assert set(listing) == {"get", "post"}
    assert set(detail) == {"get", "patch", "delete"}
    for operation in [*listing.values(), *detail.values()]:
        assert operation["security"] == [{"cookieAuth": []}]
        assert any(
            p["name"] == "project_id" and p["in"] == "path" and p["required"]
            for p in operation["parameters"]
        )
        assert "404" in operation["responses"]
    for operation in [listing["post"], detail["patch"], detail["delete"]]:
        assert any(
            p["name"] == "X-CSRFToken" and p["required"]
            for p in operation["parameters"]
        )
    assert "409" in detail["delete"]["responses"]
    assert "204" in detail["delete"]["responses"]
    response = listing["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert response["type"] == "array"
    post_ref = listing["post"]["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    stage = schema["components"]["schemas"][post_ref.rsplit("/", 1)[1]]
    assert set(stage["properties"]) == {
        "id",
        "name",
        "description",
        "parent_id",
        "position",
        "created_at",
        "updated_at",
    }
    assert "name" in stage["required"]
    assert "parent_id" not in stage["required"]
    assert stage["properties"]["parent_id"]["nullable"] is True
    assert not any(
        p["name"] in ["page", "page_size"] for p in listing["get"]["parameters"]
    )
