import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("operations console", () => {
  it("renders the five governed work areas and evidence boundaries", () => {
    const markup = renderToStaticMarkup(<App />);

    expect(markup).toContain("连接器");
    expect(markup).toContain("数据冲突");
    expect(markup).toContain("Agent Trace");
    expect(markup).toContain("评测运行");
    expect(markup).toContain("发布门禁");
    expect(markup).toContain("本地证据");
    expect(markup).toContain("外部门禁");
    expect(markup).toContain("0.1.0");
  });

  it("does not render raw credential or private-trace labels", () => {
    const markup = renderToStaticMarkup(<App />).toLowerCase();

    expect(markup).not.toContain("api_key");
    expect(markup).not.toContain("access_token");
    expect(markup).not.toContain("raw user input");
    expect(markup).not.toContain("chain of thought");
  });
});
