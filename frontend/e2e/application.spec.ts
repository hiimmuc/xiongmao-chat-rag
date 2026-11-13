import { test, expect } from "@playwright/test";
test("sign in, chat stream, safe markdown and navigation", async ({ page }) => {
  const messages: any[] = [];
  let chat: any;
  let creates = 0;
  const selectedModels: string[] = [];
  const uploads: string[] = [];
  const projectDocs: any[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const r = route.request(),
      p = new URL(r.url()).pathname.replace("/api/v1", "");
    if (p === "/auth/refresh") return route.fulfill({ status: 401, json: { code: "unauthorized", message: "Signed out" } });
    if (p === "/auth/login") {
      expect(r.postDataJSON()).toEqual({ email: "owner@example.test", password: "a long enough password" });
      return route.fulfill({
        json: { access_token: "test-token", token_type: "bearer", expires_in: 900, user: { id: "owner", email: "owner@example.test", display_name: "Owner" } },
      });
    }
    expect(r.headers().authorization).toBe("Bearer test-token");
    let body: any = { items: [], next_cursor: null };
    if (p === "/models")
      body = {
        items: [
          { id: "test-model", label: "Test model", provider: "openai" },
          { id: "gemini-test", label: "Gemini test", provider: "gemini" },
        ],
      };
    else if (p === "/documents" && r.method() === "POST") {
      uploads.push(new URL(r.url()).search);
      const doc = { id: "d1", name: "notes.md", state: "ready", bytes: 2048, created_at: "2026-11-12T09:00:00Z" };
      projectDocs.push(doc);
      body = doc;
    } else if (p === "/documents") body = { items: projectDocs, next_cursor: null };
    else if (p === "/conversations/chat-1" && r.method() === "PATCH") {
      chat = { ...chat, ...r.postDataJSON() };
      body = chat;
    }
    else if (p === "/projects")
      body = { free_id: "f1", items: [{ id: "p1", name: "My project", documents: 0, conversations: 0 }] };
    else if (p === "/me/preferences" && r.method() === "PATCH") body = r.postDataJSON();
    else if (p === "/me/preferences")
      body = { mode: "system", color_theme: "claude", font_family: "system", font_size: "medium", response_style: "default", notifications: { enabled: true, document_processing: true, system: true } };
    else if (p === "/conversations" && r.method() === "POST") {
      creates++;
      chat = { id: "chat-1", title: "New conversation", document_ids: [] };
      body = chat;
    } else if (p === "/conversations")
      body = { items: chat ? [chat] : [], next_cursor: null };
    else if (p === "/conversations/chat-1") body = chat;
    else if (p.endsWith("/messages"))
      body = { items: messages, next_cursor: null };
    else if (p.endsWith("/generations")) {
      const modelId = r.postDataJSON().model_id;
      selectedModels.push(modelId);
      messages.push(
        { id: "u1", role: "user", content: "Hello" },
        {
          id: "a1",
          role: "assistant",
          generation_id: "g1",
          status: "completed",
          content: "**Hello** <script>alert(1)</script> [1, 2, 3]",
          model_id: modelId,
          citations: [
            { id: "1", name: "Case_Studies.pdf", page: 1 },
            { id: "2", name: "Case_Studies.pdf", page: 4 },
            { id: "3", name: "notes.md" },
          ],
        },
      );
      await route.fulfill({
        contentType: "text/event-stream",
        body: 'event: start\ndata: {"generation_id":"g1","assistant_message_id":"a1"}\n\nevent: delta\ndata: {"text":"Hello"}\n\nevent: done\ndata: {"status":"completed"}\n\n',
      });
      return;
    } else if (p === "/generations/g1") body = { status: "completed" };
    else if (p === "/me") body = { id: "owner", display_name: "Owner" };
    await route.fulfill({ json: body });
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  // Sign-up refuses mismatched passwords before calling the API (no /auth/signup mock exists).
  await page.getByRole("button", { name: "Create an account" }).click();
  await page.getByLabel("Email").fill("owner@example.test");
  await page.getByLabel("Password", { exact: true }).fill("a long enough password");
  await page.getByLabel("Confirm password").fill("a different password");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("alert")).toHaveText("The passwords do not match.");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Email").fill("owner@example.test");
  await page.getByLabel("Password", { exact: true }).fill("a long enough password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();

  await page.getByLabel("Message", { exact: true }).fill("Hello");
  await page.getByLabel("Message", { exact: true }).press("Enter");
  await expect(page.locator(".message.assistant strong")).toHaveText("Hello");
  await expect(page.locator(".message script")).toHaveCount(0);
  // Several passages from one file show as one entry with numbered passage buttons.
  const sources = page.locator(".message.assistant").first().locator(".source");
  await expect(sources).toHaveCount(2);
  await expect(sources.first()).toContainText("Case_Studies.pdf");
  await expect(sources.first().locator("button.num")).toHaveText(["1", "2"]);
  await page.screenshot({
    path: "test-results/chat-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: /^Provider:/ }).click();
  await page.getByRole("option", { name: "Gemini" }).click();
  await page.getByLabel("Message", { exact: true }).fill("Second question");
  await page.getByLabel("Message", { exact: true }).press("Shift+Enter");
  await expect(page.getByLabel("Message", { exact: true })).toHaveValue("Second question\n");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.locator(".message.assistant")).toHaveCount(2);
  expect(creates).toBe(1);
  expect(selectedModels).toEqual(["test-model", "gemini-test"]);
  await expect(page.locator(".message.assistant").last()).toContainText("Gemini test");
  expect(
    await page.evaluate(() =>
      JSON.stringify({ ...sessionStorage, ...localStorage }),
    ),
  ).not.toContain("test-token");
  // Drop a file onto a project chat: it becomes a project document and is switched on for the chat.
  const files = await page.evaluateHandle(() => {
    const t = new DataTransfer();
    t.items.add(new File(["# Notes"], "notes.md", { type: "text/markdown" }));
    return t;
  });
  await expect(page.getByLabel("Message", { exact: true })).toBeEnabled(); // drops wait for the answer to finish
  await page.dispatchEvent(".chat-main", "dragenter", { dataTransfer: files });
  await expect(page.getByText("Drop files to add them")).toBeVisible();
  await page.dispatchEvent(".chat-main", "drop", { dataTransfer: files });
  await expect(page.getByText("Drop files to add them")).toBeHidden();
  await expect.poll(() => uploads).toEqual(["?project_id=p1"]);
  await expect(page.locator(".chip", { hasText: "notes.md" })).toBeVisible();
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Projects", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Documents", exact: true })).toBeVisible();
  await expect(page.locator(".doc-name", { hasText: "notes.md" })).toBeVisible();
  await expect(page.locator(".badge-ready")).toHaveText("Ready");
  await page.screenshot({ path: "test-results/projects-desktop.png", fullPage: true });
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("tab", { name: "Appearance" }).click();
  await page.getByRole("radio", { name: "Dark", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("radio", { name: /Github/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-palette", "github");
  await page.getByRole("radio", { name: "System", exact: true }).first().click();
  await page.getByRole("button", { name: "Account", exact: true }).click();
  await expect(page.getByLabel("Display name")).toHaveValue("Owner");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 390);
  await page.screenshot({
    path: "test-results/account-mobile.png",
    fullPage: true,
  });
});
