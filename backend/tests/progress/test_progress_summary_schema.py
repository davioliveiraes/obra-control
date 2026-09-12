from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema


def test_progress_summary_schema_is_read_only_flat_nullable_and_without_date_filter():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    validate_schema(schema)
    path = schema["paths"]["/api/v1/projects/{project_id}/progress-summary/"]
    assert set(path) == {"get"}
    operation = path["get"]
    assert operation["security"] == [{"cookieAuth": []}]
    assert "requestBody" not in operation
    assert set(operation["responses"]) == {"200", "403", "404"}
    assert len(operation["parameters"]) == 1
    param = operation["parameters"][0]
    assert param["name"] == "project_id" and param["in"] == "path" and param["required"]
    components = schema["components"]["schemas"]
    ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    fields = components[ref.rsplit("/", 1)[1]]["properties"]
    assert set(fields) == {"project_id", "as_of_date", "stages"}
    assert all(field["readOnly"] for field in fields.values())
    assert fields["project_id"]["type"] == "integer"
    assert fields["as_of_date"]["format"] == "date"
    assert fields["stages"]["type"] == "array"
    row_ref = fields["stages"]["items"]["$ref"]
    row = components[row_ref.rsplit("/", 1)[1]]["properties"]
    assert set(row) == {
        "stage_id",
        "progress_entry_id",
        "progress_date",
        "progress_percentage",
    }
    assert all(field["readOnly"] for field in row.values())
    assert not row["stage_id"].get("nullable", False)
    for field in ["progress_entry_id", "progress_date", "progress_percentage"]:
        assert row[field]["nullable"] is True
    assert row["progress_entry_id"]["type"] == "integer"
    assert row["progress_date"]["format"] == "date"
    assert row["progress_percentage"]["type"] == "string"
    assert row["progress_percentage"]["format"] == "decimal"
    description = operation["description"]
    for concept in [
        "progress_date <= as_of_date",
        "futuros",
        "roll-up",
        "somente leitura",
    ]:
        assert concept in description
