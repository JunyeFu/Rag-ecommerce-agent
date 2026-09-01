import { useState } from "react";
import { Icon, type IconName } from "./components";
import { CONTRACT_VERSION } from "./generated/api-contracts";
import { ConflictView, ConnectorView, EvaluationView, OverviewView, ReleaseView, RetrievalView, TraceView } from "./views";

type Section = "overview" | "traces" | "retrieval" | "connectors" | "conflicts" | "evaluations" | "release";

const navigation: { id: Section; label: string; icon: IconName }[] = [
  { id: "overview", label: "运行概览", icon: "evaluation" },
  { id: "traces", label: "Agent Trace", icon: "trace" },
  { id: "retrieval", label: "检索观测", icon: "data" },
  { id: "connectors", label: "连接器", icon: "connector" },
  { id: "conflicts", label: "数据冲突", icon: "data" },
  { id: "evaluations", label: "评测运行", icon: "evaluation" },
  { id: "release", label: "发布门禁", icon: "gate" },
];

function ActiveView({ section }: { section: Section }) {
  if (section === "overview") return <OverviewView />;
  if (section === "retrieval") return <RetrievalView />;
  if (section === "connectors") return <ConnectorView />;
  if (section === "conflicts") return <ConflictView />;
  if (section === "traces") return <TraceView />;
  if (section === "evaluations") return <EvaluationView />;
  return <ReleaseView />;
}

export function App() {
  const [section, setSection] = useState<Section>("overview");
  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="RAG Commerce Ops 首页">
          <span className="brand-mark">R</span>
          <strong>RAG Commerce Ops</strong>
          <small>v{CONTRACT_VERSION}</small>
        </a>
        <div className="top-controls">
          <button className="environment" type="button">生产预演 <span>非生产</span></button>
          <button className="role" type="button">运营审核员 <span>reviewer fixture</span></button>
        </div>
      </header>
      <div className="workspace" id="top">
        <aside className="sidebar">
          <nav aria-label="运营台主导航">
            {navigation.map((item) => (
              <button
                aria-current={section === item.id ? "page" : undefined}
                className={section === item.id ? "active" : ""}
                key={item.id}
                onClick={() => setSection(item.id)}
                type="button"
              >
                <Icon name={item.icon} />
                <span>{item.label}</span>
              </button>
            ))}
          </nav>
          <div className="sidebar-policy">
            <Icon name="gate" size={18} />
            <div><strong>字段策略已启用</strong><span>无思维链 · 无原始凭据</span></div>
          </div>
          <a className="sidebar-audit" href="#audit"><Icon name="audit" size={18} />查看审计</a>
        </aside>
        <main className="main-region">
          <ActiveView section={section} />
        </main>
      </div>
    </div>
  );
}
