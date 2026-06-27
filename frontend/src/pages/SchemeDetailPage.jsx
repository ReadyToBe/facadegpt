import { Activity, Camera, Crop, Download, ImagePlus, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import ThreeDViewer from "../components/ThreeDViewer.jsx";
import RadarChart from "../components/RadarChart.jsx";
import { api, assetUrl } from "../api/client";
import { SCHEME_METRICS, metricRank, schemePerformanceSummary } from "../utils/schemePresentation.js";

const MAX_IMAGE_BYTES = 20 * 1024 * 1024;
const OFFICIAL_MIN_SIDE = 240;
const OFFICIAL_MAX_SIDE = 8000;
const COMPRESSED_MAX_SIDE = 2048;
const VALID_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/bmp", "image/webp"]);

const labelMap = {
  key_conflict: "关键矛盾",
  priority: "推荐优先考虑",
  avoid: "需要避免",
  next_step: "下一步尝试",
  discussion: "深化思考",
};

const renderModeLabels = {
  model_capture: "3D截图渲染",
  user_image: "建筑图像渲染",
  text_prompt: "早期文字渲染",
};

export default function SchemeDetailPage() {
  const { id } = useParams();
  const [scheme, setScheme] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [rendered, setRendered] = useState("");
  const [remoteRender, setRemoteRender] = useState(null);
  const [renderHistory, setRenderHistory] = useState([]);
  const [views, setViews] = useState([]);
  const [styles, setStyles] = useState([]);
  const [viewType, setViewType] = useState("outdoor");
  const [style, setStyle] = useState("photoreal_day");
  const [renderMode, setRenderMode] = useState("model_capture");
  const [sourceImage, setSourceImage] = useState(null);
  const [selection, setSelection] = useState(null);
  const [dragBox, setDragBox] = useState(null);
  const [uploadError, setUploadError] = useState("");
  const [rendering, setRendering] = useState(false);
  const [renderError, setRenderError] = useState("");
  const viewerRef = useRef(null);
  const imageStageRef = useRef(null);

  useEffect(() => {
    let isMounted = true;
    setScheme(null);
    setFeedback(null);
    setRemoteRender(null);
    setRenderHistory([]);
    setRendered("");
    setSelection(null);

    api.getScheme(id).then((data) => {
      if (isMounted) setScheme(data.scheme);
    });
    api.getFeedback(id).then((data) => {
      if (isMounted) setFeedback(data);
    }).catch(() => {
      if (isMounted) setFeedback(null);
    });
    api.getViews().then((data) => {
      if (isMounted) setViews(data.views || []);
    });
    api.getRenderStyles().then((data) => {
      if (!isMounted) return;
      setStyles(data.styles || []);
      if (data.styles?.[0]?.id) setStyle(data.styles[0].id);
    });
    api.getSchemeRenders(id).then((data) => {
      if (isMounted) setRenderHistory(data.renders || []);
    }).catch(() => {
      if (isMounted) setRenderHistory([]);
    });

    return () => {
      isMounted = false;
    };
  }, [id]);

  function exportShot() {
    const url = viewerRef.current?.captureView?.(viewType) || viewerRef.current?.capture?.();
    if (url) setRendered(url);
  }

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    setUploadError("");
    setSourceImage(null);
    setSelection(null);
    setDragBox(null);
    if (!file) return;
    try {
      const compressed = await compressUpload(file);
      setSourceImage(compressed);
    } catch (err) {
      setUploadError(err.message);
    }
  }

  async function generateRender() {
    setRendering(true);
    setRenderError("");
    setRemoteRender(null);
    try {
      const modelImage = viewerRef.current?.captureView?.(viewType) || viewerRef.current?.capture?.();
      if (!modelImage) throw new Error("无法获取当前 3D 视图截图。");
      if (renderMode === "user_image" && !sourceImage) throw new Error("请先上传建筑图像。");

      const payload = {
        view_type: viewType,
        style,
        source_type: renderMode,
        model_image: modelImage,
      };
      if (renderMode === "user_image") {
        payload.user_image = sourceImage.dataUrl;
        if (selection) payload.bbox = selectionToBbox(selection);
      }

      const result = await api.renderScheme(id, payload);
      if (result.status === "completed" && result.image_url) {
        setRemoteRender(result);
        setRenderHistory((current) => [renderResultToHistory(result, viewType), ...current]);
      } else {
        setRenderError(result.error || "图像生成暂时不可用，可先导出当前 3D 视图。");
      }
    } catch (err) {
      setRenderError(err.message);
    } finally {
      setRendering(false);
    }
  }

  function beginSelection(event) {
    if (!sourceImage || !imageStageRef.current) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = pointFromEvent(event, imageStageRef.current, sourceImage);
    setSelection(null);
    setDragBox({ start: point, current: point });
  }

  function updateSelection(event) {
    if (!dragBox || !sourceImage || !imageStageRef.current) return;
    const point = pointFromEvent(event, imageStageRef.current, sourceImage);
    setDragBox({ ...dragBox, current: point });
  }

  function finishSelection(event) {
    if (!dragBox) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    const nextSelection = boxFromDrag(dragBox.start, dragBox.current);
    setDragBox(null);
    if (nextSelection.width >= 10 && nextSelection.height >= 10) {
      setSelection(nextSelection);
    }
  }

  if (!scheme) return <p>加载方案中...</p>;

  const activeSelection = dragBox ? boxFromDrag(dragBox.start, dragBox.current) : selection;
  const groupedHistory = groupRenderHistory(renderHistory);

  return (
    <section className="detail">
      <div className="detail-head">
        <div>
          <p className="eyebrow">方案 {scheme.scheme_label} · {scheme.strategy}</p>
          <h1>{scheme.scheme_name}</h1>
        </div>
        <button className="secondary" onClick={() => window.history.back()}>返回</button>
      </div>

      <div className="viewer-band">
        <ThreeDViewer ref={viewerRef} params={scheme.params} activeView={viewType} onViewChange={setViewType} />
      </div>

      <div className="detail-grid">
        <div className="panel balance-panel">
          <div className="section-title"><Activity size={18} /> 三目标平衡</div>
          <p className="balance-note">该图只展示当前方案，三个方向均已归一化为“越大越优”。</p>
          <RadarChart schemes={[scheme]} />
        </div>

        <div className="panel render-panel">
          <div className="section-title"><ImagePlus size={18} /> 图像渲染</div>
          <div className="render-mode-tabs" role="tablist" aria-label="渲染来源">
            <button className={renderMode === "model_capture" ? "active" : ""} onClick={() => setRenderMode("model_capture")}>
              <Camera size={16} /> 3D截图
            </button>
            <button className={renderMode === "user_image" ? "active" : ""} onClick={() => setRenderMode("user_image")}>
              <Upload size={16} /> 建筑图像
            </button>
          </div>

          <label className="field-label">渲染视角</label>
          <select value={viewType} onChange={(event) => setViewType(event.target.value)}>
            {views.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
          </select>
          <label className="field-label">渲染风格</label>
          <select value={style} onChange={(event) => setStyle(event.target.value)}>
            {styles.map((item) => <option value={item.id} key={item.id}>{item.name} · {item.description}</option>)}
          </select>

          {renderMode === "user_image" && (
            <div className="upload-block">
              <label className="field-label" htmlFor="building-source">参考建筑图像</label>
              <input
                id="building-source"
                className="upload-input"
                type="file"
                accept="image/jpeg,image/png,image/bmp,image/webp"
                onChange={handleUpload}
              />
              <label className="upload-control" htmlFor="building-source">
                <Upload size={18} /> 上传图像
              </label>
              {sourceImage && (
                <>
                  <div
                    className="image-selection-stage"
                    ref={imageStageRef}
                    onPointerDown={beginSelection}
                    onPointerMove={updateSelection}
                    onPointerUp={finishSelection}
                  >
                    <img src={sourceImage.dataUrl} alt="用户上传的建筑图像" draggable="false" />
                    {activeSelection && <span className="selection-box" style={selectionStyle(activeSelection, sourceImage)} />}
                  </div>
                  <div className="selection-actions">
                    <span>{sourceImage.width}×{sourceImage.height}px · {formatBytes(sourceImage.size)}</span>
                    <button className="secondary" onClick={() => setSelection(null)} disabled={!selection}>
                      <Crop size={16} /> 清除框选
                    </button>
                  </div>
                </>
              )}
              {uploadError && <p className="error">{uploadError}</p>}
            </div>
          )}

          <button className="primary wide" onClick={generateRender} disabled={rendering}>
            <Camera size={18} /> {rendering ? "生成中..." : "生成效果图"}
          </button>
          {remoteRender?.image_url && <img className="render-preview" src={assetUrl(remoteRender.image_url)} alt="通义万相生成的立面效果图" />}
          {renderError && <p className="error">{renderError}</p>}
          {remoteRender?.prompt && <details className="prompt-details"><summary>查看本次生成 prompt</summary><p>{remoteRender.prompt}</p></details>}

          <RenderHistory groups={groupedHistory} />
        </div>

        <div className="panel">
          <div className="section-title"><Download size={18} /> 3D 截图导出</div>
          <button className="secondary wide" onClick={exportShot}><Download size={18} /> 导出当前视角</button>
          {rendered && <img className="render-preview" src={rendered} alt="当前 3D 视图截图" />}
        </div>

        <div className="panel">
          <div className="section-title">性能指标</div>
          <div className="metric-list">
            <Metric
              label={SCHEME_METRICS.lcce.label}
              rank={metricRank(scheme.performance, "lcce")}
              unit={SCHEME_METRICS.lcce.unit}
              value={scheme.performance.lcce}
            />
            <Metric
              label={SCHEME_METRICS.lcc.label}
              rank={metricRank(scheme.performance, "lcc")}
              unit={SCHEME_METRICS.lcc.unit}
              value={scheme.performance.lcc}
            />
            <Metric
              label={SCHEME_METRICS.sda.label}
              rank={metricRank(scheme.performance, "sda")}
              unit={SCHEME_METRICS.sda.unit}
              value={scheme.performance.sda}
            />
          </div>
          <p className="scheme-summary">{schemePerformanceSummary(scheme)}</p>
          <p>{scheme.description}</p>
          <p className="risk">{scheme.risk_note}</p>
        </div>

        <div className="panel wide-panel">
          <div className="section-title">设计评估</div>
          {feedback && Object.entries(feedback).map(([key, value]) => <p key={key}><strong>{labelMap[key]}：</strong>{value}</p>)}
        </div>
      </div>
    </section>
  );
}

function RenderHistory({ groups }) {
  const visibleGroups = Object.entries(renderModeLabels)
    .map(([sourceType, title]) => ({ sourceType, title, items: groups[sourceType] || [] }))
    .filter((group) => group.items.length);

  if (!visibleGroups.length) return null;

  return (
    <div className="render-history">
      <div className="section-title">渲染记录</div>
      {visibleGroups.map((group) => (
        <div className="render-history-group" key={group.sourceType}>
          <div className="history-count">{group.title} · {group.items.length}</div>
          <div className="render-history-grid">
            {group.items.map((item) => (
              <div className="render-history-card" key={item.id}>
                {item.image_url ? (
                  <img src={assetUrl(item.image_url)} alt={`${group.title}生成图`} />
                ) : (
                  <div className="render-history-empty">生成失败</div>
                )}
                <span>{item.view_type || "视角"} · {formatDate(item.created_at)}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function Metric({ label, rank, unit, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}<small>{unit}</small></strong>
      <em>{rank}</em>
    </div>
  );
}

function renderResultToHistory(result, viewType) {
  return {
    id: result.render_id,
    scheme_id: result.scheme_id,
    view_type: viewType,
    image_url: result.image_url,
    source_type: result.source_type || "model_capture",
    source_image_url: result.source_image_url,
    status: result.status,
    provider: result.provider,
    prompt: result.prompt,
    created_at: new Date().toISOString(),
  };
}

function groupRenderHistory(items) {
  return items.reduce((groups, item) => {
    const key = item.source_type || "text_prompt";
    groups[key] = groups[key] || [];
    groups[key].push(item);
    return groups;
  }, {});
}

async function compressUpload(file) {
  if (!VALID_IMAGE_TYPES.has(file.type)) {
    throw new Error("仅支持 JPEG、PNG、BMP 或 WEBP 图像。");
  }
  const image = await loadImage(file);
  const originalWidth = image.naturalWidth;
  const originalHeight = image.naturalHeight;
  validateOfficialImageShape(originalWidth, originalHeight);

  const scale = Math.min(1, COMPRESSED_MAX_SIDE / Math.max(originalWidth, originalHeight));
  const width = Math.round(originalWidth * scale);
  const height = Math.round(originalHeight * scale);
  validateOfficialImageShape(width, height);

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, width, height);
  context.drawImage(image, 0, 0, width, height);

  let quality = 0.88;
  let dataUrl = canvas.toDataURL("image/jpeg", quality);
  while (dataUrlBytes(dataUrl) > MAX_IMAGE_BYTES && quality > 0.55) {
    quality -= 0.08;
    dataUrl = canvas.toDataURL("image/jpeg", quality);
  }
  const size = dataUrlBytes(dataUrl);
  if (size > MAX_IMAGE_BYTES) {
    throw new Error("压缩后仍超过 20MB，请换一张更小的图像。");
  }
  return { dataUrl, width, height, name: file.name, size };
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("无法读取这张图像。"));
    };
    image.src = url;
  });
}

function validateOfficialImageShape(width, height) {
  if (
    width < OFFICIAL_MIN_SIDE
    || height < OFFICIAL_MIN_SIDE
    || width > OFFICIAL_MAX_SIDE
    || height > OFFICIAL_MAX_SIDE
  ) {
    throw new Error("图像宽高需要在 240 到 8000 像素之间。");
  }
  const aspect = width / height;
  if (aspect < 1 / 8 || aspect > 8) {
    throw new Error("图像宽高比需要在 1:8 到 8:1 之间。");
  }
}

function pointFromEvent(event, element, sourceImage) {
  const rect = element.getBoundingClientRect();
  const x = ((event.clientX - rect.left) / rect.width) * sourceImage.width;
  const y = ((event.clientY - rect.top) / rect.height) * sourceImage.height;
  return {
    x: clamp(x, 0, sourceImage.width),
    y: clamp(y, 0, sourceImage.height),
  };
}

function boxFromDrag(start, current) {
  const x = Math.min(start.x, current.x);
  const y = Math.min(start.y, current.y);
  return {
    x,
    y,
    width: Math.abs(current.x - start.x),
    height: Math.abs(current.y - start.y),
  };
}

function selectionToBbox(box) {
  return [
    Math.round(box.x),
    Math.round(box.y),
    Math.round(box.x + box.width),
    Math.round(box.y + box.height),
  ];
}

function selectionStyle(box, sourceImage) {
  return {
    left: `${(box.x / sourceImage.width) * 100}%`,
    top: `${(box.y / sourceImage.height) * 100}%`,
    width: `${(box.width / sourceImage.width) * 100}%`,
    height: `${(box.height / sourceImage.height) * 100}%`,
  };
}

function dataUrlBytes(dataUrl) {
  const base64 = dataUrl.split(",", 2)[1] || "";
  return Math.floor((base64.length * 3) / 4);
}

function formatBytes(bytes) {
  if (!bytes) return "0MB";
  return `${(bytes / 1024 / 1024).toFixed(2)}MB`;
}

function formatDate(value) {
  if (!value) return "刚刚";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
