"""HTTP routers, mounted under /api."""

from fastapi import APIRouter

from app.api.routes import assessments, classes, review, students, submissions

api_router = APIRouter()
api_router.include_router(classes.router)
api_router.include_router(students.router)
api_router.include_router(assessments.router)
api_router.include_router(submissions.router)
api_router.include_router(review.router)

__all__ = ["api_router"]
