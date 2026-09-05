from .context import CURRENT_ORGANIZATION_SESSION_KEY, get_active_membership


class OrganizationContextMiddleware:
    """Revalidate the selected membership on each authenticated request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.organization = None
        request.membership = None

        if not request.user.is_authenticated:
            request.session.pop(CURRENT_ORGANIZATION_SESSION_KEY, None)
        elif CURRENT_ORGANIZATION_SESSION_KEY in request.session:
            membership = get_active_membership(
                request.user, request.session[CURRENT_ORGANIZATION_SESSION_KEY]
            )
            if membership is None:
                request.session.pop(CURRENT_ORGANIZATION_SESSION_KEY, None)
            else:
                request.membership = membership
                request.organization = membership.organization

        return self.get_response(request)
