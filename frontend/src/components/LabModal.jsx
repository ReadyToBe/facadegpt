import { Activity, FlaskConical, LoaderCircle, RefreshCw, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import ThreeDViewer from "./ThreeDViewer.jsx";
import { api } from "../api/client";

const DEFAULT_PARAMS = {
  horizontal_depth: 300,
  shading_type: 2,
  material: 2,
  spacing: 500,
  h_rotation: 0,
  v_rotation: -30,
  blade_depth: 200,
  window_distance: 200,
  wwr: 50,
  glass_type: 2,
};

const PARAM_DEFS = [
  { key: "horizontal_depth", label: "挑檐深度", min: 100, max: 600, step: 100, unit: "mm" },
  {
    key: "shading_type",
    label: "遮阳形式",
    options: [
      { value: 1, label: "水平" },
      { value: 2, label: "垂直" },
      { value: 3, label: "混合" },
    ],
  },
  {
    key: "material",
    label: "构件材料",
    options: [
      { value: 1, label: "混凝土" },
      { value: 2, label: "铝材" },
      { value: 3, label: "钢材" },
    ],
  },
  { key: "spacing", label: "构件间距", min: 100, max: 900, step: 100, unit: "mm" },
  { key: "h_rotation", label: "水平旋转", min: 0, max: 90, step: 10, unit: "deg" },
  { key: "v_rotation", label: "垂直旋转", min: -90, max: 90, step: 10, unit: "deg" },
  { key: "blade_depth", label: "遮阳深度", min: 100, max: 600, step: 100, unit: "mm" },
  { key: "window_distance", label: "离窗距离", min: 100, max: 600, step: 100, unit: "mm" },
  { key: "wwr", label: "窗墙比", min: 20, max: 80, step: 10, unit: "%" },
  {
    key: "glass_type",
    label: "玻璃类型",
    options: [
      { value: 1, label: "单层Low-E" },
      { value: 2, label: "双层Low-E" },
      { value: 3, label: "双层中空" },
      { value: 4, label: "三层中空" },
    ],
  },
];

const METRICS = [
  { key: "lcce", label: "LCCE", unit: "kgCO2/m2" },
  { key: "lcc", label: "LCC", unit: "yuan/m2" },
  { key: "sda", label: "sDA", unit: "%" },
];

export default function LabModal({ onClose }) {
  const [draftParams, setDraftParams] = useState(DEFAULT_PARAMS);
  const [modelParams, setModelParams] = useState(DEFAULT_PARAMS);
  const [performance, setPerformance] = useState(null);
  const [evaluations, setEvaluations] = useState(null);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const hasDraftChanges = useMemo(() => !sameParams(draftParams, modelParams), [draftParams, modelParams]);

  useEffect(() => {
    let cancelled = false;
    async function loadLab() {
      setLoading(true);
      setError("");
      try {
        const result = await api.getLab();
        if (cancelled) return;
        const nextParams = normalizeParams(result.params || DEFAULT_PARAMS);
        setDraftParams(nextParams);
        setModelParams(nextParams);
        setPerformance(result.performance || null);
        setEvaluations(result.evaluations || null);
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadLab();
    return () => { cancelled = true; };
  }, []);

  function setParam(key, value) {
    const def = PARAM_DEFS.find((item) => item.key === key);
    const nextValue = normalizeValue(value, def);
    setNotice("");
    setDraftParams((current) => ({ ...current, [key]: nextValue }));
  }

  function updateModel() {
    if (!hasDraftChanges) return;
    setModelParams(normalizeParams(draftParams));
    setPerformance(null);
    setEvaluations(null);
  }

  async function evaluateCurrent() {
    if (hasDraftChanges || evaluating) return;
    setEvaluating(true);
    setError("");
    try {
      const result = await api.evaluateLab(modelParams);
      const nextParams = normalizeParams(result.params || modelParams);
      setDraftParams(nextParams);
      setModelParams(nextParams);
      setPerformance(result.performance || null);
      setEvaluations(result.evaluations || null);
    } catch (err) {
      setError(err.message);
    } finally {
      setEvaluating(false);
    }
  }

  return (
    <div className="lab-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="lab-modal" aria-label="实验室">
        <header className="lab-head">
          <div>
            <p>PERSONAL LAB</p>
            <h2><FlaskConical size={22} /> 实验室</h2>
            <p className="lab-guide">这里是遮阳性能实验室，你可以通过调节参数，查看任意遮阳方案的性能评价。</p>
          </div>
          <button className="tool-button" onClick={onClose} title="关闭" aria-label="关闭"><X size={18} /></button>
        </header>

        {loading ? (
          <div className="lab-loading"><LoaderCircle className="spin" size={18} /> 载入实验室...</div>
        ) : (
          <div className="lab-body">
            <div className="lab-model-panel">
              <div className="lab-panel-head">
                <span><Activity size={17} /> 当前方案</span>
                {hasDraftChanges && <em>待更新</em>}
              </div>
              <div className="lab-viewer"><ThreeDViewer params={modelParams} /></div>
              <div className="lab-actions">
                <button className="secondary" onClick={updateModel} disabled={!hasDraftChanges}>
                  <RefreshCw size={17} /> 更新方案3D模型
                </button>
                <button className="primary" onClick={evaluateCurrent} disabled={evaluating || hasDraftChanges}>
                  {evaluating ? <LoaderCircle className="spin" size={17} /> : <Activity size={17} />}
                  {evaluating ? "计算中" : "查看当前方案的性能数值"}
                </button>
              </div>
              {error && <div className="workspace-error">{error}</div>}
            </div>

            <div className="lab-controls-panel">
              <div className="lab-panel-head"><span><SlidersHorizontal size={17} /> 参数</span></div>
              <div className="lab-param-list">
                {PARAM_DEFS.map((def) => (
                  <ParamControl
                    def={def}
                    key={def.key}
                    onUnavailable={() => setNotice("混合遮阳方案功能待开发")}
                    value={draftParams[def.key]}
                    onChange={(value) => setParam(def.key, value)}
                  />
                ))}
              </div>
              {notice && <div className="workspace-notice lab-notice">{notice}</div>}

              <div className="lab-results">
                <div className={`lab-overall grade-${evaluations?.overall?.grade || "none"}`}>
                  <span>综合评价</span>
                  <strong>{evaluations?.overall?.grade || "--"}</strong>
                </div>
                <div className="lab-metric-grid">
                  {METRICS.map((metric) => (
                    <MetricResult
                      grade={evaluations?.metrics?.[metric.key]?.grade}
                      key={metric.key}
                      label={metric.label}
                      unit={metric.unit}
                      value={performance?.[metric.key]}
                    />
                  ))}
                </div>
                <p className="lab-basis">标准：代际解集图示范围三分位</p>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function ParamControl({ def, value, onChange, onUnavailable }) {
  if (def.options) {
    return (
      <div className="lab-param-row">
        <span>{def.label}</span>
        <div className="lab-segmented">
          {def.options.map((option) => (
            <button
              className={Number(value) === option.value ? "active" : ""}
              key={option.value}
              onClick={() => {
                if (def.key === "shading_type" && option.value === 3) {
                  onUnavailable();
                  return;
                }
                onChange(option.value);
              }}
              title={def.key === "shading_type" && option.value === 3 ? "功能待开发" : undefined}
              type="button"
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <label className="lab-param-row">
      <span>{def.label}</span>
      <div className="lab-slider-control">
        <input
          type="range"
          min={def.min}
          max={def.max}
          step={def.step}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
        <input
          type="number"
          min={def.min}
          max={def.max}
          step={def.step}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
        <small>{def.unit}</small>
      </div>
    </label>
  );
}

function MetricResult({ label, value, unit, grade }) {
  return (
    <div className={`lab-metric grade-${grade || "none"}`}>
      <span>{label}</span>
      <strong>{value == null ? "--" : Number(value).toFixed(2)}</strong>
      <em>{grade || "--"}</em>
      <small>{unit}</small>
    </div>
  );
}

function normalizeParams(params) {
  return PARAM_DEFS.reduce((result, def) => {
    result[def.key] = normalizeValue(params?.[def.key] ?? DEFAULT_PARAMS[def.key], def);
    return result;
  }, {});
}

function normalizeValue(rawValue, def) {
  if (def.options) {
    const value = Number(rawValue);
    return def.options.some((option) => option.value === value) ? value : def.options[0].value;
  }
  const numeric = Number(rawValue);
  const fallback = DEFAULT_PARAMS[def.key];
  const bounded = clamp(Number.isFinite(numeric) ? numeric : fallback, def.min, def.max);
  const stepped = Math.round((bounded - def.min) / def.step) * def.step + def.min;
  return clamp(stepped, def.min, def.max);
}

function sameParams(a, b) {
  return PARAM_DEFS.every((def) => Number(a?.[def.key]) === Number(b?.[def.key]));
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
