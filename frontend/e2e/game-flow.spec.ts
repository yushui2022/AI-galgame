import { expect, test } from "@playwright/test";

const disabledProviders = {
  llm: { kind: "minicpm", base_url: "", api_key: "", model: "MiniCPM", enabled: false, extra: {} },
  image: {
    kind: "minimax",
    base_url: "https://api.minimax.cn",
    api_key: "",
    model: "image-01",
    enabled: false,
    extra: {}
  },
  video: {
    kind: "seedance",
    base_url: "https://ark.cn-beijing.volces.com/api/v3",
    api_key: "",
    model: "",
    enabled: false,
    extra: {}
  },
  embedding: null
};

async function reachDecision(page: import("@playwright/test").Page) {
  const decision = page.getByRole("region", { name: "选择下一步" });
  const dialogue = page.getByRole("button", { name: /显示完整对白|继续剧情/ });

  // Wait for the newly-created turn to replace the previous decision panel.
  await expect(dialogue).toBeVisible();

  for (let attempt = 0; attempt < 16 && !(await decision.isVisible().catch(() => false)); attempt += 1) {
    if (await dialogue.isVisible().catch(() => false)) {
      await dialogue.click({ force: true, timeout: 800 }).catch(() => undefined);
      await page.waitForTimeout(250);
    } else {
      const skip = page.getByRole("button", { name: "跳过演出" });
      if (await skip.isVisible().catch(() => false)) {
        await skip.click().catch(() => undefined);
      }
      await page.waitForTimeout(150);
    }
  }

  await expect(decision).toBeVisible();
  await expect(dialogue).toBeHidden();
}

test("首次设置向导要求三个供应商测试通过", async ({ page }) => {
  await page.route("**/api/settings/providers**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/test")) {
      await route.fulfill({ json: { ok: true, message: "连接与配置检查通过", latency_ms: 5 } });
      return;
    }
    if (request.method() === "PUT") {
      const payload = request.postDataJSON();
      for (const key of ["llm", "image", "video"]) {
        if (payload[key].api_key) payload[key].api_key = "••••••••";
      }
      await route.fulfill({ json: payload });
      return;
    }
    await route.fulfill({ json: disabledProviders });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "把你的模型接入故事。" })).toBeVisible();

  await page.getByLabel("API 地址").fill("http://127.0.0.1:8000/v1");
  await page.getByLabel("API Key").fill("local-test-key");
  await page.getByRole("button", { name: "保存并测试" }).click();

  await page.getByRole("button", { name: "图片模型" }).click();
  await page.getByLabel("API Key").fill("image-test-key");
  await page.getByRole("button", { name: "保存并测试" }).click();

  await page.getByRole("button", { name: "视频模型" }).click();
  await page.getByLabel("模型或 Endpoint ID").fill("video-endpoint-id");
  await page.getByLabel("API Key").fill("video-test-key");
  await page.getByRole("button", { name: "保存并测试" }).click();

  await expect(page.getByRole("button", { name: /进入故事库/ })).toBeEnabled();
  await page.getByRole("button", { name: /进入故事库/ }).click();
  await expect(page.getByRole("heading", { name: "故事会记住你的选择。" })).toBeVisible();
});

test("示例故事支持选项、自由输入、媒体跳过、分叉和画像保存", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "故事会记住你的选择。" })).toBeVisible();

  await page.getByRole("button", { name: /进入雨夜/ }).click();
  await expect(page.getByText("第 1 幕", { exact: true })).toBeVisible();
  await reachDecision(page);
  await expect(page.getByRole("button", { name: /把短信内容告诉林澄/ })).toBeEnabled();

  await page.getByRole("button", { name: /把短信内容告诉林澄/ }).click();
  await expect(page.getByText("第 2 幕", { exact: true })).toBeVisible({ timeout: 20_000 });
  await reachDecision(page);

  await page.getByRole("button", { name: "自定义行动" }).click();
  await page.getByLabel("或者，亲自决定下一步").fill("检查窗台上有没有留下脚印");
  await page.getByRole("button", { name: "提交自由行动" }).click();
  await expect(page.getByText("第 3 幕", { exact: true })).toBeVisible({ timeout: 20_000 });
  await reachDecision(page);

  await page.getByRole("button", { name: "打开暂停菜单" }).click();
  await page.getByRole("button", { name: /故事分支/ }).click();
  await expect(page.getByRole("heading", { name: "故事分支" })).toBeVisible();
  await page.getByRole("button", { name: "从这里创建分支" }).first().click();
  await expect(page.getByRole("heading", { name: "故事分支" })).toBeHidden();
  await page.getByRole("button", { name: "打开暂停菜单" }).click();
  await page.getByRole("button", { name: /故事分支/ }).click();
  await expect(page.locator(".branch-switcher button")).toHaveCount(2);
  await page.getByRole("button", { name: "关闭" }).click();

  await page.getByRole("button", { name: "打开暂停菜单" }).click();
  await page.getByRole("button", { name: /玩家画像/ }).click();
  await page.getByLabel("给系统的备注").fill("偏好慢热悬疑，不要快速揭晓真相");
  await page.getByRole("button", { name: /保存画像/ }).click();
  await expect(page.getByText("画像已保存")).toBeVisible();

  await page.reload();
  await expect(page.getByText("第 3 幕", { exact: true })).toBeVisible();
});
