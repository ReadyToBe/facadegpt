import { ArrowLeft, BarChart3 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import RadarChart from "../components/RadarChart.jsx";
import SchemeCard from "../components/SchemeCard.jsx";
import { api } from "../api/client";
import { useFacadeStore } from "../stores/useFacadeStore";

export default function ResultsPage() {
  const { id } = useParams();
  const { schemes, setSchemes } = useFacadeStore();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadSavedSchemes() {
    setLoading(true);
    setError("");
    try {
      const result = await api.getProjectSchemes(id);
      setSchemes(result.schemes || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function regenerate() {
    setLoading(true);
    setError("");
    try {
      await api.generateSchemes(id, { num_schemes: 1, strategies: ["balanced"] });
      const saved = await api.getProjectSchemes(id);
      setSchemes(saved.schemes || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSavedSchemes();
  }, [id]);

  return (
    <section className="results">
      <div className="toolbar">
        <Link className="secondary" to={`/project/${id}/chat`}><ArrowLeft size={17} /> 返回调整</Link>
        <button className="primary" onClick={regenerate} disabled={loading}><BarChart3 size={18} /> 生成新一组方案</button>
      </div>
      <div className="result-intro">
        <div>
          <p className="eyebrow">PERFORMANCE STUDY</p>
          <h1>方案性能对比</h1>
        </div>
        <p>比较低碳、成本与采光表现，找到更适合继续深化的立面方向。</p>
      </div>
      {error && <p className="error">{error}</p>}
      {loading ? (
        <div className="empty-state">正在读取已保存方案...</div>
      ) : schemes.length > 0 ? (
        <>
          <div className="chart-band">
            <div className="chart-label">LATEST 04 / NORMALIZED SCORE</div>
            <RadarChart schemes={schemes.slice(0, 4)} />
          </div>
          <p className="history-count">共保存 {schemes.length} 个方案，最新生成的方案排在前面。</p>
          <div className="scheme-grid">
            {schemes.map((scheme) => <SchemeCard scheme={scheme} key={scheme.scheme_id} />)}
          </div>
        </>
      ) : (
        <div className="empty-state">
          <h2>这个项目还没有保存方案</h2>
          <p>返回调整参数后生成第一组方案，之后再次打开项目就能直接查看。</p>
          <Link className="primary" to={`/project/${id}/chat`}>返回生成方案</Link>
        </div>
      )}
    </section>
  );
}
