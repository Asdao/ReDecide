import { existsSync, readFileSync } from "node:fs";
import { ModelRuntime } from "@earendil-works/pi-coding-agent";

export interface ModelOverrideConfig {
  readonly provider: string;
  readonly model: string;
  readonly baseUrl?: string;
  readonly apiKey?: string;
  /** API adapter used when registering a model absent from Pi's built-in catalog. */
  readonly api?: "openai-completions";
}

export interface ConfiguredModel {
  readonly modelRuntime: ModelRuntime;
  readonly model: unknown;
}

/**
 * Resolve an optional model override without ever logging the credential.
 *
 * DeepSeek is a built-in Pi provider. Setting DEEPSEEK_API_KEY therefore
 * enables a convenient default, while HARNESS_* variables can select another
 * built-in provider or redirect one through a compatible gateway.
 */
export function readModelOverrideConfig(env: NodeJS.ProcessEnv = process.env): ModelOverrideConfig | undefined {
  const explicitProvider = clean(env.HARNESS_MODEL_PROVIDER);
  const explicitModel = clean(env.HARNESS_MODEL);
  const explicitBaseUrl = clean(env.HARNESS_MODEL_BASE_URL);
  const explicitApiKey = clean(env.HARNESS_MODEL_API_KEY);
  const explicitApi = clean(env.HARNESS_MODEL_API);
  const deepSeekKey = clean(env.DEEPSEEK_API_KEY);
  const provider = explicitProvider ?? (deepSeekKey ? "deepseek" : undefined);
  const model = explicitModel ?? (provider === "deepseek" ? "deepseek-v4-pro" : undefined);
  const apiKey = explicitApiKey ?? (provider === "deepseek" ? deepSeekKey : undefined);

  if (!provider && !model && !explicitBaseUrl && !apiKey) return undefined;
  if (!provider) throw new Error("HARNESS_MODEL_PROVIDER is required when configuring a model override");
  if (!model) throw new Error("HARNESS_MODEL is required when configuring a model override");
  if (explicitBaseUrl !== undefined) validateBaseUrl(explicitBaseUrl);
  if (explicitApi !== undefined && explicitApi !== "openai-completions") {
    throw new Error("HARNESS_MODEL_API must be openai-completions");
  }
  return {
    provider,
    model,
    ...(explicitBaseUrl === undefined ? {} : { baseUrl: explicitBaseUrl }),
    ...(apiKey === undefined ? {} : { apiKey }),
    ...(explicitApi === undefined ? {} : { api: "openai-completions" as const }),
  };
}

/** Build the Pi runtime and select the configured model, if one was requested. */
export async function createConfiguredModel(
  env: NodeJS.ProcessEnv = process.env,
): Promise<ConfiguredModel | undefined> {
  const config = readModelOverrideConfig(env);
  if (!config) return undefined;

  // Null modelsPath keeps model configuration in memory; a web server should
  // not write Pi's interactive-user configuration into the host home folder.
  const modelRuntime = await ModelRuntime.create({ modelsPath: null });
  const builtInModel = modelRuntime.getModel(config.provider, config.model);
  if (config.baseUrl !== undefined) {
    if (builtInModel !== undefined) {
      // A base URL alone overlays a built-in provider while preserving its
      // model catalog and API implementation.
      modelRuntime.registerProvider(config.provider, { baseUrl: config.baseUrl });
    } else {
      // Pi's catalog does not yet name every vendor release (for example a
      // DeepSeek V3 Flash deployment). Register that exact model as a small
      // OpenAI-compatible adapter instead of requiring a global models file.
      modelRuntime.registerProvider(config.provider, {
        baseUrl: config.baseUrl,
        api: config.api ?? "openai-completions",
        models: [{
          id: config.model,
          name: config.model,
          reasoning: false,
          input: ["text"],
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
          contextWindow: 128_000,
          maxTokens: 8_192,
          compat: { supportsDeveloperRole: false },
        }],
      });
    }
  }
  if (config.apiKey !== undefined) {
    await modelRuntime.setRuntimeApiKey(config.provider, config.apiKey);
  }
  const model = modelRuntime.getModel(config.provider, config.model);
  if (!model) {
    const available = modelRuntime.getModels(config.provider).map((candidate) => candidate.id).join(", ");
    throw new Error(`Configured model not found: ${config.provider}/${config.model}${available ? `. Available: ${available}` : ""}`);
  }
  return { modelRuntime, model };
}

/** Load simple KEY=value files without overwriting deployment-provided env vars. */
export function loadDotEnv(paths: readonly string[]): void {
  for (const path of paths) {
    if (!path) continue;
    if (!existsSync(path)) continue;
    const content = readFileSync(path, "utf8") as string;
    for (const line of content.split(/\r?\n/u)) {
      const match = /^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/u.exec(line);
      if (!match || Object.prototype.hasOwnProperty.call(process.env, match[1])) continue;
      process.env[match[1]] = parseEnvValue(match[2]);
    }
  }
}

function clean(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

function validateBaseUrl(value: string): void {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error("HARNESS_MODEL_BASE_URL must be an absolute http(s) URL");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("HARNESS_MODEL_BASE_URL must use http or https");
  }
}

function parseEnvValue(value: string): string {
  if (value.length >= 2) {
    const first = value[0];
    const last = value[value.length - 1];
    if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
      return value.slice(1, -1);
    }
  }
  return value.replace(/\s+#.*$/u, "").trim();
}
