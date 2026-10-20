import { test, expect } from "@playwright/test";
import path from "node:path";

test("account, real planner, guided steps, photo alignment, and persistence", async ({
  page,
}) => {
  const email = `e2e-${Date.now()}@example.com`;
  await page.goto("/");
  if (process.env.CIRCUITPILOT_QA_DIR)
    await page.screenshot({
      path: path.join(process.env.CIRCUITPILOT_QA_DIR, "auth.png"),
      fullPage: true,
    });
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("isolated-e2e-password");
  await page.getByRole("button", { name: "Create your workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Good builds start" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Series LED/ }).click();
  await page
    .getByPlaceholder("My first breadboard circuit")
    .fill("Browser LED test");
  await page
    .getByRole("button", { name: "Validate & generate reference layout" })
    .click();
  await expect(page.getByText("Connectivity graph passed")).toBeVisible();
  await expect(
    page.getByText("Reference layout · physical verification pending"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Hole A1", exact: true }).click();
  await expect(
    page.getByText(/STRIP_L_1 · 5 directly connected holes/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Next step" }).click();
  await page.getByLabel("Mark this reference step complete").check();
  await expect(page.getByText(/^1\/[1-9]\d*$/)).toBeVisible();
  if (process.env.CIRCUITPILOT_QA_DIR)
    await page.screenshot({
      path: path.join(process.env.CIRCUITPILOT_QA_DIR, "layout.png"),
      fullPage: true,
    });
  await page.getByRole("button", { name: "Align a photo" }).click();
  await page
    .getByLabel("Upload circuit photo")
    .setInputFiles(path.join(__dirname, "fixtures/synthetic-calibration.png"));
  const canvas = page.getByRole("img", { name: "Photo calibration area" });
  await expect(canvas).toBeVisible();
  const bounds = (await canvas.boundingBox())!;
  for (const [x, y] of [
    [80, 40],
    [540, 40],
    [540, 440],
    [80, 440],
  ]) {
    await canvas.click({
      position: { x: (bounds.width * x) / 640, y: (bounds.height * y) / 480 },
    });
  }
  await page.getByRole("button", { name: "Align expected layout" }).click();
  await expect(page.getByText("Needs your confirmation")).toBeVisible();
  await expect(
    page.getByText("No trained detector is loaded.", { exact: false }).first(),
  ).toBeVisible();
  if (process.env.CIRCUITPILOT_QA_DIR)
    await page.screenshot({
      path: path.join(process.env.CIRCUITPILOT_QA_DIR, "photo.png"),
      fullPage: true,
    });
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Good builds start" }),
  ).toBeVisible();
  await page
    .locator(".project-nav")
    .getByRole("button", { name: "Browser LED test" })
    .click();
  await expect(page.getByText("Connectivity graph passed")).toBeVisible();
  await expect(page.getByText(/^1\/[1-9]\d*$/)).toBeVisible();
});

test("invalid netlist cannot produce a plan and mobile layout stays within viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const signup = await page.request.post("/api/v1/auth/register", {
    data: {
      email: `mobile-${Date.now()}@example.com`,
      password: "isolated-mobile-password",
    },
  });
  expect(signup.status()).toBe(201);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Good builds start" }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Circuit JSON" })
    .fill('{"schema_version":"9.0"}');
  await page
    .getByRole("button", { name: "Validate & generate reference layout" })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "schema_version" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await expect(page.getByText("Connectivity graph passed")).not.toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  if (process.env.CIRCUITPILOT_QA_DIR)
    await page.screenshot({
      path: path.join(process.env.CIRCUITPILOT_QA_DIR, "mobile.png"),
      fullPage: true,
    });
});
