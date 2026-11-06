import { useState, useRef, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { fixtureOpsIdentity, opsClient, setOpsCredential } from "./generated/ops-client";
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
  const queryClient = useQueryClient();
  const loginAttempt = useRef(0);
  const [connected, setConnected] = useState(fixtureOpsIdentity);
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");
  const [connecting, setConnecting] = useState(false);
  function disconnect() {
    loginAttempt.current += 1;
    setConnecting(false);
    setSecret("");
    setError("");
    setOpsCredential("");
    queryClient.clear();
    setConnected(false);
  }
  async function signIn(event: FormEvent) {
    event.preventDefault();
    const attempt = ++loginAttempt.current;
    setConnecting(true);
    setError("");
    setOpsCredential(secret.trim());
    setSecret("");
    try {
      await opsClient.policy();
      if (attempt !== loginAttempt.current) return;
      queryClient.clear();
      setConnected(true);
    } catch {
      if (attempt !== loginAttempt.current) return;
      disconnect();
      setError("凭据无效或暂时无法连接，请确认后重试。");
    } finally { if (attempt === loginAttempt.current) setConnecting(false); }
  }
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
          <button className="environment" type="button">{fixtureOpsIdentity ? "本地演示" : "运营工作台"}<span>{fixtureOpsIdentity ? "非生产" : "服务端授权"}</span></button>
          <button className="role" type="button" onClick={disconnect}>{connecting ? "取消连接" : connected ? "退出运营身份" : "尚未连接"}</button>
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
          {connected ? <ActiveView section={section} /> : <section className="panel ops-signin">
            <h1>连接运营工作台</h1>
            <p>使用管理员提供的运营凭据。权限由服务器决定，退出或刷新页面后需重新连接。</p>
            <form onSubmit={(event) => void signIn(event)}>
              <label htmlFor="ops-credential">运营凭据</label>
              <input id="ops-credential" type="password" autoComplete="off" value={secret} onChange={(event) => setSecret(event.target.value)} required />
              <button className="primary-action" type="submit" disabled={connecting}>{connecting ? "连接中" : "连接"}</button>
            </form>
            {error && <p role="alert">{error}</p>}
          </section>}
        </main>
      </div>
    </div>
  );
}
