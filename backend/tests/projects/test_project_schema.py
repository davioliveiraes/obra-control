from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema

from apps.projects.models import ProjectStatus


def test_project_schema_describes_tenant_scoped_crud_and_optional_fields():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    validate_schema(schema)
    listing = schema["paths"]["/api/v1/projects/"]
    detail = schema["paths"]["/api/v1/projects/{id}/"]
    assert set(listing) == {"get", "post"}
    assert set(detail) == {"get", "patch", "delete"}
    for operation in [*listing.values(), *detail.values()]:
        assert operation["security"] == [{"cookieAuth": []}]
    for operation in [listing["post"], detail["patch"], detail["delete"]]:
        assert any(
            p["name"] == "X-CSRFToken" and p["required"]
            for p in operation["parameters"]
        )
    for operation in detail.values():
        assert "404" in operation["responses"]

    components = schema["components"]["schemas"]
    post_ref = listing["post"]["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    project = components[post_ref.rsplit("/", 1)[1]]
    properties = project["properties"]
    assert set(properties) == {
        "id",
        "name",
        "customer_id",
        "status",
        "description",
        "planned_start_date",
        "planned_end_date",
        "created_at",
        "updated_at",
    }
    assert "name" in project["required"]
    for field in ["customer_id", "planned_start_date", "planned_end_date"]:
        assert field not in project["required"]
        assert properties[field]["nullable"] is True
    assert properties["planned_start_date"]["format"] == "date"
    assert properties["planned_end_date"]["format"] == "date"
    assert properties["customer_id"]["type"] == "integer"
    for field in ["id", "created_at", "updated_at"]:
        assert properties[field]["readOnly"] is True
    status_schema = properties["status"]
    assert status_schema["default"] == "planning"
    status_ref = status_schema["allOf"][0]["$ref"]
    assert components[status_ref.rsplit("/", 1)[1]]["enum"] == ProjectStatus.values
    assert "201" in listing["post"]["responses"]
    page_ref = listing["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    assert set(components[page_ref.rsplit("/", 1)[1]]["properties"]) == {
        "count",
        "next",
        "previous",
        "results",
    }
