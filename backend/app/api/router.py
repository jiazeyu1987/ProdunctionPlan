from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import ROLE_SCHEDULER, get_current_user, require_roles
from .routes import app_queries, auth, commands, inventory, jobs, materials, orders


api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(
    orders.router,
    dependencies=[Depends(get_current_user), Depends(require_roles(ROLE_SCHEDULER))],
)
api_router.include_router(
    materials.router,
    dependencies=[Depends(get_current_user), Depends(require_roles(ROLE_SCHEDULER))],
)
api_router.include_router(
    inventory.router,
    dependencies=[Depends(get_current_user), Depends(require_roles(ROLE_SCHEDULER))],
)
api_router.include_router(jobs.router, dependencies=[Depends(get_current_user)])
api_router.include_router(app_queries.router, dependencies=[Depends(get_current_user)])
api_router.include_router(commands.router, dependencies=[Depends(get_current_user)])
