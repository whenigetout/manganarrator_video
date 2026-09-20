import { test, expect } from "@playwright/test";

test("profiles reuse global setup and expose independent channel connections", async ({
  page,
}) => {
  const defaults = {
    preset: {},
    provider_id: "",
    prompt: "Accurate metadata",
    category: "10",
    tags: [],
    privacy: "private",
    language: "en",
    made_for_kids: false,
    contains_synthetic_media: false,
  };
  const profiles = [
    {
      ...defaults,
      id: "music",
      name: "Music profile",
      connected: true,
      connection_status: "connected",
      channel_name: "Music channel",
      channel_handle: "@music",
      channel_id: "UC_music",
    },
    {
      ...defaults,
      id: "stories",
      name: "Story profile",
      connected: false,
      connection_status: "disconnected",
    },
  ];
  const connects = [],
    disconnects = [];
  let globalImports = 0;
  await page.route("**/video/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (path.endsWith("/frame"))
      return route.fulfill({
        contentType: "image/png",
        body: Buffer.from(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jC1kAAAAASUVORK5CYII=",
          "base64",
        ),
      });
    let body = {};
    if (path.endsWith("/capabilities")) body = { nvenc: false };
    else if (
      path.endsWith("/jobs") ||
      path.endsWith("/runs") ||
      path.endsWith("/providers")
    )
      body = [];
    else if (path.endsWith("/configuration/google")) globalImports++;
    else if (path.endsWith("/configuration"))
      body = {
        google_configured: true,
        redirect_uri: "http://localhost/callback",
      };
    else if (path.endsWith("/profiles")) body = profiles;
    else if (path.endsWith("/connect") && method === "POST") {
      const id = path.split("/").at(-2);
      connects.push(id);
      const p = profiles.find((p) => p.id === id);
      Object.assign(p, {
        connected: true,
        connection_status: "connected",
        channel_name: id === "stories" ? "Story channel" : "Music channel",
        channel_handle: "@" + id,
        channel_id: "UC_" + id,
      });
      body = { url: "about:blank#authorized-" + id };
    } else if (path.endsWith("/disconnect") && method === "POST") {
      const id = path.split("/").at(-2);
      disconnects.push(id);
      Object.assign(
        profiles.find((p) => p.id === id),
        { connected: false, connection_status: "disconnected" },
      );
    }
    await route.fulfill({ json: body });
  });
  await page.goto("./");
  await page.getByTitle("Channel profiles and setup").click();
  const connection = page.getByRole("region", {
    name: "YouTube channel connection",
  });
  await expect(connection).toContainText("Connection status: Connected");
  await expect(connection).toContainText("Music channel");
  await expect(connection).toContainText("@music");
  await expect(connection).toContainText("UC_music");
  await expect(
    connection.getByRole("button", { name: "Reconnect YouTube channel" }),
  ).toBeEnabled();
  await page.getByLabel("Edit channel profile").selectOption("stories");
  await expect(connection).toContainText("Connection status: Disconnected");
  await expect(
    connection.getByRole("button", { name: "Disconnect", exact: true }),
  ).toBeDisabled();
  const popupEvent = page.waitForEvent("popup");
  await connection
    .getByRole("button", { name: "Connect YouTube channel", exact: true })
    .click();
  const popup = await popupEvent;
  await popup.close();
  await expect(connection).toContainText("@stories");
  await expect(connection).toContainText("UC_stories");
  await expect(connection).toContainText("Connection status: Connected");
  await connection
    .getByRole("button", { name: "Disconnect", exact: true })
    .click();
  await expect(connection).toContainText("Connection status: Disconnected");
  await expect(connection).toContainText("UC_stories");
  await page.getByLabel("Edit channel profile").selectOption("music");
  await expect(connection).toContainText("Connection status: Connected");
  profiles[0].connection_status = "needs_reauth";
  profiles[0].connected = false;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(connection).toContainText("Reconnect required");
  await expect(
    connection.getByRole("button", { name: "Reconnect YouTube channel" }),
  ).toBeEnabled();
  await page.getByLabel("Profile name", { exact: true }).fill("Unsaved edit");
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByLabel("Profile name", { exact: true })).toHaveValue(
    "Unsaved edit",
  );
  await page.screenshot({ path: "../local_tmp/channel-profile-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "../local_tmp/channel-profile-mobile.png" });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  expect(connects).toEqual(["stories"]);
  expect(disconnects).toEqual(["stories"]);
  expect(globalImports).toBe(0);
});
