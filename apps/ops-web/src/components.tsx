import type { ReactNode } from "react";

export type IconName =
  | "audit"
  | "chevron"
  | "connector"
  | "data"
  | "evaluation"
  | "gate"
  | "trace";

const iconPaths: Record<IconName, ReactNode> = {
  connector: <path d="M8 3v4m8-4v4M5 7h14v4a7 7 0 0 1-14 0V7Zm7 11v3" />,
  data: <path d="M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Zm0 0v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />,
  trace: <path d="M6 4v6a2 2 0 0 0 2 2h8m-2-3 3 3-3 3M6 20v-3" />,
  evaluation: <path d="M5 20V10m5 10V4m5 16v-7m5 7H3m14-12 2 2 3-4" />,
  gate: <path d="M12 3 5 6v5c0 4.8 2.9 8.2 7 10 4.1-1.8 7-5.2 7-10V6l-7-3Zm-3 9 2 2 4-5" />,
  audit: <path d="M7 3h10v18H7zM9.5 8h5M9.5 12h5M9.5 16h3" />,
  chevron: <path d="m9 5 7 7-7 7" />,
};

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg
      aria-hidden="true"
      className="icon"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
    >
      <g stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7">
        {iconPaths[name]}
      </g>
    </svg>
  );
}

export function StatusTag({ value }: { value: string }) {
  const normalized = value.toLowerCase().replaceAll("_", "-");
  return <span className={`status-tag status-${normalized}`}>{value}</span>;
}

export function PageHeading({ title, summary }: { title: string; summary: string }) {
  return (
    <header className="page-heading">
      <div>
        <h1>{title}</h1>
        <p>{summary}</p>
      </div>
      <time dateTime="2026-08-26T17:00:00+08:00">证据时点 2026-08-26 17:00 CST</time>
    </header>
  );
}

export function EvidenceBoundary({
  local,
  external,
}: {
  local: string;
  external?: string | null;
}) {
  return (
    <div className="evidence-boundary">
      <span><b>本地证据</b>{local}</span>
      <span className={external ? "external-open" : "external-clear"}>
        <b>外部门禁</b>{external ?? "无"}
      </span>
    </div>
  );
}

export function RatioBar({ value }: { value: number }) {
  return (
    <span className="ratio" aria-label={`配额使用 ${Math.round(value * 100)}%`}>
      <span style={{ width: `${Math.min(value * 100, 100)}%` }} />
    </span>
  );
}
