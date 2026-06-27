import { ArrowUpRight, Camera } from "lucide-react";
import { Link } from "react-router-dom";
import { SCHEME_METRICS, metricRank } from "../utils/schemePresentation.js";

const names = { balanced: "综合平衡型", "low-carbon": "低碳优先型", "low-cost": "成本优先型", daylight: "采光优先型", custom: "自定义权重" };

export default function SchemeCard({ scheme }) {
  return (
    <article className="scheme-card">
      <div className="scheme-head">
        <span className="badge">方案 {scheme.scheme_label}</span>
        <strong>{names[scheme.strategy] || scheme.strategy}</strong>
      </div>
      <h2>{scheme.scheme_name}</h2>
      {scheme.created_at && <time className="scheme-time">生成于 {new Date(scheme.created_at).toLocaleString()}</time>}
      <p>{scheme.description}</p>
      <div className="score-row">
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
      <details>
        <summary>参数表</summary>
        <div className="param-grid">
          {Object.entries(scheme.params).map(([key, value]) => <span key={key}>{key}<strong>{value}</strong></span>)}
        </div>
      </details>
      <Link className="primary wide" to={`/scheme/${scheme.scheme_id}`}>
        <Camera size={17} /> 查看方案 <ArrowUpRight size={17} />
      </Link>
    </article>
  );
}

function Metric({ label, rank, unit, value }) {
  return (
    <div className="mini-metric">
      <span>{label}</span>
      <strong>{value}<small>{unit}</small></strong>
      <em>{rank}</em>
    </div>
  );
}
