import type { UtcIsoTimestamp } from "./value-types";

export type ModelProviderPreset = "dashscope" | "custom";
export type ModelProviderConfigurationSource = "deployment" | "workspace";

export interface ModelProviderConfigurationStatus {
  readonly status: "unconfigured" | "ready";
  readonly revision: number;
  readonly source: ModelProviderConfigurationSource | null;
  readonly preset: ModelProviderPreset | null;
  readonly baseUrl: string | null;
  readonly dashscopeBaseUrl: string;
  readonly model: string | null;
  readonly apiKeyHint: string | null;
  readonly verifiedAt: UtcIsoTimestamp | null;
  readonly updatedAt: UtcIsoTimestamp | null;
  readonly editable: boolean;
}

export interface ConfigureModelProviderInput {
  readonly preset: ModelProviderPreset;
  readonly baseUrl: string | null;
  readonly model: string;
  readonly apiKey: string;
}
