import { Building2, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

export default function WorkspaceEntryPage() {
  const navigate = useNavigate();
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function enterWorkspace() {
      try {
        const data = await api.listProjects();
        let project = data.projects?.[0];
        if (!project) project = await api.createProject("我的第一个外遮阳项目");
        if (!cancelled) navigate(`/project/${project.project_id}/chat`, { replace: true });
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    }

    enterWorkspace();
    return () => { cancelled = true; };
  }, [navigate]);

  return (
    <section className="workspace-entry" aria-live="polite">
      <span><Building2 size={24} /></span>
      {error ? <><strong>无法进入项目工作区</strong><p>{error}</p></> : <><LoaderCircle className="spin" size={18} /><strong>正在进入 FacadeGPT</strong></>}
    </section>
  );
}
