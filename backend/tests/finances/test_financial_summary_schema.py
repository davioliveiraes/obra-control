from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema


def test_financial_summary_schema_is_read_only_and_has_exact_money_contract():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    validate_schema(schema)
    path = schema["paths"]["/api/v1/projects/{project_id}/financial-summary/"]
    assert set(path) == {"get"}
    operation = path["get"]
    assert operation["security"] == [{"cookieAuth": []}]
    assert "requestBody" not in operation
    assert set(operation["responses"]) == {"200", "403", "404"}
    assert len(operation["parameters"]) == 1
    param = operation["parameters"][0]
    assert param["name"] == "project_id" and param["in"] == "path" and param["required"]
    ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    fields = schema["components"]["schemas"][ref.rsplit("/", 1)[1]]["properties"]
    assert set(fields) == {
        "project_id",
        "revenue_total",
        "expense_total",
        "realized_balance",
    }
    assert all(field["readOnly"] for field in fields.values())
    for field in ["revenue_total", "expense_total", "realized_balance"]:
        assert (
            fields[field]["type"] == "string" and fields[field]["format"] == "decimal"
        )
