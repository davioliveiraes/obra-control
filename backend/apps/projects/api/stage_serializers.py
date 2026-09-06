from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from ..models import ProjectStage


class ProjectStageSerializer(serializers.ModelSerializer):
    parent_id = serializers.PrimaryKeyRelatedField(
        source="parent",
        queryset=ProjectStage.objects.none(),
        required=False,
        allow_null=True,
        pk_field=serializers.IntegerField(min_value=1, max_value=2**63 - 1),
        error_messages={"does_not_exist": "Etapa pai indisponível."},
        help_text="Etapa do mesmo Project da URL; null define uma raiz.",
    )

    class Meta:
        model = ProjectStage
        fields = (
            "id",
            "name",
            "description",
            "parent_id",
            "position",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        project = self.context.get("project")
        if project is not None:
            self.fields["parent_id"].queryset = ProjectStage.objects.filter(
                project=project
            )

    def validate(self, attrs):
        parent_id = getattr(self.instance, "parent_id", None)
        if "parent" in attrs:
            parent_id = attrs["parent"].pk if attrs["parent"] is not None else None
        candidate = ProjectStage(
            pk=getattr(self.instance, "pk", None),
            project=self.context["project"],
            parent_id=parent_id,
        )
        try:
            candidate.clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                {"parent_id": error.message_dict["parent"]}
            ) from error
        return attrs
