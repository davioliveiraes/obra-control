from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema


def test_customer_schema_describes_crud_without_writable_organization():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    validate_schema(schema)
    paths = schema["paths"]
    listing = paths["/api/v1/customers/"]
    detail = paths["/api/v1/customers/{id}/"]
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
    customer = components[post_ref.rsplit("/", 1)[1]]
    assert set(customer["properties"]) == {
        "id",
        "name",
        "email",
        "phone",
        "created_at",
        "updated_at",
    }
    assert "name" in customer["required"]
    for field in ["id", "created_at", "updated_at"]:
        assert customer["properties"][field]["readOnly"] is True
    assert not {"organization", "organization_id"} & set(customer["properties"])
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
