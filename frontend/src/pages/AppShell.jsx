import { Building2 } from "lucide-react";
import { Link, Outlet, useLocation } from "react-router-dom";

export default function AppShell() {
  const location = useLocation();
  const isWorkspace = location.pathname === "/" || location.pathname.startsWith("/project/");
  return (
    <div className={`app${isWorkspace ? " workspace-shell" : ""}`}>
      {!isWorkspace && (
        <header className="topbar">
          <Link to="/" className="brand" aria-label="进入 FacadeGPT 项目工作区">
            <span className="brand-mark"><Building2 size={19} /></span>
            <span>FacadeGPT</span>
          </Link>
          <span className="topbar-context">建筑外遮阳设计助手</span>
        </header>
      )}
      <main className={`main${isWorkspace ? " workspace-main" : ""}`}>
        <Outlet />
      </main>
    </div>
  );
}
