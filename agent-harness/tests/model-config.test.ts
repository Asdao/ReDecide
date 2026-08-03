import { describe, expect, it } from "vitest";
import { createConfiguredModel, readModelOverrideConfig } from "../src/model-config.js";

describe("model configuration", () => {
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
});
