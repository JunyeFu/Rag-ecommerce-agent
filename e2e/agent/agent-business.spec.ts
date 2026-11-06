import { expect, test, type APIRequestContext } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const apiBase = "http://127.0.0.1:8080";

type GoldenScenario = {
  id: string;
  query: string;
  expected_product_id: string;
};

type MissionResult = {
  userId: string;
  threadId: string;
  runId: string;
  events: string;
  snapshot: {
    status: string;
    goal: string;
    candidates: Array<{
      product_id: string;
      variant_id: string;
      evidence_refs: string[];
    }>;
    recommendation_routes: Array<{
      route_type: "STRICT" | "BUDGET" | "ALTERNATIVE";
      status: "AVAILABLE" | "UNAVAILABLE";
      relaxed_constraints: string[];
      product_ids: string[];
    }>;
  };
};

function userHeaders(userId: string, idempotencyKey?: string) {
  return {
    "X-User-ID": userId,
    ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
  };
}

function eventIds(stream: string) {
  return [...stream.matchAll(/^id: (\d+)$/gm)].map((match) => Number(match[1]));
}

async function runMission(
  request: APIRequestContext,
  userId: string,
  goal: string,
  text: string,
  key: string,
): Promise<MissionResult> {
  const created = await request.post(`${apiBase}/v1/threads`, {
    headers: userHeaders(userId),
    data: { goal },
  });
  expect(created.status()).toBe(201);
  const { thread_id: threadId } = (await created.json()) as { thread_id: string };

  const accepted = await request.post(`${apiBase}/v1/threads/${threadId}/turns`, {
    headers: userHeaders(userId, key),
    data: { text, media_ids: [] },
  });
  expect(accepted.status()).toBe(202);
  const { run_id: runId } = (await accepted.json()) as { run_id: string };

  const stream = await request.get(`${apiBase}/v1/agent-runs/${runId}/events`, {
    headers: userHeaders(userId),
  });
  expect(stream.ok()).toBeTruthy();
  const events = await stream.text();

  const snapshotResponse = await request.get(`${apiBase}/v1/threads/${threadId}`, {
    headers: userHeaders(userId),
  });
  expect(snapshotResponse.ok()).toBeTruthy();
  const snapshot = (await snapshotResponse.json()) as MissionResult["snapshot"];
  return { userId, threadId, runId, events, snapshot };
}

test("agent simple: completes one grounded RAG recommendation", async ({ request }) => {
  const mission = await runMission(
    request,
    "00000000-0000-5000-8000-000000000401",
    "预算 2000 元的演示手机",
    "Nova Mobile Pulse 01 演示手机，预算 2000 元",
    "agent-simple-1",
  );

  for (const event of ["products", "offers", "comparison", "completed"]) {
    expect(mission.events).toContain(`event: ${event}`);
  }
  expect(mission.events).toContain("DEMO_FIXTURE");
  expect(mission.snapshot.status).toBe("COMPLETED");
  expect(mission.snapshot.candidates.length).toBeGreaterThanOrEqual(3);
  expect(mission.snapshot.candidates[0].product_id).toBe(
    "3c0668b8-1315-54ea-8d88-90c652c9aaf8",
  );
  expect(mission.snapshot.candidates.every((candidate) => candidate.evidence_refs.length > 0)).toBe(
    true,
  );
  expect(mission.snapshot.recommendation_routes.map((route) => route.route_type)).toEqual([
    "STRICT",
    "BUDGET",
    "ALTERNATIVE",
  ]);
});

test("agent moderate: clarifies, resumes, replays idempotently, and restores SSE", async ({ request }) => {
  const userId = "00000000-0000-5000-8000-000000000402";
  const created = await request.post(`${apiBase}/v1/threads`, {
    headers: userHeaders(userId),
    data: { goal: "通勤降噪耳机" },
  });
  const { thread_id: threadId } = (await created.json()) as { thread_id: string };

  const vagueTurn = await request.post(`${apiBase}/v1/threads/${threadId}/turns`, {
    headers: userHeaders(userId, "agent-moderate-clarify"),
    data: { text: "通勤降噪耳机", media_ids: [] },
  });
  const vagueAccepted = (await vagueTurn.json()) as { run_id: string };
  const vagueEvents = await request.get(`${apiBase}/v1/agent-runs/${vagueAccepted.run_id}/events`, {
    headers: userHeaders(userId),
  });
  expect(await vagueEvents.text()).toContain("event: clarification_required");

  const waiting = await request.get(`${apiBase}/v1/threads/${threadId}`, {
    headers: userHeaders(userId),
  });
  expect((await waiting.json()).status).toBe("WAITING_CLARIFICATION");

  const answerPayload = { text: "预算上限 1500 元", media_ids: [] };
  const answered = await request.post(`${apiBase}/v1/threads/${threadId}/turns`, {
    headers: userHeaders(userId, "agent-moderate-answer"),
    data: answerPayload,
  });
  expect(answered.status()).toBe(202);
  const accepted = (await answered.json()) as { run_id: string; replayed: boolean };
  expect(accepted.replayed).toBe(false);

  const replay = await request.post(`${apiBase}/v1/threads/${threadId}/turns`, {
    headers: userHeaders(userId, "agent-moderate-answer"),
    data: answerPayload,
  });
  const replayed = (await replay.json()) as { run_id: string; replayed: boolean };
  expect(replayed.run_id).toBe(accepted.run_id);
  expect(replayed.replayed).toBe(true);

  const fullStream = await request.get(`${apiBase}/v1/agent-runs/${accepted.run_id}/events`, {
    headers: userHeaders(userId),
  });
  const fullEvents = await fullStream.text();
  expect(fullEvents).toContain("event: completed");
  const ids = eventIds(fullEvents);
  expect(ids.length).toBeGreaterThan(2);
  const cursor = ids.at(-3)!;
  const resumedStream = await request.get(`${apiBase}/v1/agent-runs/${accepted.run_id}/events`, {
    headers: { ...userHeaders(userId), "Last-Event-ID": String(cursor) },
  });
  const resumedIds = eventIds(await resumedStream.text());
  expect(resumedIds.length).toBe(2);
  expect(resumedIds.every((id) => id > cursor)).toBe(true);

  const completed = await request.get(`${apiBase}/v1/threads/${threadId}`, {
    headers: userHeaders(userId),
  });
  const snapshot = await completed.json();
  expect(snapshot.status).toBe("COMPLETED");
  expect(snapshot.goal).toBe("通勤降噪耳机; 预算上限 1500 元");
  expect(snapshot.recommendation_routes.map((route: { route_type: string }) => route.route_type)).toEqual([
    "STRICT",
    "BUDGET",
    "ALTERNATIVE",
  ]);
});

test("agent heavy: completes ten missions and a shopping decision loop with isolation", async ({
  request,
}) => {
  const scenarios = JSON.parse(
    fs.readFileSync(path.resolve("evals/v3/golden-scenarios.json"), "utf8"),
  ).scenarios as GoldenScenario[];

  const missions = await Promise.all(
    scenarios.map((scenario, index) =>
      runMission(
        request,
        `00000000-0000-5000-8000-${String(500 + index).padStart(12, "0")}`,
        scenario.query,
        scenario.query,
        `agent-heavy-${scenario.id}`,
      ),
    ),
  );

  expect(missions).toHaveLength(10);
  missions.forEach((mission, index) => {
    expect(mission.snapshot.status).toBe("COMPLETED");
    expect(mission.snapshot.candidates[0].product_id).toBe(scenarios[index].expected_product_id);
    expect(mission.snapshot.candidates.every((candidate) => candidate.evidence_refs.length > 0)).toBe(
      true,
    );
    expect(mission.events).toContain("event: products");
    expect(mission.events).toContain("event: offers");
    expect(mission.events).toContain("event: comparison");
    expect(mission.events).toContain("event: completed");
    expect(mission.snapshot.recommendation_routes).toHaveLength(3);
  });

  const primary = missions[0];
  const productId = primary.snapshot.candidates[0].product_id;
  const product = await request.get(`${apiBase}/v1/products/${productId}`, {
    headers: userHeaders(primary.userId),
  });
  const productBody = await product.json();
  const offers = await request.get(`${apiBase}/v1/products/${productId}/offers?fresh=true`, {
    headers: userHeaders(primary.userId),
  });
  const offersBody = await offers.json();
  expect(offersBody.offers[0].verification).toBe("DEMO_FIXTURE");
  expect(offersBody.offers[0].business_facts.map((fact: { fact_type: string }) => fact.fact_type)).toEqual([
    "price",
    "inventory",
    "delivery",
    "merchant",
    "after_sales",
  ]);
  expect(
    offersBody.offers[0].business_facts.every(
      (fact: { verification_level: string; evidence_ref: string }) =>
        fact.verification_level === "DEMO_FIXTURE" && fact.evidence_ref.length > 0,
    ),
  ).toBe(true);

  const list = await request.post(`${apiBase}/v1/lists`, {
    headers: userHeaders(primary.userId),
    data: { name: "黄金场景方案" },
  });
  const listBody = await list.json();
  const saved = await request.patch(`${apiBase}/v1/lists/${listBody.list_id}`, {
    headers: userHeaders(primary.userId),
    data: { add_variant_id: productBody.variant_id },
  });
  expect((await saved.json()).variant_ids).toContain(productBody.variant_id);

  const offerId = offersBody.offers[0].offer_id;
  const cart = await request.post(`${apiBase}/v1/cart`, {
    headers: userHeaders(primary.userId),
    data: { operation: "add", offer_id: offerId, quantity: 1 },
  });
  const cartItems = (await cart.json()).items;
  expect(cartItems).toHaveLength(1);
  expect(cartItems[0]).toMatchObject({ offer_id: offerId, quantity: 1 });
  expect(cartItems[0].product.product_id).toBe(productBody.product_id);
  expect(cartItems[0].quote.offer_id).toBe(offerId);
  expect(cartItems[0].quote.verification).toBe("DEMO_FIXTURE");
  expect(cartItems[0].quote.source_ref).toBeTruthy();
  expect(Date.parse(cartItems[0].quote.expires_at)).toBeGreaterThan(Date.parse(cartItems[0].quote.collected_at));

  const watcherPath = `${apiBase}/v1/threads/${primary.threadId}/watchers`;
  const watcher = await request.post(watcherPath, {
    headers: userHeaders(primary.userId),
    data: { kind: "PRICE_BELOW", offer_id: offerId, threshold_minor: 180000 },
  });
  expect(watcher.status()).toBe(201);
  const watcherBody = await watcher.json();
  expect(watcherBody.status).toBe("DEMO_DRAFT");
  expect(watcherBody.scheduler_active).toBe(false);
  expect(watcherBody.disclosure).toContain("不会后台提醒");
  const watchers = await request.get(watcherPath, { headers: userHeaders(primary.userId) });
  expect((await watchers.json()).watchers).toHaveLength(1);

  const resolved = await request.post(`${apiBase}/v1/offers/${offerId}/resolve`, {
    headers: userHeaders(primary.userId),
    data: { confirmed_quote_change: false },
  });
  expect((await resolved.json()).link_url).toMatch(/^https:\/\//);

  const isolatedLists = await request.get(`${apiBase}/v1/lists`, {
    headers: userHeaders(missions[1].userId),
  });
  const isolatedCart = await request.get(`${apiBase}/v1/cart`, {
    headers: userHeaders(missions[1].userId),
  });
  expect((await isolatedLists.json()).lists).toEqual([]);
  expect((await isolatedCart.json()).items).toEqual([]);
  const isolatedWatcher = await request.get(watcherPath, {
    headers: userHeaders(missions[1].userId),
  });
  expect(isolatedWatcher.status()).toBe(404);
});
