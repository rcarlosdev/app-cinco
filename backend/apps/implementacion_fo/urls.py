from rest_framework.routers import DefaultRouter
from apps.implementacion_fo.views import MappingPredioViewSet, SharePointMappingConfigViewSet

router = DefaultRouter()
router.register(r"mapping-predios", MappingPredioViewSet, basename="mapping-predios")
router.register(r"sharepoint-mapping", SharePointMappingConfigViewSet, basename="sharepoint-mapping")

urlpatterns = router.urls

