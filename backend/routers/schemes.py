from __future__ import annotations

import base64
import binascii
from pathlib import Path
import struct
from typing import Annotated
import urllib.request
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from auth import current_user_id
from database import get_connection
from services.image_client import ImageGenerationUnavailable, generate_facade_render
from services.render_styles import render_style_options

router = APIRouter(prefix="/api", tags=["schemes"])
UserId = Annotated[str, Depends(current_user_id)]
RENDERS_DIR = Path(__file__).resolve().parents[1] / "renders"
RENDERS_DIR.mkdir(exist_ok=True)
CAPTURE_PATH = Path("k:/FileK/AAAAASCD/facadegpt2/scheme_3d_threejs.png")
ALLOWED_IMAGE_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/bmp": ".bmp",
    "image/webp": ".webp",
}
MAX_SOURCE_IMAGE_BYTES = 20 * 1024 * 1024
MIN_SOURCE_IMAGE_SIDE = 240
MAX_SOURCE_IMAGE_SIDE = 8000


class RenderRequest(BaseModel):
    view_type: str
    style: str = "photoreal_day"
    source_type: str = "model_capture"
    model_image: str | None = None
    user_image: str | None = None
    bbox: list[int] | None = None


class CaptureRequest(BaseModel):
    image: str
    filename: str = "scheme_3d_threejs.png"


def _require_scheme(conn, scheme_id: str, user_id: str) -> None:
    exists = conn.execute(
        """
        SELECT s.id
        FROM schemes s
        JOIN projects p ON p.id = s.project_id
        WHERE s.id = ? AND p.user_id = ?
        """,
        (scheme_id, user_id),
    ).fetchone()
    if not exists:
        raise HTTPException(404, "Scheme not found")


def _scheme_payload(conn, scheme_id: str, user_id: str) -> dict:
    scheme = conn.execute(
        """
        SELECT s.id AS scheme_id, s.scheme_name, s.scheme_label, s.strategy,
               replace(s.created_at, ' ', 'T') || 'Z' AS created_at,
               s.description, s.risk_note, s.fitness_score
        FROM schemes s
        JOIN projects p ON p.id = s.project_id
        WHERE s.id = ? AND p.user_id = ?
        """,
        (scheme_id, user_id),
    ).fetchone()
    if not scheme:
        raise HTTPException(404, "Scheme not found")
    params = conn.execute("SELECT * FROM scheme_params WHERE scheme_id=?", (scheme_id,)).fetchone()
    perf = conn.execute("SELECT * FROM scheme_performance WHERE scheme_id=?", (scheme_id,)).fetchone()
    return {"scheme": dict(scheme) | {"params": dict(params), "performance": dict(perf)}}


@router.get("/schemes/{scheme_id}")
def get_scheme(scheme_id: str, user_id: UserId):
    with get_connection() as conn:
        return _scheme_payload(conn, scheme_id, user_id)


@router.delete("/schemes/{scheme_id}", status_code=204)
def delete_scheme(scheme_id: str, user_id: UserId):
    with get_connection() as conn:
        _require_scheme(conn, scheme_id, user_id)
        local_images = [
            image_url
            for row in conn.execute(
                "SELECT image_url, source_image_url FROM render_images WHERE scheme_id = ?", (scheme_id,)
            ).fetchall()
            for image_url in (row["image_url"], row["source_image_url"])
            if image_url and image_url.startswith("/renders/")
        ]
        conn.execute("DELETE FROM schemes WHERE id = ?", (scheme_id,))

    renders_root = RENDERS_DIR.resolve()
    for image_url in local_images:
        image_path = (RENDERS_DIR / Path(image_url).name).resolve()
        if image_path.parent == renders_root:
            image_path.unlink(missing_ok=True)
    return Response(status_code=204)


@router.get("/schemes/{scheme_id}/teaching-feedback")
def get_feedback(scheme_id: str, user_id: UserId):
    with get_connection() as conn:
        feedback = conn.execute(
            """
            SELECT tf.key_conflict, tf.priority, tf.avoid, tf.next_step, tf.discussion
            FROM teaching_feedback tf
            JOIN schemes s ON s.id = tf.scheme_id
            JOIN projects p ON p.id = s.project_id
            WHERE tf.scheme_id = ? AND p.user_id = ?
            """,
            (scheme_id, user_id),
        ).fetchone()
        if not feedback:
            raise HTTPException(404, "Feedback not found")
        return dict(feedback)


@router.get("/render/view-options")
def view_options():
    return {
        "views": [
            {"id": "indoor", "name": "室内人视角", "description": "从室内看向窗外"},
            {"id": "outdoor", "name": "室外视角", "description": "街道人视角度"},
            {"id": "axonometric", "name": "轴测视角", "description": "45度俯视轴测"},
            {"id": "elevation", "name": "立面正视图", "description": "正投影立面"},
        ]
    }


@router.get("/render/style-options")
def style_options():
    return {"styles": render_style_options()}


@router.get("/schemes/{scheme_id}/renders")
def get_scheme_renders(scheme_id: str, user_id: UserId):
    with get_connection() as conn:
        _require_scheme(conn, scheme_id, user_id)
        rows = conn.execute(
            """
            SELECT id, scheme_id, view_type, image_url, source_type, source_image_url,
                   status, provider, prompt, replace(created_at, ' ', 'T') || 'Z' AS created_at
            FROM render_images
            WHERE scheme_id = ?
            ORDER BY created_at DESC
            """,
            (scheme_id,),
        ).fetchall()
    return {"renders": [dict(row) for row in rows]}


@router.post("/schemes/{scheme_id}/render")
def render_scheme(scheme_id: str, payload: RenderRequest, user_id: UserId):
    render_id = str(uuid.uuid4())
    if payload.source_type not in {"model_capture", "user_image"}:
        raise HTTPException(400, "source_type must be model_capture or user_image")

    with get_connection() as conn:
        scheme = _scheme_payload(conn, scheme_id, user_id)["scheme"]
        source_type = payload.source_type
        model_image = _validated_image_data_url(payload.model_image, "3D model capture")
        user_image = _validated_image_data_url(payload.user_image, "uploaded building image") if source_type == "user_image" else None
        bbox = _validated_bbox(payload.bbox, user_image) if payload.bbox else None
        source_image_url = _persist_data_image(user_image or model_image, render_id, "source")
        try:
            generated = generate_facade_render(
                scheme,
                payload.view_type,
                payload.style,
                source_type=source_type,
                model_image=model_image["data_url"],
                user_image=user_image["data_url"] if user_image else None,
                bbox=bbox,
            )
            image_url = _persist_remote_image(generated["image_url"], render_id)
            status = generated["status"]
        except ImageGenerationUnavailable as exc:
            image_url = ""
            status = "fallback"
            generated = {"error": str(exc), "provider": "dashscope", "source_type": source_type}
        conn.execute(
            """
            INSERT INTO render_images (
                id, scheme_id, view_type, image_url, source_type,
                source_image_url, status, provider, prompt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                render_id,
                scheme_id,
                payload.view_type,
                image_url,
                source_type,
                source_image_url,
                status,
                generated.get("provider"),
                generated.get("prompt"),
            ),
        )
    return {
        "render_id": render_id,
        "scheme_id": scheme_id,
        "image_url": image_url,
        "source_image_url": source_image_url,
        "status": status,
        "source_type": source_type,
        **generated,
    }


def _persist_remote_image(remote_url: str, render_id: str) -> str:
    path = RENDERS_DIR / f"{render_id}.png"
    try:
        request = urllib.request.Request(remote_url, headers={"User-Agent": "FacadeGPT/1.0"})
        with urllib.request.urlopen(request, timeout=45) as response:
            path.write_bytes(response.read())
        return f"/renders/{path.name}"
    except Exception:
        return remote_url


def _persist_data_image(image: dict, render_id: str, role: str) -> str:
    suffix = image["extension"]
    path = RENDERS_DIR / f"{render_id}-{role}{suffix}"
    path.write_bytes(image["bytes"])
    return f"/renders/{path.name}"


def _validated_image_data_url(data_url: str | None, label: str) -> dict:
    if not data_url:
        raise HTTPException(400, f"{label} is required")
    if not data_url.startswith("data:image/") or ";base64," not in data_url:
        raise HTTPException(400, f"{label} must be a base64 image data URL")

    header, raw_b64 = data_url.split(",", 1)
    mime_type = header[5:].split(";", 1)[0].lower()
    if mime_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise HTTPException(400, f"{label} must be JPEG, PNG, BMP, or WEBP")
    try:
        image_bytes = base64.b64decode(raw_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(400, f"{label} contains invalid base64 data") from exc

    if len(image_bytes) > MAX_SOURCE_IMAGE_BYTES:
        raise HTTPException(400, f"{label} must be 20MB or smaller")
    detected = _detect_image_type(image_bytes)
    if not detected:
        raise HTTPException(400, f"{label} is not a supported image")
    detected_mime = "image/jpeg" if detected == "jpeg" else f"image/{detected}"
    if detected_mime != mime_type and not (mime_type == "image/jpg" and detected_mime == "image/jpeg"):
        raise HTTPException(400, f"{label} image type does not match the data URL")

    width, height = _image_dimensions(image_bytes, detected)
    if (
        width < MIN_SOURCE_IMAGE_SIDE
        or height < MIN_SOURCE_IMAGE_SIDE
        or width > MAX_SOURCE_IMAGE_SIDE
        or height > MAX_SOURCE_IMAGE_SIDE
    ):
        raise HTTPException(400, f"{label} dimensions must be between 240 and 8000 pixels")
    aspect = width / height
    if aspect < 1 / 8 or aspect > 8:
        raise HTTPException(400, f"{label} aspect ratio must be between 1:8 and 8:1")

    canonical_mime = "image/jpeg" if detected_mime == "image/jpeg" else mime_type
    canonical_b64 = base64.b64encode(image_bytes).decode("ascii")
    return {
        "data_url": f"data:{canonical_mime};base64,{canonical_b64}",
        "mime_type": canonical_mime,
        "extension": ALLOWED_IMAGE_MIME_TYPES[canonical_mime],
        "bytes": image_bytes,
        "width": width,
        "height": height,
    }


def _validated_bbox(bbox: list[int] | None, image: dict | None) -> list[int] | None:
    if bbox is None:
        return None
    if image is None:
        raise HTTPException(400, "bbox can only be used with an uploaded building image")
    if len(bbox) != 4:
        raise HTTPException(400, "bbox must contain [x1, y1, x2, y2]")
    try:
        x1, y1, x2, y2 = [int(value) for value in bbox]
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "bbox must contain integer pixel coordinates") from exc
    x1 = max(0, min(image["width"], x1))
    x2 = max(0, min(image["width"], x2))
    y1 = max(0, min(image["height"], y1))
    y2 = max(0, min(image["height"], y2))
    if x2 <= x1 or y2 <= y1:
        raise HTTPException(400, "bbox must cover a visible image area")
    return [x1, y1, x2, y2]


def _detect_image_type(image_bytes: bytes) -> str | None:
    if image_bytes.startswith(b"\xff\xd8"):
        return "jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image_bytes.startswith(b"BM"):
        return "bmp"
    if len(image_bytes) >= 12 and image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "webp"
    return None


def _image_dimensions(image_bytes: bytes, image_type: str) -> tuple[int, int]:
    if image_type == "png":
        if len(image_bytes) < 24 or image_bytes[:8] != b"\x89PNG\r\n\x1a\n":
            raise HTTPException(400, "Invalid PNG image")
        width, height = struct.unpack(">II", image_bytes[16:24])
        return width, height
    if image_type == "jpeg":
        return _jpeg_dimensions(image_bytes)
    if image_type == "bmp":
        if len(image_bytes) < 26:
            raise HTTPException(400, "Invalid BMP image")
        width = struct.unpack("<I", image_bytes[18:22])[0]
        height = abs(struct.unpack("<i", image_bytes[22:26])[0])
        return width, height
    if image_type == "webp":
        return _webp_dimensions(image_bytes)
    raise HTTPException(400, "Unsupported image type")


def _jpeg_dimensions(image_bytes: bytes) -> tuple[int, int]:
    if image_bytes[:2] != b"\xff\xd8":
        raise HTTPException(400, "Invalid JPEG image")
    index = 2
    while index + 1 < len(image_bytes):
        if image_bytes[index] != 0xFF:
            index += 1
            continue
        marker = image_bytes[index + 1]
        index += 2
        while marker == 0xFF:
            if index >= len(image_bytes):
                raise HTTPException(400, "Could not read JPEG dimensions")
            marker = image_bytes[index]
            index += 1
        if marker in {0xD8, 0xD9, 0x01} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(image_bytes):
            break
        segment_length = struct.unpack(">H", image_bytes[index : index + 2])[0]
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if index + 7 > len(image_bytes):
                break
            height, width = struct.unpack(">HH", image_bytes[index + 3 : index + 7])
            return width, height
        index += segment_length
    raise HTTPException(400, "Could not read JPEG dimensions")


def _webp_dimensions(image_bytes: bytes) -> tuple[int, int]:
    if len(image_bytes) < 30 or image_bytes[:4] != b"RIFF" or image_bytes[8:12] != b"WEBP":
        raise HTTPException(400, "Invalid WEBP image")
    chunk = image_bytes[12:16]
    if chunk == b"VP8 ":
        if len(image_bytes) < 30:
            raise HTTPException(400, "Invalid WEBP image")
        width = struct.unpack("<H", image_bytes[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", image_bytes[28:30])[0] & 0x3FFF
        return width, height
    if chunk == b"VP8L":
        if len(image_bytes) < 25:
            raise HTTPException(400, "Invalid WEBP image")
        bits = struct.unpack("<I", image_bytes[21:25])[0]
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    if chunk == b"VP8X":
        if len(image_bytes) < 30:
            raise HTTPException(400, "Invalid WEBP image")
        width = int.from_bytes(image_bytes[24:27], "little") + 1
        height = int.from_bytes(image_bytes[27:30], "little") + 1
        return width, height
    raise HTTPException(400, "Could not read WEBP dimensions")


@router.post("/capture")
def capture_image(payload: CaptureRequest):
    try:
        b64 = payload.image.split(",", 1)[-1]
        output_path = CAPTURE_PATH
        output_path.write_bytes(base64.b64decode(b64))
        return {"saved": str(output_path), "status": "ok"}
    except Exception as exc:
        raise HTTPException(400, f"Failed to save capture: {exc}") from exc
