from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema


def test_cost_summary_schema_is_read_only_with_flat_direct_stage_values():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    validate_schema(schema)
    path = schema["paths"]["/api/v1/projects/{project_id}/cost-summary/"]
    assert set(path) == {"get"}
    operation = path["get"]
    assert operation["security"] == [{"cookieAuth": []}]
    assert "requestBody" not in operation
    assert set(operation["responses"]) == {"200", "403", "404"}
    assert len(operation["parameters"]) == 1
    assert operation["parameters"][0]["name"] == "project_id"
    assert (
        operation["parameters"][0]["in"] == "path"
        and operation["parameters"][0]["required"]
    )
    components = schema["components"]["schemas"]
    ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    summary = components[ref.rsplit("/", 1)[1]]["properties"]
    money_fields = {"budget_total", "actual_total", "variance_amount"}
    assert set(summary) == money_fields | {
        "project_id",
        "unallocated_actual_total",
        "stages",
    }
    assert summary["stages"]["type"] == "array"
    stage_ref = summary["stages"]["items"]["$ref"]
    stage = components[stage_ref.rsplit("/", 1)[1]]["properties"]
    assert set(stage) == money_fields | {"stage_id"}
    for fields in [summary, stage]:
        assert all(field["readOnly"] for field in fields.values())
        for name in money_fields | (
            {"unallocated_actual_total"} if fields is summary else set()
        ):
            assert (
                fields[name]["type"] == "string" and fields[name]["format"] == "decimal"
            )
