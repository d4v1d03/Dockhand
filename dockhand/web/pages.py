"""HTML routes."""

from fastapi import APIRouter, Request

from dockhand.web.templating import templates

router = APIRouter()


@router.get("/", include_in_schema=False)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"sessions": []})
