from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import MembershipRole


class HasActiveOrganization(BasePermission):
    """Require the context validated by OrganizationContextMiddleware, not a role."""

    message = "Selecione uma organização ativa."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and getattr(request, "organization", None) is not None
            and getattr(request, "membership", None) is not None
        )


class IsOrganizationAdminOrReadOnly(BasePermission):
    """Authorize methods using the membership already validated by the middleware."""

    message = "Seu papel na organização não permite esta operação."

    def has_permission(self, request, view):
        membership = getattr(request, "membership", None)
        return membership is not None and (
            request.method in SAFE_METHODS
            or membership.role in (MembershipRole.OWNER, MembershipRole.ADMIN)
        )
