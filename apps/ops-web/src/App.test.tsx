import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { App } from "./App";

describe("operations console", () => {
  it("renders the five governed work areas and evidence boundaries", () => {
    const markup = renderToStaticMarkup(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);

    expect(markup).toContain("连接器");
    expect(markup).toContain("数据冲突");
    expect(markup).toContain("Agent Trace");
    expect(markup).toContain("评测运行");
    expect(markup).toContain("发布门禁");
    expect(markup).toContain("0.2.0");
  });

  it("does not render raw credential or private-trace labels", () => {
    const markup = renderToStaticMarkup(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>).toLowerCase();

    expect(markup).not.toContain("api_key");
    expect(markup).not.toContain("access_token");
    expect(markup).not.toContain("raw user input");
    expect(markup).not.toContain("chain of thought");
  });
});
