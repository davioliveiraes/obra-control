from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema


def test_planning_schema_has_scoped_routes_and_immutable_stage_on_patch():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    validate_schema(schema)
    listing = schema["paths"]["/api/v1/projects/{project_id}/planning/"]
    detail = schema["paths"]["/api/v1/projects/{project_id}/planning/{id}/"]
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
    assert "400" in listing["post"]["responses"]
    assert "400" in detail["patch"]["responses"]
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
    fields = {
        "id",
        "stage_id",
        "planned_start_date",
        "planned_end_date",
        "created_at",
        "updated_at",
    }
    assert set(create["properties"]) == fields
    assert set(patch["properties"]) == fields
    assert {"stage_id", "planned_start_date", "planned_end_date"} <= set(
        create["required"]
    )
    assert not create["properties"]["stage_id"].get("readOnly", False)
    assert patch["properties"]["stage_id"]["readOnly"] is True
    assert {
        name
        for name, field in patch["properties"].items()
        if not field.get("readOnly", False)
    } == {"planned_start_date", "planned_end_date"}
    for name in ["planned_start_date", "planned_end_date"]:
        assert create["properties"][name]["format"] == "date"
        assert not create["properties"][name].get("nullable", False)
