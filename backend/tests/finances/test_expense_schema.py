from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema

from apps.finances.models import ExpenseStatus


def test_expense_schema_is_nested_paginated_and_has_no_delete_or_put():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    validate_schema(schema)
    listing = schema["paths"]["/api/v1/projects/{project_id}/expenses/"]
    detail = schema["paths"]["/api/v1/projects/{project_id}/expenses/{id}/"]
    assert set(listing) == {"get", "post"}
    assert set(detail) == {"get", "patch"}
    for operation in [*listing.values(), *detail.values()]:
        assert operation["security"] == [{"cookieAuth": []}]
        assert "403" in operation["responses"] and "404" in operation["responses"]
        assert any(
            p["name"] == "project_id" and p["in"] == "path" and p["required"]
            for p in operation["parameters"]
        )
    components = schema["components"]["schemas"]
    for operation in [listing["post"], detail["patch"]]:
        assert "400" in operation["responses"]
        assert any(
            p["name"] == "X-CSRFToken" and p["required"]
            for p in operation["parameters"]
        )
        ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        contract = components[ref.rsplit("/", 1)[1]]
        fields = contract["properties"]
        assert set(fields) == {
            "id",
            "stage_id",
            "description",
            "amount",
            "expense_date",
            "status",
            "notes",
            "created_at",
            "updated_at",
        }
        assert fields["stage_id"]["nullable"] is True
        assert "stage_id" not in contract.get("required", [])
        assert (
            fields["amount"]["type"] == "string"
            and fields["amount"]["format"] == "decimal"
        )
        assert fields["expense_date"]["format"] == "date"
        for name in ["id", "created_at", "updated_at"]:
            assert fields[name]["readOnly"] is True
        status = fields["status"]
        assert status["default"] == "active"
        assert (
            components[status["allOf"][0]["$ref"].rsplit("/", 1)[1]]["enum"]
            == ExpenseStatus.values
        )
        if operation is listing["post"]:
            assert {"description", "amount", "expense_date"} <= set(
                contract["required"]
            )
    page_ref = listing["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    assert set(components[page_ref.rsplit("/", 1)[1]]["properties"]) == {
        "count",
        "next",
        "previous",
        "results",
    }
    assert "409" in schema["paths"]["/api/v1/projects/{id}/"]["delete"]["responses"]
