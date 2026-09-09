from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema


def test_rdo_schema_nested_context_flat_payload_and_pagination():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    validate_schema(schema)
    prefix = "/api/v1/projects/{project_id}/daily-reports/"
    paths = schema["paths"]
    components = schema["components"]["schemas"]
    for collection_path, detail_path, activity in [
        (prefix, prefix + "{id}/", False),
        (
            prefix + "{report_id}/activities/",
            prefix + "{report_id}/activities/{id}/",
            True,
        ),
    ]:
        collection, detail = paths[collection_path], paths[detail_path]
        assert set(collection) == {"get", "post"}
        assert set(detail) == {"get", "patch", "delete"}
        for operation in [*collection.values(), *detail.values()]:
            assert operation["security"] == [{"cookieAuth": []}]
            assert {"403", "404"} <= set(operation["responses"])
            parameters = {
                p["name"]
                for p in operation["parameters"]
                if p["in"] == "path" and p["required"]
            }
            assert "project_id" in parameters
            if activity:
                assert "report_id" in parameters
        for operation in [collection["post"], detail["patch"], detail["delete"]]:
            assert any(
                p["name"] == "X-CSRFToken" and p["required"]
                for p in operation["parameters"]
            )
        for operation in [collection["post"], detail["patch"]]:
            assert "400" in operation["responses"]
            ref = operation["requestBody"]["content"]["application/json"]["schema"][
                "$ref"
            ]
            contract = components[ref.rsplit("/", 1)[1]]
            fields = contract["properties"]
            expected = {"id", "created_at", "updated_at"} | (
                {"stage_id", "description", "position"}
                if activity
                else {"report_date", "weather_notes", "general_notes"}
            )
            assert set(fields) == expected
            for name in ["id", "created_at", "updated_at"]:
                assert fields[name]["readOnly"] is True
            if activity:
                assert fields["stage_id"]["nullable"] is True
                assert "stage_id" not in contract.get("required", [])
            if operation is collection["post"]:
                assert ("description" if activity else "report_date") in contract[
                    "required"
                ]
            else:
                assert not contract.get("required")
        response = collection["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        if activity:
            assert response["type"] == "array"
        else:
            assert set(
                components[response["$ref"].rsplit("/", 1)[1]]["properties"]
            ) == {"count", "next", "previous", "results"}
    assert (
        "registros vinculados"
        in paths["/api/v1/projects/{id}/"]["delete"]["responses"]["409"]["description"]
    )
