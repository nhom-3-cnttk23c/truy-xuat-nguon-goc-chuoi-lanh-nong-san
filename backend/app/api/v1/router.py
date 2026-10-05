from fastapi import APIRouter, Depends

from app.api.v1.endpoints import events, farms, lots
from app.core.authorization import enforce_route_permission

api_router = APIRouter(dependencies=[Depends(enforce_route_permission)])

# Đăng ký API nghiệp vụ tại api_router để mặc định yêu cầu quyền.
api_router.include_router(farms.router, prefix="/farms", tags=["farms"])
api_router.include_router(lots.router, prefix="/lots", tags=["lots"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
