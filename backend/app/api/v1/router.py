from fastapi import APIRouter, Depends

from app.api.v1.endpoints import (
    audit,
    events,
    farms,
    handovers,
    imports,
    locations,
    lots,
    products,
    recalls,
)
from app.core.authorization import enforce_route_permission

api_router = APIRouter(dependencies=[Depends(enforce_route_permission)])

# Đăng ký API nghiệp vụ tại api_router để mặc định yêu cầu quyền.
api_router.include_router(farms.router, prefix="/farms", tags=["farms"])
api_router.include_router(lots.router, prefix="/lots", tags=["lots"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(products.router, prefix="/products", tags=["products"])
api_router.include_router(handovers.router, prefix="/handovers", tags=["handovers"])
api_router.include_router(locations.router, prefix="/locations", tags=["locations"])
api_router.include_router(imports.router, prefix="/imports", tags=["imports"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(
    recalls.router,
    prefix="/recalls",
    tags=["recalls"],
)
