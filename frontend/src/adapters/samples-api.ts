import {
  samplePreparationSchema,
  samplesResponseSchema,
  type SamplePreparation,
  type SampleSummary,
} from "@/domain/samples";
import { apiBaseUrl } from "@/lib/http";

async function readJson(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    throw new Error("The backend returned a non-JSON response.");
  }
  return response.json();
}

export async function getSamples(signal?: AbortSignal): Promise<SampleSummary[]> {
  const response = await fetch(`${apiBaseUrl}/api/samples`, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });
  const payload = await readJson(response);

  if (!response.ok) {
    throw new Error("The sample list could not be loaded.");
  }

  return samplesResponseSchema.parse(payload).samples;
}

export async function selectSample(
  sampleId: string,
  signal?: AbortSignal,
): Promise<SamplePreparation> {
  const response = await fetch(`${apiBaseUrl}/api/analyze`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ sample_id: sampleId }),
    signal,
  });
  const payload = await readJson(response);

  if (!response.ok) {
    throw new Error("The selected sample could not be prepared.");
  }

  return samplePreparationSchema.parse(payload);
}
