from rest_framework.permissions import BasePermission


class HasActiveOrganization(BasePermission):
    """Require the context validated by OrganizationContextMiddleware, not a role."""

    message = "Selecione uma organização ativa."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and getattr(request, "organization", None) is not None
            and getattr(request, "membership", None) is not None
        )
