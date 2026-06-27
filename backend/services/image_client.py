from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request

from .render_styles import render_style_prompt
from .settings import dashscope_api_key, dashscope_image_model, image_provider

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
DASHSCOPE_TEXT_TO_IMAGE_PATH = "/services/aigc/text2image/image-synthesis"
DASHSCOPE_MULTIMODAL_PATH = "/services/aigc/multimodal-generation/generation"


class ImageGenerationUnavailable(RuntimeError):
    pass


def image_provider_status() -> dict:
    provider = image_provider()
    return {
        "provider": provider,
        "configured": provider == "dashscope" and bool(dashscope_api_key()),
        "model": dashscope_image_model() if provider == "dashscope" else None,
    }


def generate_facade_render(
    scheme: dict,
    view_type: str,
    style: str,
    *,
    source_type: str = "text_prompt",
    model_image: str | None = None,
    user_image: str | None = None,
    bbox: list[int] | None = None,
) -> dict:
    if image_provider() != "dashscope":
        raise ImageGenerationUnavailable("IMAGE_PROVIDER is not dashscope")
    key = dashscope_api_key()
    if not key:
        raise ImageGenerationUnavailable("DASHSCOPE_API_KEY is not configured")

    prompt = _build_prompt(scheme, view_type, style, source_type=source_type, has_user_image=bool(user_image))
    if source_type in {"model_capture", "user_image"}:
        result = _submit_multimodal_task(
            key,
            prompt,
            source_type=source_type,
            model_image=model_image,
            user_image=user_image,
            bbox=bbox,
        )
        image_url = _extract_image_url(result)
        return {
            "status": "completed",
            "image_url": image_url,
            "provider": "dashscope",
            "model": _image_edit_model(),
            "task_id": result.get("request_id"),
            "prompt": prompt,
            "source_type": source_type,
        }

    task = _submit_text_to_image_task(key, prompt)
    task_id = task.get("output", {}).get("task_id")
    if not task_id:
        raise ImageGenerationUnavailable(f"DashScope did not return task_id: {task}")
    result = _poll_task(key, task_id)
    image_url = _extract_image_url(result)
    return {
        "status": "completed",
        "image_url": image_url,
        "provider": "dashscope",
        "model": dashscope_image_model(),
        "task_id": task_id,
        "prompt": prompt,
        "source_type": source_type,
    }


def _image_edit_model() -> str:
    configured = dashscope_image_model()
    if configured.startswith("wanx"):
        return "wan2.7-image"
    return configured


def _submit_multimodal_task(
    api_key: str,
    prompt: str,
    *,
    source_type: str,
    model_image: str | None,
    user_image: str | None,
    bbox: list[int] | None,
) -> dict:
    content: list[dict] = []
    bbox_list: list[list[list[int]]] | None = None
    if source_type == "model_capture":
        if not model_image:
            raise ImageGenerationUnavailable("3D model capture is required for model-capture rendering")
        content.append({"image": model_image})
        content.append({"text": prompt[:5000]})
    elif source_type == "user_image":
        if not user_image or not model_image:
            raise ImageGenerationUnavailable("Both uploaded building image and 3D model capture are required")
        content.append({"image": model_image})
        content.append({"image": user_image})
        content.append({"text": prompt[:5000]})
        if bbox:
            bbox_list = [[], [bbox]]
    else:
        raise ImageGenerationUnavailable(f"Unsupported render source_type: {source_type}")

    parameters: dict = {"size": "2K", "n": 1, "watermark": False}
    if bbox_list:
        parameters["bbox_list"] = bbox_list

    payload = {
        "model": _image_edit_model(),
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ]
        },
        "parameters": parameters,
    }
    request = urllib.request.Request(
        f"{DASHSCOPE_BASE_URL}{DASHSCOPE_MULTIMODAL_PATH}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ImageGenerationUnavailable(_format_dashscope_error("image editing", exc.code, body)) from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise ImageGenerationUnavailable(f"DashScope image edit failed: {exc}") from exc


def _submit_text_to_image_task(api_key: str, prompt: str) -> dict:
    payload = {
        "model": dashscope_image_model(),
        "input": {
            "prompt": prompt[:2100],
            "negative_prompt": (
                "low resolution, low quality, distorted geometry, extra text, watermark, "
                "messy facade, unrealistic structure"
            ),
        },
        "parameters": {
            "size": "1024*1024",
            "n": 1,
            "prompt_extend": True,
            "watermark": False,
        },
    }
    request = urllib.request.Request(
        f"{DASHSCOPE_BASE_URL}{DASHSCOPE_TEXT_TO_IMAGE_PATH}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ImageGenerationUnavailable(_format_dashscope_error("submit", exc.code, body)) from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise ImageGenerationUnavailable(f"DashScope submit failed: {exc}") from exc


def _poll_task(api_key: str, task_id: str) -> dict:
    last_response: dict = {}
    for _ in range(36):
        request = urllib.request.Request(
            f"{DASHSCOPE_BASE_URL}/tasks/{task_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                last_response = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ImageGenerationUnavailable(_format_dashscope_error("poll", exc.code, body)) from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            raise ImageGenerationUnavailable(f"DashScope poll failed: {exc}") from exc
        status = last_response.get("output", {}).get("task_status")
        if status == "SUCCEEDED":
            return last_response
        if status in {"FAILED", "CANCELED", "UNKNOWN"}:
            raise ImageGenerationUnavailable(f"DashScope task {status}: {last_response}")
        time.sleep(2)
    raise ImageGenerationUnavailable(f"DashScope task timed out: {last_response}")


def _extract_image_url(result: dict) -> str:
    output = result.get("output", {})
    results = output.get("results") or []
    if results and results[0].get("url"):
        return results[0]["url"]
    choices = output.get("choices") or []
    for choice in choices:
        content = choice.get("message", {}).get("content", [])
        for item in content:
            if item.get("image"):
                return item["image"]
    raise ImageGenerationUnavailable(f"DashScope result did not contain image url: {result}")


def _format_dashscope_error(action: str, status_code: int, body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return f"DashScope {action} failed (HTTP {status_code})."

    code = payload.get("code", "UnknownError")
    message = payload.get("message", "")
    if code == "InvalidApiKey":
        return "DashScope API Key is invalid. Please check the key file."
    if code in {"Arrearage", "AccessDenied", "Forbidden"}:
        return "DashScope image service is unavailable. Please check service activation, balance, and API key permissions."
    if code == "Throttling":
        return "DashScope requests are being throttled. Please wait and try again."
    if code == "InvalidParameter":
        return f"DashScope rejected the image request parameters: {message or 'please check model and image settings.'}"
    return f"DashScope {action} failed ({code}): {message or f'HTTP {status_code}'}"


def _build_prompt(
    scheme: dict,
    view_type: str,
    style: str,
    *,
    source_type: str = "text_prompt",
    has_user_image: bool = False,
) -> str:
    params = scheme.get("params", {})
    perf = scheme.get("performance", {})
    shading = {
        1: "horizontal exterior sunshade louvers",
        2: "vertical exterior sunshade fins",
        3: "mixed horizontal and vertical exterior shading",
    }.get(params.get("shading_type"), "exterior shading system")
    material = {1: "concrete", 2: "aluminium", 3: "dark steel"}.get(params.get("material"), "aluminium")
    view = _view_prompt(view_type)
    spatial_rules = _view_spatial_rules(view_type)
    base = (
        f"{render_style_prompt(style)}, {view}, contemporary office building facade, {shading}, "
        f"{material} shading elements, window wall ratio {params.get('wwr')} percent, "
        f"louver spacing {params.get('spacing')} mm, blade depth {params.get('blade_depth')} mm, "
        f"high-performance glass, green building design, clear daylight, professional architectural visualization, "
        f"performance concept LCCE {perf.get('lcce')}, LCC {perf.get('lcc')}, sDA {perf.get('sda')}, "
        "realistic materials, no text, no watermark, no people in foreground. "
        f"{spatial_rules}"
    )
    if source_type == "model_capture":
        return (
            f"{base}. Use the provided 3D model screenshot as the composition, camera angle, and facade geometry reference. "
            "Preserve the louver count, orientation, spacing rhythm, projection depth, wall opening proportions, and view direction. "
            "Do not swap the indoor and outdoor sides. The exterior shading devices must stay outside the glass plane and outside the room. "
            "Only enhance materials, lighting, shadows, glazing realism, and architectural atmosphere."
        )
    if source_type == "user_image" and has_user_image:
        return (
            f"{base}. There are two input images: image 1 is the current facade shading scheme from the 3D model, "
            "image 2 is the user's building photograph and must remain the full output scene. Apply the shading system style, "
            "louver direction, material, rhythm, and depth from image 1 onto the facade area of image 2. Preserve image 2's "
            "building massing, perspective, windows, lighting, surroundings, sky, and full image crop. Do not output only the selected box; "
            "return the complete architectural rendering with the edited facade integrated naturally. Keep the user's building camera viewpoint, "
            "and place the shading system on the exterior side of the facade rather than behind the glass or inside the rooms."
        )
    return base


def _view_prompt(view_type: str) -> str:
    return {
        "indoor": (
            "interior eye-level office view from inside the room, looking outward through a clear glass facade toward daylight, "
            "with a modest office interior foreground such as floor slab, ceiling, side wall, desks or seating kept subtle"
        ),
        "outdoor": (
            "street-level exterior perspective from outside the building, looking at the facade and the exterior sunshade layer, "
            "urban daylight context, facade depth clearly readable"
        ),
        "axonometric": (
            "clean architectural axonometric view showing the room volume, glass wall, and exterior sunshade system as layered construction, "
            "slightly elevated camera, diagrammatic spatial clarity"
        ),
        "elevation": (
            "orthographic front elevation of the facade, no perspective distortion, flat and centered composition, "
            "sunshade rhythm and spacing shown accurately across the full wall"
        ),
    }.get(view_type, "architectural exterior perspective")


def _view_spatial_rules(view_type: str) -> str:
    common = (
        "The facade assembly order is fixed: room interior, glass curtain wall, then exterior sunshade elements projecting outward. "
        "Glass remains a continuous plane at the facade opening; louvers or fins are outside the glass and never inside the room."
    )
    return {
        "indoor": (
            f"{common} For this indoor view, the camera is inside the office. The correct depth order from camera to outside is: "
            "office interior foreground, interior side of glass, transparent glass pane, exterior vertical or horizontal shading devices, outdoor daylight. "
            "The glass should be visually between the viewer and the exterior shading devices; the shading devices may be seen through or beyond the glass, "
            "not as interior mullions. Do not turn this into an exterior facade close-up or an outside elevation view. "
            "Show subtle interior depth and daylight entering the room."
        ),
        "outdoor": (
            f"{common} For this exterior view, the sunshade devices are the foremost facade layer facing the viewer, "
            "with glass and room interior visible behind them only through gaps or reflections. Do not place a second glass curtain wall in front of the shading devices."
        ),
        "axonometric": (
            f"{common} For the axonometric view, separate the layers legibly: room box behind, glass plane at the wall, "
            "and sunshade array projecting outward from the exterior side. Keep the construction order unambiguous."
        ),
        "elevation": (
            f"{common} For the elevation view, keep the facade flat, frontal, and orthographic: shading devices overlay the glass from the exterior side, "
            "with accurate spacing and no perspective exaggeration."
        ),
    }.get(view_type, common)
