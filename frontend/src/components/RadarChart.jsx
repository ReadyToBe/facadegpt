import * as echarts from "echarts";
import { useEffect, useRef } from "react";

export default function RadarChart({ schemes }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.setOption({
      color: ["#1bcaa1", "#151b19", "#65a9ff", "#ff8d63"],
      tooltip: { backgroundColor: "#151b19", borderWidth: 0, textStyle: { color: "#fff" } },
      legend: { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8, textStyle: { color: "#607069" } },
      radar: {
        radius: "62%",
        splitNumber: 4,
        axisName: { color: "#34423c", fontWeight: 700 },
        splitArea: { areaStyle: { color: ["#fbfcfb", "#f4f8f6"] } },
        splitLine: { lineStyle: { color: "#d8e1dc" } },
        axisLine: { lineStyle: { color: "#c5d1cb" } },
        indicator: [
          { name: "低碳", max: 100 },
          { name: "低成本", max: 100 },
          { name: "采光", max: 100 },
        ],
      },
      series: [{
        type: "radar",
        data: schemes.map((scheme) => ({
          name: scheme.scheme_name || `方案${scheme.scheme_label}`,
          areaStyle: { opacity: 0.08 },
          value: [
            Math.max(0, Math.min(100, 100 - ((scheme.performance.lcce - 2800) / 400) * 100)),
            Math.max(0, Math.min(100, 100 - ((scheme.performance.lcc - 6000) / 2500) * 100)),
            scheme.performance.sda,
          ],
        })),
      }],
    });
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [schemes]);

  return <div className="radar" ref={ref} />;
}
