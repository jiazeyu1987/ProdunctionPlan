from __future__ import annotations

from fastapi import APIRouter

from .routes import app_queries, commands, inventory, jobs, materials, orders


api_router = APIRouter(prefix="/api")
api_router.include_router(orders.router)
api_router.include_router(materials.router)
api_router.include_router(inventory.router)
api_router.include_router(jobs.router)
api_router.include_router(app_queries.router)
api_router.include_router(commands.router)
