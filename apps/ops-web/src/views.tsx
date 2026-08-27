import { useMemo, useState } from "react";
import type { ConnectorStatus, EntityConflict, EvaluationRun } from "./generated/api-contracts";
import { EvidenceBoundary, Icon, PageHeading, RatioBar, StatusTag } from "./components";
import { connectors, entityConflicts, evaluationRuns, releaseGates, traces } from "./ops-data";

function formatPercent(value?: number | null) {
  return value == null ? "—" : `${(value * 100).toFixed(2)}%`;
}

function formatFreshness(value?: number | null) {
  if (value == null) return "—";
  const minutes = Math.floor(value / 60);
  const seconds = value % 60;
  return `${minutes}分${seconds}秒`;
}

export function ConnectorView() {
  const [selectedId, setSelectedId] = useState(connectors[0].source_id);
  const selected = connectors.find((item) => item.source_id === selectedId) ?? connectors[0];
  const histogram = [4, 14, 36, 23, 11, 6, 3, 1];

  return (
    <div className="page-with-rail">
      <section className="page-canvas">
        <PageHeading title="连接器" summary="授权、健康、限流和报价新鲜度；fixture 与 live 结论严格分层。" />
        <div className="subnav" aria-label="连接器视图">
          <button className="active" type="button">来源健康</button>
          <button type="button">授权与配额</button>
          <button type="button">速率限制</button>
          <button type="button">报价新鲜度</button>
        </div>
        <div className="toolbar">
          <label>
            <span className="sr-only">搜索来源</span>
            <input placeholder="搜索来源名称或域名" type="search" />
          </label>
          <select aria-label="健康状态"><option>所有健康状态</option></select>
          <label className="check"><input type="checkbox" />仅看异常</label>
          <button className="secondary-action" type="button">刷新本地证据</button>
        </div>
        <div className="table-scroll">
          <table>
            <caption className="sr-only">连接器来源健康状态</caption>
            <thead><tr><th>来源</th><th>授权状态</th><th>健康状态</th><th>错误率(5m)</th><th>速率限制</th><th>报价新鲜度 P50</th><th>更新时间</th><th /></tr></thead>
            <tbody>
              {connectors.map((item) => (
                <tr className={item.source_id === selected.source_id ? "selected-row" : ""} key={item.source_id}>
                  <td><button className="source-button" onClick={() => setSelectedId(item.source_id)} type="button"><b>{item.display_name}</b><small>{item.source_id}</small></button></td>
                  <td><StatusTag value={item.authorization} /></td>
                  <td><StatusTag value={item.health} /></td>
                  <td>{formatPercent(item.error_rate_5m)}</td>
                  <td><span>{item.requests_used.toLocaleString()} / {item.requests_limit.toLocaleString()}</span><RatioBar value={item.requests_used / item.requests_limit} /></td>
                  <td>{formatFreshness(item.freshness_p50_seconds)}</td>
                  <td><time dateTime={item.last_observed_at}>17:00:00</time></td>
                  <td><button aria-label={`查看 ${item.display_name}`} className="icon-button" onClick={() => setSelectedId(item.source_id)} type="button"><Icon name="chevron" size={17} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="analytics-band">
          <section className="chart-panel">
            <header><h2>报价新鲜度</h2><span>P50 6分10秒 · P95 18分40秒</span></header>
            <div className="histogram" aria-label="报价新鲜度分布">
              {histogram.map((value, index) => <span key={index} style={{ height: `${value * 2.2}px` }} />)}
            </div>
            <div className="axis"><span>≤1分</span><span>2–5分</span><span>10–20分</span><span>&gt;60分</span></div>
          </section>
          <section className="limit-panel">
            <header><h2>外部门禁</h2><span>不可由 fixture 推断</span></header>
            {connectors.map((item) => (
              <div className="limit-row" key={item.source_id}><b>{item.display_name}</b><RatioBar value={item.requests_used / item.requests_limit} /><span>{item.evidence.external_gate ? "BLOCKED" : "CLEAR"}</span></div>
            ))}
          </section>
        </div>
      </section>
      <ConnectorRail connector={selected} />
    </div>
  );
}

function ConnectorRail({ connector }: { connector: ConnectorStatus }) {
  return (
    <aside className="detail-rail" aria-label={`${connector.display_name}详情`}>
      <header><div><h2>{connector.display_name}</h2><StatusTag value={connector.health} /></div><span>{connector.source_id}</span></header>
      <section><h3>状态概览</h3><dl className="fact-list"><div><dt>授权状态</dt><dd><StatusTag value={connector.authorization} /></dd></div><div><dt>错误率(5m)</dt><dd>{formatPercent(connector.error_rate_5m)}</dd></div><div><dt>报价新鲜度</dt><dd>{formatFreshness(connector.freshness_p50_seconds)}</dd></div><div><dt>更新时间</dt><dd>17:00:00 CST</dd></div></dl></section>
      <section><h3>主要问题</h3><p className="warning-box">本地 fixture 可验证契约和降级状态，但不能证明联盟授权、live 报价或生产限流有效。</p></section>
      <section className="rail-actions"><h3>操作</h3><button type="button">刷新本地证据</button><button disabled title="需要生产 SSO/RBAC 与安全审批" type="button">提升配额</button><button disabled title="需要生产 SSO/RBAC 与安全审批" type="button">暂停来源</button></section>
      <section><h3>证据边界</h3><EvidenceBoundary local={connector.evidence.local_evidence} external={connector.evidence.external_gate} /></section>
      <a className="audit-link" href="#audit"><Icon name="audit" size={17} />查看不可变审计</a>
    </aside>
  );
}

export function ConflictView() {
  const [items, setItems] = useState(entityConflicts);
  const [reason, setReason] = useState("来源型号字段存在可复核冲突");
  const pending = items.filter((item) => item.status === "PENDING").length;

  function resolve(item: EntityConflict, status: EntityConflict["status"]) {
    if (reason.trim().length < 12) return;
    setItems((current) => current.map((value) => value.conflict_id === item.conflict_id ? { ...value, status } : value));
  }

  return (
    <section className="page-canvas standalone">
      <PageHeading title="数据冲突" summary={`${pending} 条待复核；合并需要 reviewer 权限、理由、幂等键与不可变审计。`} />
      <div className="evidence-notice"><strong>字段最小化</strong><span>只显示实体引用、冲突字段、来源引用与置信度，不展示原始商家响应。</span></div>
      <label className="reason-field"><span>本次复核理由（至少 12 字）</span><input onChange={(event) => setReason(event.target.value)} value={reason} /></label>
      <div className="table-scroll">
        <table><caption className="sr-only">商品实体冲突复核队列</caption><thead><tr><th>冲突 ID</th><th>实体对</th><th>冲突字段</th><th>来源</th><th>置信度</th><th>状态</th><th>受控操作</th></tr></thead><tbody>
          {items.map((item) => <tr key={item.conflict_id}><td><b>{item.conflict_id}</b></td><td>{item.left_entity_ref}<br />{item.right_entity_ref}</td><td>{item.conflict_fields.join(" · ")}</td><td>{item.source_refs.join(" / ")}</td><td>{Math.round(item.confidence * 100)}%</td><td><StatusTag value={item.status} /></td><td><div className="inline-actions"><button disabled={item.status !== "PENDING" || reason.trim().length < 12} onClick={() => resolve(item, "MERGED")} type="button">合并</button><button disabled={item.status !== "PENDING" || reason.trim().length < 12} onClick={() => resolve(item, "KEPT_SEPARATE")} type="button">保持分离</button></div></td></tr>)}
        </tbody></table>
      </div>
    </section>
  );
}

export function TraceView() {
  const [selectedId, setSelectedId] = useState(traces[0].run_id);
  const selected = traces.find((item) => item.run_id === selectedId) ?? traces[0];
  return (
    <section className="page-canvas standalone">
      <PageHeading title="Agent Trace" summary="只读公共轨迹：版本、阶段、工具摘要、哈希与 EvidenceRef；不展示思维链或原始输入。" />
      <div className="split-view">
        <div className="table-scroll"><table><caption className="sr-only">Agent 运行轨迹</caption><thead><tr><th>Run</th><th>状态</th><th>模型 / Prompt</th><th>工具</th><th>耗时</th><th>成本估算</th></tr></thead><tbody>{traces.map((trace) => <tr className={trace.run_id === selectedId ? "selected-row" : ""} key={trace.run_id} onClick={() => setSelectedId(trace.run_id)}><td><button className="source-button" onClick={() => setSelectedId(trace.run_id)} type="button"><b>{trace.run_id}</b><small>{trace.created_at.slice(0, 10)}</small></button></td><td><StatusTag value={trace.status} /></td><td>{trace.model_version}<br /><small>{trace.prompt_version}</small></td><td>{trace.tools.length}</td><td>{trace.duration_ms} ms</td><td>{trace.estimated_cost_microunits} μ</td></tr>)}</tbody></table></div>
        <aside className="trace-detail"><h2>{selected.run_id}</h2><p>{selected.redaction_policy}</p>{selected.tools.map((tool) => <div className="tool-step" key={`${tool.tool}-${tool.arguments_sha256}`}><span /><div><strong>{tool.tool}</strong><StatusTag value={tool.status} /><dl><dt>参数摘要</dt><dd>{tool.arguments_sha256}</dd><dt>EvidenceRef</dt><dd>{tool.evidence_refs.join(", ")}</dd><dt>耗时</dt><dd>{tool.duration_ms} ms</dd></dl></div></div>)}</aside>
      </div>
    </section>
  );
}

export function EvaluationView() {
  const [runs, setRuns] = useState(evaluationRuns);
  function queueRun() {
    const next: EvaluationRun = {
      ...evaluationRuns[0],
      run_id: `eval-queued-${runs.length + 1}`,
      dataset_version: "v2-competition-1",
      runner_version: "deterministic-1",
      status: "QUEUED",
      case_count: 0,
      metrics: {},
      evidence: {
        local_evidence: "pending:runner",
        external_gate: "真实模型预算和 held-out 人工双评未批准",
      },
      created_at: new Date().toISOString(),
    };
    setRuns((current) => [...current, next]);
  }
  return (
    <section className="page-canvas standalone">
      <PageHeading title="评测运行" summary="数据版本、runner、原始失败与门禁状态可重放；本地 smoke 不冒充 held-out 或真实模型质量。" />
      <div className="command-row"><div><strong>受控运行</strong><span>reviewer · Idempotency-Key · 审计</span></div><button onClick={queueRun} type="button">排队本地确定性运行</button></div>
      <div className="table-scroll"><table><caption className="sr-only">评测运行记录</caption><thead><tr><th>Run</th><th>数据 / Runner</th><th>状态</th><th>用例</th><th>确定性指标</th><th>证据边界</th></tr></thead><tbody>{runs.map((run) => <tr key={run.run_id}><td><b>{run.run_id}</b></td><td>{run.dataset_version}<br /><small>{run.runner_version}</small></td><td><StatusTag value={run.status} /></td><td>{run.case_count || "待运行"}</td><td>{Object.entries(run.metrics).length ? Object.entries(run.metrics).map(([key, value]) => <span className="metric-line" key={key}>{key}: {value.toFixed(2)}</span>) : "—"}</td><td><EvidenceBoundary local={run.evidence.local_evidence} external={run.evidence.external_gate} /></td></tr>)}</tbody></table></div>
    </section>
  );
}

export function ReleaseView() {
  const passed = useMemo(() => releaseGates.filter((gate) => gate.status === "PASSED").length, []);
  return (
    <section className="page-canvas standalone">
      <PageHeading title="发布门禁" summary={`${passed}/${releaseGates.length} 层有当前通过证据；LIVE、HUMAN 与 RELEASE 不得由本地检查代替。`} />
      <div className="gate-sequence" aria-label="发布门禁序列">{releaseGates.map((gate, index) => <div className="gate-node" key={gate.gate_id}><span>{index + 1}</span><div><small>{gate.evidence_level}</small><strong>{gate.title}</strong><StatusTag value={gate.status} /></div></div>)}</div>
      <div className="table-scroll"><table><caption className="sr-only">发布门禁证据与阻塞</caption><thead><tr><th>门禁</th><th>证据层级</th><th>状态</th><th>当前证据</th><th>硬阻塞</th></tr></thead><tbody>{releaseGates.map((gate) => <tr key={gate.gate_id}><td><b>{gate.title}</b><small>{gate.gate_id}</small></td><td>{gate.evidence_level}</td><td><StatusTag value={gate.status} /></td><td>{gate.evidence_ref ?? "—"}</td><td>{gate.blocker ?? "无"}</td></tr>)}</tbody></table></div>
      <div className="release-stop"><Icon name="gate" /><div><strong>当前不可发布</strong><p>只有 LOCAL 与 INTEGRATION 证据完成；生产授权、真实流量、物理设备、人工验收、法律与正式签名尚未完成。</p></div></div>
    </section>
  );
}
