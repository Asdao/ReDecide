import { describe, expect, it } from "vitest";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createConfiguredModel, loadDotEnv, readModelOverrideConfig } from "../src/model-config.js";

describe("model configuration", () => {
  it("leaves Pi's normal provider selection untouched when unset", () => {
    expect(readModelOverrideConfig({})).toBeUndefined();
  });

  it("uses DeepSeek defaults when only its standard key is configured", () => {
    const config = readModelOverrideConfig({ DEEPSEEK_API_KEY: "secret" });
    expect(config).toEqual({
      provider: "deepseek",
      model: "deepseek-v4-pro",
      apiKey: "secret",
    });
  });

  it("supports an explicit provider, model, and compatible gateway", () => {
    const config = readModelOverrideConfig({
      HARNESS_MODEL_PROVIDER: "deepseek",
      HARNESS_MODEL: "deepseek-v4-pro",
      HARNESS_MODEL_BASE_URL: "https://gateway.example/v1",
      HARNESS_MODEL_API_KEY: "secret",
    });
    expect(config).toEqual({
      provider: "deepseek",
      model: "deepseek-v4-pro",
      baseUrl: "https://gateway.example/v1",
      apiKey: "secret",
    });
  });

  it("accepts an OpenAI-compatible vendor model alias", () => {
    const config = readModelOverrideConfig({
      HARNESS_MODEL_PROVIDER: "deepseek",
      HARNESS_MODEL: "deepseek-v3-flash",
      HARNESS_MODEL_BASE_URL: "https://api.deepseek.com",
      HARNESS_MODEL_API: "openai-completions",
      DEEPSEEK_API_KEY: "secret",
    });
    expect(config).toEqual({
      provider: "deepseek",
      model: "deepseek-v3-flash",
      baseUrl: "https://api.deepseek.com",
      apiKey: "secret",
      api: "openai-completions",
    });
  });

  it("fails closed for an invalid gateway URL", () => {
    expect(() => readModelOverrideConfig({
      HARNESS_MODEL_PROVIDER: "deepseek",
      HARNESS_MODEL: "deepseek-v4-pro",
      HARNESS_MODEL_BASE_URL: "file:///tmp/model",
    })).toThrow("HARNESS_MODEL_BASE_URL must use http or https");
  });

  it("selects a built-in DeepSeek model without writing Pi config files", async () => {
    const configured = await createConfiguredModel({
      HARNESS_MODEL_PROVIDER: "deepseek",
      HARNESS_MODEL: "deepseek-v4-pro",
    });
    expect(configured?.model).toMatchObject({ provider: "deepseek", id: "deepseek-v4-pro" });
  });

  it("registers an unknown DeepSeek model in memory when a compatible endpoint is configured", async () => {
    const configured = await createConfiguredModel({
      HARNESS_MODEL_PROVIDER: "deepseek",
      HARNESS_MODEL: "deepseek-v3-flash",
      HARNESS_MODEL_BASE_URL: "https://api.deepseek.com",
      HARNESS_MODEL_API: "openai-completions",
      DEEPSEEK_API_KEY: "secret",
    });
    expect(configured?.model).toMatchObject({ provider: "deepseek", id: "deepseek-v3-flash" });
  });

  it("loads quoted dotenv values without overwriting deployment env", () => {
    const directory = mkdtempSync(join(tmpdir(), "cs2-harness-"));
    const path = join(directory, ".env");
    const original = process.env.HARNESS_TEST_EXISTING;
    process.env.HARNESS_TEST_EXISTING = "deployment-value";
    try {
      writeFileSync(path, "HARNESS_TEST_QUOTED=\"hello world\"\nHARNESS_TEST_EXISTING=local-value\n");
      loadDotEnv([path]);
      expect(process.env.HARNESS_TEST_QUOTED).toBe("hello world");
      expect(process.env.HARNESS_TEST_EXISTING).toBe("deployment-value");
    } finally {
      delete process.env.HARNESS_TEST_QUOTED;
      if (original === undefined) delete process.env.HARNESS_TEST_EXISTING;
      else process.env.HARNESS_TEST_EXISTING = original;
      rmSync(directory, { recursive: true, force: true });
    }
  });
});
