import {
  ArrowUpRight,
  Bot,
  Building2,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  FlaskConical,
  FolderKanban,
  ImagePlus,
  Layers3,
  LoaderCircle,
  MessageSquareText,
  Plus,
  Send,
  Settings2,
  Sparkles,
  Trash2,
  UserRound,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import LabModal from "../components/LabModal.jsx";
import ThreeDViewer from "../components/ThreeDViewer.jsx";
import { api } from "../api/client";
import { PROJECT_PROMPT_EXAMPLES } from "../config/projectPromptExamples.js";
import { useFacadeStore } from "../stores/useFacadeStore";
import { SCHEME_METRICS, metricRank, schemePerformanceSummary } from "../utils/schemePresentation.js";

const strategyNames = {
  balanced: "综合平衡",
  "low-carbon": "低碳优先",
  "low-cost": "成本优先",
  daylight: "采光优先",
  custom: "自定义权重",
};

export default function ProjectChatPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const {
    currentProject,
    projectInfo,
    parameterRanges,
    setProjectBundle,
    setParsed,
    setSchemes: setStoredSchemes,
  } = useFacadeStore();
  const [projects, setProjects] = useState([]);
  const [schemes, setSchemes] = useState([]);
  const [messages, setMessages] = useState([]);
  const [selectedSchemeId, setSelectedSchemeId] = useState("");
  const [input, setInput] = useState("");
  const [weights, setWeights] = useState({ weight_lcce: 0.33, weight_lcc: 0.33, weight_sda: 0.34 });
  const [lastParsedDemand, setLastParsedDemand] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showLab, setShowLab] = useState(false);
  const [schemesCollapsed, setSchemesCollapsed] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [showProjectCreator, setShowProjectCreator] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [creatingProject, setCreatingProject] = useState(false);
  const endRef = useRef(null);

  const selectedScheme = schemes.find((item) => item.scheme_id === selectedSchemeId) || schemes[0] || null;
  const userDiscussion = useMemo(
    () => messages.filter((item) => item.role === "user").map((item) => item.content).join("\n"),
    [messages],
  );
  const isFirstTurn = !messages.some((item) => item.role === "user");

  // Reset project-local state when switching projects so conversations stay isolated.
  useEffect(() => {
    setMessages([]);
    setSchemes([]);
    setSelectedSchemeId("");
    setInput("");
    setError("");
    setNotice("");
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    async function loadWorkspace() {
      setError("");
      try {
        const [bundle, projectData, messageData, schemeData] = await Promise.all([
          api.getProject(id),
          api.listProjects(),
          api.getProjectMessages(id),
          api.getProjectSchemes(id),
        ]);
        if (cancelled) return;
        setProjectBundle(bundle);
        setProjects(projectData.projects || []);
        setMessages(messageData.messages || []);
        setSchemes(schemeData.schemes || []);
        setStoredSchemes(schemeData.schemes || []);
        setSelectedSchemeId(schemeData.schemes?.[0]?.scheme_id || "");
        setWeights({
          weight_lcce: bundle.project_info?.weight_lcce ?? 0.33,
          weight_lcc: bundle.project_info?.weight_lcc ?? 0.33,
          weight_sda: bundle.project_info?.weight_sda ?? 0.34,
        });
        setLastParsedDemand(bundle.project_info?.demand_text || "");

      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    }
    loadWorkspace();
    return () => { cancelled = true; };
  }, [id]);

  async function createProject(event) {
    event.preventDefault();
    const name = newProjectName.trim();
    if (!name || creatingProject) return;
    setCreatingProject(true);
    setError("");
    try {
      const project = await api.createProject(name);
      setNewProjectName("");
      setShowProjectCreator(false);
      navigate(`/project/${project.project_id}/chat`);
    } catch (err) {
      setError(err.message);
    } finally {
      setCreatingProject(false);
    }
  }

  useEffect(() => {
    if (chatBusy || messages.some((item) => item.role === "user")) {
      endRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, chatBusy]);

  async function sendMessage(textOverride) {
    const content = (typeof textOverride === "string" ? textOverride : input).trim();
    if (!content || chatBusy) return;
    const temporaryId = `pending-${Date.now()}`;
    setInput("");
    setError("");
    setChatBusy(true);
    setMessages((current) => [...current, { message_id: temporaryId, role: "user", content }]);
    try {
      const result = await api.chatProject(id, content);
      setMessages((current) => [
        ...current.filter((item) => item.message_id !== temporaryId),
        result.user_message,
        result.assistant_message,
      ]);
    } catch (err) {
      setMessages((current) => current.filter((item) => item.message_id !== temporaryId));
      setError(err.message);
    } finally {
      setChatBusy(false);
    }
  }

  function handleComposerKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  }

  function setWeight(key, value) {
    const next = { ...weights, [key]: Number(value) };
    const otherKeys = Object.keys(next).filter((item) => item !== key);
    const remaining = Math.max(0, 1 - next[key]);
    const otherTotal = otherKeys.reduce((sum, item) => sum + next[item], 0) || 1;
    otherKeys.forEach((item) => { next[item] = Number(((next[item] / otherTotal) * remaining).toFixed(2)); });
    next[key] = Number(next[key].toFixed(2));
    next.weight_sda = Number((1 - next.weight_lcce - next.weight_lcc).toFixed(2));
    setWeights(next);
  }

  async function saveWeights() {
    await api.updateWeights(id, { ...weights, source: "workspace" });
    setNotice("优化权重已保存");
  }

  async function generateSchemes() {
    if (generating) return;
    setGenerating(true);
    setError("");
    setNotice("");
    try {
      let nextWeights = weights;
      if (userDiscussion && userDiscussion !== lastParsedDemand) {
        const parsed = await api.parseDemand(id, userDiscussion);
        setParsed(parsed);
        nextWeights = {
          weight_lcce: parsed.project_info.weights.lcce,
          weight_lcc: parsed.project_info.weights.lcc,
          weight_sda: parsed.project_info.weights.sda,
        };
        setWeights(nextWeights);
        setLastParsedDemand(userDiscussion);
      }
      await api.updateWeights(id, { ...nextWeights, source: "conversation" });
      const strategy = projectInfo?.weight_preset || "balanced";
      const generated = await api.generateSchemes(id, {
        num_schemes: 1,
        strategies: [strategy],
      });
      const saved = await api.getProjectSchemes(id);
      setSchemes(saved.schemes || []);
      setStoredSchemes(saved.schemes || []);
      setSelectedSchemeId(generated.schemes?.[0]?.scheme_id || saved.schemes?.[0]?.scheme_id || "");
      setNotice("已根据当前讨论生成 1 个新方案");
    } catch (err) {
      setError(err.message);
    } finally {
      setGenerating(false);
    }
  }

  async function deleteSelectedScheme() {
    if (!selectedScheme) return;
    const confirmed = window.confirm(`确定删除“${selectedScheme.scheme_name}”吗？此操作无法撤销。`);
    if (!confirmed) return;
    try {
      await api.deleteScheme(selectedScheme.scheme_id);
      const saved = await api.getProjectSchemes(id);
      setSchemes(saved.schemes || []);
      setStoredSchemes(saved.schemes || []);
      setSelectedSchemeId(saved.schemes?.[0]?.scheme_id || "");
      setNotice("方案已删除");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className={`project-workspace${schemesCollapsed ? " schemes-collapsed" : ""}`}>
      <aside className="workspace-projects">
        <Link to="/" className="workspace-brand" aria-label="进入 FacadeGPT 项目工作区">
          <span className="brand-mark"><Building2 size={19} /></span>
          <span>
            <strong>FacadeGPT</strong>
            <small>建筑外遮阳设计助手</small>
          </span>
        </Link>
        <button className={`workspace-lab-entry${showLab ? " active" : ""}`} onClick={() => setShowLab(true)}>
          <FlaskConical size={16} /> 实验室
        </button>
        <div className="workspace-pane-title">
          <span><FolderKanban size={17} /> 项目</span>
          <button className="workspace-add-button" onClick={() => setShowProjectCreator((value) => !value)} title="新建项目" aria-label="新建项目"><Plus size={16} /></button>
        </div>
        {showProjectCreator && (
          <form className="workspace-project-create" onSubmit={createProject}>
            <label htmlFor="new-project-name">新项目名称</label>
            <input
              id="new-project-name"
              autoFocus
              value={newProjectName}
              onChange={(event) => setNewProjectName(event.target.value)}
              placeholder="例如：广州办公楼西立面"
              maxLength={48}
            />
            <div>
              <button type="button" className="secondary" onClick={() => setShowProjectCreator(false)}>取消</button>
              <button type="submit" className="primary" disabled={!newProjectName.trim() || creatingProject}>{creatingProject ? "创建中" : "创建"}</button>
            </div>
          </form>
        )}
        <nav className="workspace-project-list" aria-label="项目列表">
          {projects.map((project) => (
            <Link
              className={`workspace-project-link${project.project_id === id ? " active" : ""}`}
              key={project.project_id}
              to={`/project/${project.project_id}/chat`}
            >
              <span>{project.name}</span>
              <em>{project.scheme_count}</em>
            </Link>
          ))}
        </nav>
        <button className="workspace-new-project" onClick={() => setShowProjectCreator(true)}><Plus size={16} /> 新建项目</button>
      </aside>

      <main className="conversation-pane">
        <header className="conversation-head">
          <div>
            <h1>{currentProject?.name || "项目讨论"}</h1>
          </div>
          <div className="conversation-actions">
            <button className="tool-button" title="项目参数" onClick={() => setShowSettings(true)}><Settings2 size={18} /></button>
            <button className="primary" onClick={generateSchemes} disabled={generating || !userDiscussion}>
              {generating ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}
              {generating ? "生成中" : "生成方案"}
            </button>
          </div>
        </header>

        <div className="chat-feed">
          {messages.map((message) => (
            <article className={`chat-message ${message.role}`} key={message.message_id}>
              {message.role === "assistant" && <MessageAvatar role="assistant" />}
              <div className="message-body">
                <div className="message-meta">
                  <strong>{message.role === "assistant" ? "FacadeGPT" : "你"}</strong>
                  <span>{message.role === "assistant" ? "建筑外遮阳设计助手" : "项目创建者"}</span>
                </div>
                {message.role === "assistant" ? (
                  <AssistantMessageContent content={message.content} />
                ) : (
                  <div className="message-content">{message.content}</div>
                )}
              </div>
              {message.role === "user" && <MessageAvatar role="user" />}
            </article>
          ))}
          {chatBusy && <div className="chat-thinking"><LoaderCircle className="spin" size={16} /> 正在分析项目条件...</div>}
          <div ref={endRef} />
        </div>

        <div className="composer-wrap">
          {notice && <div className="workspace-notice">{notice}</div>}
          {error && <div className="workspace-error">{error}</div>}
          <div className="chat-composer">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder="继续讨论项目、提出疑问或补充设计条件…"
              rows={3}
            />
            <div className="composer-toolbar">
              <div className="composer-tool-group">
                <button
                  type="button"
                  className="composer-tool"
                  title="上传你的方案示意图给facadegpt"
                  aria-label="上传你的方案示意图给facadegpt"
                >
                  <ImagePlus size={16} />
                  <span>图像</span>
                </button>
              </div>
              <div className="composer-tool-group composer-tool-group-right">
                <button type="button" className="composer-model-switch" title="模型切换暂未开放" aria-label="模型切换暂未开放">
                  <Layers3 size={15} />
                  <span>FacadeGPT</span>
                  <ChevronDown size={14} />
                </button>
                <button className="composer-send" onClick={() => sendMessage()} disabled={!input.trim() || chatBusy} aria-label="发送消息" title="发送消息"><Send size={18} /></button>
              </div>
            </div>
          </div>
          {isFirstTurn && !chatBusy && (
            <div className="prompt-suggestions" aria-label="示例项目提示词">
              <span>不知道从哪里开始？试试这些示例项目</span>
              <div>
                {PROJECT_PROMPT_EXAMPLES.map((example) => (
                  <button
                    type="button"
                    key={example.label}
                    onClick={() => sendMessage(example.prompt)}
                    title="点击后直接发送给 FacadeGPT"
                  >
                    <span>{example.label}</span>
                    <ArrowUpRight size={15} />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </main>

      {schemesCollapsed ? (
        <aside className="scheme-collapsed-rail" aria-label="方案面板已收起">
          <button
            className="tool-button"
            onClick={() => setSchemesCollapsed(false)}
            title="展开方案面板"
            aria-label="展开方案面板"
            aria-expanded="false"
          >
            <ChevronLeft size={18} />
          </button>
          <span>方案</span>
          <em>{schemes.length}</em>
        </aside>
      ) : (
        <>
          <aside className="scheme-rail">
            <div className="workspace-pane-title scheme-rail-title">
              <span><MessageSquareText size={17} /> 方案</span>
              <button
                className="workspace-add-button"
                onClick={() => setSchemesCollapsed(true)}
                title="收起方案面板"
                aria-label="收起方案面板"
                aria-expanded="true"
              >
                <ChevronRight size={16} />
              </button>
            </div>
            <div className="scheme-rail-list">
              {schemes.map((scheme) => (
                <button
                  className={scheme.scheme_id === selectedScheme?.scheme_id ? "active" : ""}
                  key={scheme.scheme_id}
                  onClick={() => setSelectedSchemeId(scheme.scheme_id)}
                >
                  <span>方案 {scheme.scheme_label}</span>
                  <small>{strategyNames[scheme.strategy] || scheme.strategy}</small>
                </button>
              ))}
              {!schemes.length && <p className="rail-empty">讨论清楚后生成第一组方案</p>}
            </div>
          </aside>

          <aside className="scheme-preview">
            {selectedScheme ? (
              <>
                <header className="scheme-preview-head">
                  <div><h2>方案 {selectedScheme.scheme_label}</h2></div>
                  <button className="tool-button danger" onClick={deleteSelectedScheme} title="删除方案"><Trash2 size={17} /></button>
                </header>
                <div className="scheme-model"><ThreeDViewer params={selectedScheme.params} /></div>
                <div className="preview-metrics">
                  <PreviewMetric
                    label={SCHEME_METRICS.lcce.label}
                    rank={metricRank(selectedScheme.performance, "lcce")}
                    unit={SCHEME_METRICS.lcce.unit}
                    value={selectedScheme.performance.lcce}
                  />
                  <PreviewMetric
                    label={SCHEME_METRICS.lcc.label}
                    rank={metricRank(selectedScheme.performance, "lcc")}
                    unit={SCHEME_METRICS.lcc.unit}
                    value={selectedScheme.performance.lcc}
                  />
                  <PreviewMetric
                    label={SCHEME_METRICS.sda.label}
                    rank={metricRank(selectedScheme.performance, "sda")}
                    unit={SCHEME_METRICS.sda.unit}
                    value={selectedScheme.performance.sda}
                  />
                </div>
                <p className="scheme-preview-summary">{schemePerformanceSummary(selectedScheme)}</p>
                <details className="preview-params">
                  <summary>几何参数</summary>
                  <div>{Object.entries(selectedScheme.params).filter(([key]) => key !== "scheme_id").map(([key, value]) => <span key={key}><small>{key}</small><strong>{value}</strong></span>)}</div>
                </details>
                <Link className="primary scheme-file-link" to={`/scheme/${selectedScheme.scheme_id}`}>查看方案详情/导出渲染 <ArrowUpRight size={17} /></Link>
              </>
            ) : (
              <div className="scheme-preview-empty"><Sparkles size={24} /><h2>等待方案生成</h2><p>项目讨论会保留在左侧，准备好后即可生成并比较方案。</p></div>
            )}
          </aside>
        </>
      )}

      {showSettings && (
        <div className="drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowSettings(false); }}>
          <aside className="settings-drawer" aria-label="项目参数">
            <header><div><p>PROJECT SETTINGS</p><h2>项目参数</h2></div><button className="tool-button" onClick={() => setShowSettings(false)} title="关闭"><X size={18} /></button></header>
            <div className="settings-info">
              <span>地点<strong>{projectInfo?.location || "待讨论"}</strong></span>
              <span>气候区<strong>{projectInfo?.climate_zone || "待讨论"}</strong></span>
              <span>建筑类型<strong>{projectInfo?.building_type || "待讨论"}</strong></span>
              <span>朝向<strong>{projectInfo?.orientation || "待讨论"}</strong></span>
            </div>
            <div className="drawer-section-title">优化目标权重</div>
            <WeightSlider label="LCCE" value={weights.weight_lcce} onChange={(value) => setWeight("weight_lcce", value)} />
            <WeightSlider label="LCC" value={weights.weight_lcc} onChange={(value) => setWeight("weight_lcc", value)} />
            <WeightSlider label="sDA" value={weights.weight_sda} onChange={(value) => setWeight("weight_sda", value)} />
            <button className="secondary wide" onClick={saveWeights}>保存权重</button>
          </aside>
        </div>
      )}

      {showLab && <LabModal onClose={() => setShowLab(false)} />}
    </section>
  );
}

function MessageAvatar({ role }) {
  if (role === "assistant") {
    return <div className="message-avatar assistant-avatar" aria-hidden="true"><Bot size={19} /></div>;
  }
  return <div className="message-avatar user-avatar" aria-hidden="true"><UserRound size={18} /></div>;
}

function AssistantMessageContent({ content }) {
  const blocks = content.split(/\n/);
  return (
    <div className="message-content assistant-rich-text">
      {blocks.map((line, index) => {
        const text = line.trim();
        if (!text) return <span className="assistant-spacer" key={`blank-${index}`} />;
        const heading = /^(#{1,3}\s*)?([一二三四五六七八九十]+[、.．]|Step\s*\d+|第[一二三四五六七八九十\d]+步)/i.test(text);
        const listItem = /^([-•*]\s+|\d+[.、]\s*)/.test(text);
        return (
          <p className={`${heading ? "assistant-heading" : ""}${listItem ? " assistant-list-item" : ""}`} key={`${text}-${index}`}>
            {renderInlineEmphasis(text.replace(/^#{1,3}\s*/, ""))}
          </p>
        );
      })}
    </div>
  );
}

function renderInlineEmphasis(text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }
    return <span key={`${part}-${index}`}>{part}</span>;
  });
}

function PreviewMetric({ label, rank, unit, value }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}<small>{unit}</small></strong>
      <em>{rank}</em>
    </div>
  );
}

function WeightSlider({ label, value, onChange }) {
  return (
    <label className="slider-row">
      <span>{label}</span>
      <input type="range" min="0" max="1" step="0.01" value={value} onChange={(event) => onChange(event.target.value)} />
      <strong>{Number(value).toFixed(2)}</strong>
    </label>
  );
}
