import type {
  ConfigureModelProviderRequest,
  ModelProviderConfigurationStatus as ModelProviderConfigurationStatusDto,
} from "@xingwen/contracts";
import type {
  ModelProviderConfigurationStatus,
  UtcIsoTimestamp,
} from "@xingwen/domain";

import { validateAndMap, type HttpClient } from "./http-client";
import type { ModelProviderRepository } from "./ports";

function mapStatus(
  value: ModelProviderConfigurationStatusDto,
): ModelProviderConfigurationStatus {
  return {
    status: value.status,
    revision: value.revision,
    source: value.source,
    preset: value.preset,
    baseUrl: value.base_url,
    dashscopeBaseUrl: value.dashscope_base_url,
    model: value.model,
    apiKeyHint: value.api_key_hint,
    verifiedAt: value.verified_at as UtcIsoTimestamp | null,
    updatedAt: value.updated_at as UtcIsoTimestamp | null,
    editable: value.editable,
  };
}

export function createModelProviderRepository(
  http: HttpClient,
): ModelProviderRepository {
  const path = "/api/model-provider/configuration";
  return {
    async getConfiguration() {
      const payload = await http.getRequired<unknown>(path);
      return validateAndMap(
        "ModelProviderConfigurationStatus",
        payload,
        mapStatus,
      );
    },
    async configure(input, expectedRevision) {
      const body: ConfigureModelProviderRequest = {
        preset: input.preset,
        base_url: input.baseUrl,
        model: input.model,
        api_key: input.apiKey,
      };
      const payload = await http.put<unknown>(path, body, {
        "If-Match": String(expectedRevision),
      });
      return validateAndMap(
        "ModelProviderConfigurationStatus",
        payload,
        mapStatus,
      );
    },
    async removeConfiguration(expectedRevision) {
      const payload = await http.deleteRequired<unknown>(path, {
        "If-Match": String(expectedRevision),
      });
      return validateAndMap(
        "ModelProviderConfigurationStatus",
        payload,
        mapStatus,
      );
    },
  };
}
