export const SCHEME_METRICS = {
  lcce: { label: "LCCE", unit: "kgCO2/m2" },
  lcc: { label: "LCC", unit: "yuan/m2" },
  sda: { label: "sDA", unit: "%" },
};

const PARAM_LABELS = {
  shading_type: { 1: "水平遮阳", 2: "垂直遮阳", 3: "混合遮阳" },
  material: { 1: "混凝土", 2: "铝材", 3: "钢材" },
  glass_type: { 1: "单层Low-E", 2: "双层Low-E", 3: "双层中空", 4: "三层中空" },
};

export function metricRank(performance, key) {
  return performance?.[`${key}_rank`] || "待评估";
}

export function schemePerformanceSummary(scheme) {
  if (!scheme) return "";
  const params = scheme.params || {};
  const performance = scheme.performance || {};
  const shadingType = labelFor("shading_type", params.shading_type, "外遮阳构件");
  const material = labelFor("material", params.material, "构件材料");
  const glassType = labelFor("glass_type", params.glass_type, "高性能玻璃");
  const spacing = paramWithUnit(params.spacing, "mm");
  const bladeDepth = paramWithUnit(params.blade_depth, "mm");
  const windowDistance = paramWithUnit(params.window_distance, "mm");
  const wwr = paramWithUnit(params.wwr, "%");
  const ranks = [
    `LCCE ${metricRank(performance, "lcce")}`,
    `LCC ${metricRank(performance, "lcc")}`,
    `sDA ${metricRank(performance, "sda")}`,
  ].join("、");

  return `几何形态为${spacing}间距的${shadingType}，遮阳深度${bladeDepth}、离窗${windowDistance}，采用${material}构件与${glassType}，窗墙比${wwr}；当前性能评价：${ranks}。`;
}

function labelFor(key, value, fallback) {
  return PARAM_LABELS[key]?.[Number(value)] || fallback;
}

function paramWithUnit(value, unit) {
  if (value === null || value === undefined || value === "") return `待定${unit}`;
  return `${value}${unit}`;
}
