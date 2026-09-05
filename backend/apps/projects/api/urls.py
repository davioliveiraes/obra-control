from rest_framework.routers import SimpleRouter

from .views import ProjectViewSet

app_name = "projects"

router = SimpleRouter()
router.register("", ProjectViewSet, basename="project")
urlpatterns = router.urls
