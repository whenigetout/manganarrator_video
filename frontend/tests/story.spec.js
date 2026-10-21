import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const source = fs.readFileSync(
  path.resolve("../fixtures/story-demo.md"),
  "utf8",
);
function take(seconds = 0.25) {
  const rate = 16000,
    n = Math.round(rate * seconds),
    buf = Buffer.alloc(44 + n * 2);
  buf.write("RIFF");
  buf.writeUInt32LE(buf.length - 8, 4);
  buf.write("WAVEfmt ", 8);
  buf.writeUInt32LE(16, 16);
  buf.writeUInt16LE(1, 20);
  buf.writeUInt16LE(1, 22);
  buf.writeUInt32LE(rate, 24);
  buf.writeUInt32LE(rate * 2, 28);
  buf.writeUInt16LE(2, 32);
  buf.writeUInt16LE(16, 34);
  buf.write("data", 36);
  buf.writeUInt32LE(n * 2, 40);
  return { name: "take.wav", mimeType: "audio/wav", buffer: buf };
}
test("import, edit, voices, images, render, persistence and mobile", async ({
  page,
  request,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("./#story");
  await page
    .getByLabel("Import manuscript", { exact: true })
    .setInputFiles({
      name: "demo.md",
      mimeType: "text/markdown",
      buffer: Buffer.from(source),
    });
  await expect(
    page.getByRole("heading", {
      name: "The Lantern Road",
      exact: true,
      level: 1,
    }),
  ).toBeVisible();
  const text = page.getByLabel("Text line-one");
  await text.fill("A lantern waited above the closed gate.");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Saved", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".story-source")).toContainText(
    "A lantern swung above",
  );
  await page.getByRole("button", { name: /Voices$/ }).click();
  for (const line of ["line-one", "line-two"]) {
    await page
      .getByLabel(`Audio ${line}`, { exact: true })
      .setInputFiles(take());
    await expect(page.getByRole("status")).toHaveCount(0);
  }
  await expect(page.locator("audio")).toHaveCount(2);
  await page.getByRole("button", { name: /Visuals$/ }).click();
  await page.getByRole("button", { name: "Add shot", exact: true }).click();
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Saved", exact: true }),
  ).toBeVisible();
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a8ioAAAAASUVORK5CYII=",
    "base64",
  );
  await page
    .locator('input[aria-label^="Image shot_"]')
    .setInputFiles({ name: "still.png", mimeType: "image/png", buffer: png });
  await expect(page.getByRole("status")).toHaveCount(0);
  await expect(page.locator(".story-shot img")).toBeVisible();
  await page.getByRole("button", { name: /Timeline$/ }).click();
  await expect(page.locator(".story-clip.audio")).toHaveCount(4);
  await page.getByRole("button", { name: /Export$/ }).click();
  await page.getByLabel("Resolution", { exact: true }).selectOption("640x360");
  await page
    .getByRole("button", { name: "Preview scene", exact: true })
    .click();
  await expect(page.locator(".story-render video")).toBeVisible({
    timeout: 60000,
  });
  await expect
    .poll(() =>
      page.locator(".story-render video").evaluate((v) => v.readyState),
    )
    .toBeGreaterThanOrEqual(2);
  const href = await page
    .getByRole("link", { name: "Production manifest" })
    .getAttribute("href");
  const manifest = await (await request.get(href)).json();
  expect(manifest.timeline.duration).toBeCloseTo(0.8, 2);
  expect(manifest.render.scene_id).toBe("gate");
  await page.reload();
  await page.getByRole("button", { name: /Manuscript$/ }).click();
  await expect(page.getByLabel("Text line-one")).toHaveValue(
    "A lantern waited above the closed gate.",
  );
  await page.getByRole("button", { name: "Lock scene", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Unlock scene", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Text line-one")).toBeDisabled();
  await page.screenshot({
    path: "../local_tmp/story-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "../local_tmp/story-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  expect(errors).toEqual([]);
});
