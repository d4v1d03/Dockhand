"""HTML routes."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from dockhand.db.engine import db_session
from dockhand.db.models import Session
from dockhand.events import get_bus
from dockhand.web.templating import templates

router = APIRouter()


@router.get("/", include_in_schema=False)
def index(request: Request):
    with db_session() as db:
        sessions = [
            s.to_dict() for s in db.query(Session).order_by(Session.created_at.desc()).limit(30)
        ]
    return templates.TemplateResponse(request, "index.html", {"sessions": sessions})


@router.get("/sessions/{session_id}", include_in_schema=False)
def session_page(request: Request, session_id: str):
    with db_session() as db:
        sess = db.get(Session, session_id)
        if sess is None:
            raise HTTPException(404, "no such session")
        data = sess.to_dict()
    events = get_bus().replay(session_id)
    return templates.TemplateResponse(
        request,
        "session.html",
        {"s": data, "events": events, "last_id": events[-1]["id"] if events else 0},
    )


@router.get("/sessions/{session_id}/diff.patch", include_in_schema=False)
def session_patch(session_id: str):
    from dockhand.web.api import get_diff_data

    data = get_diff_data(session_id)
    return PlainTextResponse(
        data["patch"],
        media_type="text/x-patch",
        # attachment: the browser saves the file instead of displaying it
        headers={"Content-Disposition": f'attachment; filename="{session_id}.patch"'},
    )
