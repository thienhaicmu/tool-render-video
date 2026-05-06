import base64
import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services.subtitle_engine import render_subtitle_preview

router = APIRouter(prefix="/api/subtitle", tags=["subtitle"])
logger = logging.getLogger("app.subtitle")


class SubtitlePreviewRequest(BaseModel):
    subtitle_style: str = Field("tiktok_bounce_v1", description="Style ID or alias")
    font_name: str = Field("Bungee", description="Font family name")
    font_size: int = Field(0, ge=0, le=120, description="0 = use preset default")
    aspect_ratio: str = Field("9:16", description="9:16 | 3:4 | 4:5 | 1:1 | 16:9")
    margin_v: int | None = Field(None, description="Vertical margin px; null = auto")
    sample_text: str = Field("This is a preview subtitle", max_length=120)


@router.post("/preview")
async def subtitle_preview(req: SubtitlePreviewRequest):
    """Render one PNG frame with the requested subtitle style applied.

    Returns image_base64 + mime_type on success, error string on failure.
    Never raises — callers should handle both shapes.
    """
    try:
        png_bytes = render_subtitle_preview(
            subtitle_style=req.subtitle_style,
            font_name=req.font_name,
            font_size=req.font_size,
            aspect_ratio=req.aspect_ratio,
            margin_v=req.margin_v,
            sample_text=req.sample_text,
        )
        return {
            "image_base64": base64.b64encode(png_bytes).decode("ascii"),
            "mime_type": "image/png",
        }
    except Exception as exc:
        logger.warning(
            "subtitle_preview_endpoint_error style=%s error=%s",
            req.subtitle_style, exc,
        )
        return JSONResponse(
            status_code=500,
            content={"error": str(exc)},
        )
