from pathlib import Path

from fastapi.templating import Jinja2Templates

from dockhand import __version__
from dockhand.config import get_settings

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["app_version"] = __version__
templates.env.globals["settings"] = get_settings()
