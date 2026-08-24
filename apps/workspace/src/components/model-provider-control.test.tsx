import { QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ModelProviderConfigurationStatus } from "@xingwen/domain";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createTestRuntime } from "../test/runtime";
import { ModelProviderControl } from "./model-provider-control";

// jsdom does not implement scrollIntoView, which Radix listboxes use.
Element.prototype.scrollIntoView ??= () => undefined;

afterEach(() => {
  cleanup();
});

function renderControl() {
  const runtime = createTestRuntime();
  render(
    <QueryClientProvider client={runtime.queryClient}>
      <ModelProviderControl runtime={runtime} />
    </QueryClientProvider>,
  );
  return runtime;
}

const unconfigured: ModelProviderConfigurationStatus = {
  status: "unconfigured",
  revision: 0,
  source: null,
  preset: null,
  baseUrl: null,
  dashscopeBaseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
  model: null,
  apiKeyHint: null,
  verifiedAt: null,
  updatedAt: null,
  editable: true,
};

describe("ModelProviderControl", () => {
  it("keeps setup non-blocking and opens it from the persistent entry", async () => {
    const runtime = createTestRuntime();
    vi.spyOn(
      runtime.repositories.modelProvider,
      "getConfiguration",
    ).mockResolvedValue(unconfigured);
    render(
      <QueryClientProvider client={runtime.queryClient}>
        <ModelProviderControl runtime={runtime} />
      </QueryClientProvider>,
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(
      await screen.findByRole("button", { name: "配置模型服务" }),
    );
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText("Base URL")).toHaveValue(
      "https://dashscope.aliyuncs.com/compatible-mode/v1",
    );
    expect(screen.getByLabelText("Base URL")).toHaveAttribute("readonly");
    expect(screen.getByLabelText("模型 ID")).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: "后续配置" }));

    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });

  it("tests and saves one workspace-wide Qwen connection", async () => {
    const runtime = createTestRuntime();
    vi.spyOn(
      runtime.repositories.modelProvider,
      "getConfiguration",
    ).mockResolvedValue(unconfigured);
    const configure = vi
      .spyOn(runtime.repositories.modelProvider, "configure")
      .mockResolvedValue({
        ...unconfigured,
        status: "ready",
        source: "workspace",
        preset: "dashscope",
        baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: "research-model",
        apiKeyHint: "••••1234",
        verifiedAt: "2026-08-24T00:00:00Z",
        updatedAt: "2026-08-24T00:00:00Z",
      });
    render(
      <QueryClientProvider client={runtime.queryClient}>
        <ModelProviderControl runtime={runtime} />
      </QueryClientProvider>,
    );

    fireEvent.click(
      await screen.findByRole("button", { name: "配置模型服务" }),
    );
    await screen.findByRole("dialog");
    fireEvent.change(screen.getByLabelText("模型 ID"), {
      target: { value: "research-model" },
    });
    fireEvent.change(screen.getByLabelText("API 密钥"), {
      target: { value: "secret-key-1234" },
    });
    fireEvent.click(screen.getByRole("button", { name: "测试并保存" }));

    await waitFor(() => expect(configure).toHaveBeenCalledOnce());
    expect(configure).toHaveBeenCalledWith(
      {
        preset: "dashscope",
        baseUrl: null,
        model: "research-model",
        apiKey: "secret-key-1234",
      },
      0,
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });

  it("keeps configuration open when the connection test fails", async () => {
    const runtime = createTestRuntime();
    vi.spyOn(
      runtime.repositories.modelProvider,
      "getConfiguration",
    ).mockResolvedValue(unconfigured);
    vi.spyOn(runtime.repositories.modelProvider, "configure").mockRejectedValue(
      new Error("provider unavailable"),
    );
    render(
      <QueryClientProvider client={runtime.queryClient}>
        <ModelProviderControl runtime={runtime} />
      </QueryClientProvider>,
    );

    fireEvent.click(
      await screen.findByRole("button", { name: "配置模型服务" }),
    );
    fireEvent.change(screen.getByLabelText("模型 ID"), {
      target: { value: "research-model" },
    });
    fireEvent.change(screen.getByLabelText("API 密钥"), {
      target: { value: "secret-key-1234" },
    });
    fireEvent.click(screen.getByRole("button", { name: "测试并保存" }));

    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.getByRole("dialog")).toBeVisible();
  });

  it("keeps the model ID user-owned instead of exposing test fixtures", async () => {
    const runtime = createTestRuntime();
    vi.spyOn(
      runtime.repositories.modelProvider,
      "getConfiguration",
    ).mockResolvedValue(unconfigured);
    render(
      <QueryClientProvider client={runtime.queryClient}>
        <ModelProviderControl runtime={runtime} />
      </QueryClientProvider>,
    );

    fireEvent.click(
      await screen.findByRole("button", { name: "配置模型服务" }),
    );
    fireEvent.change(await screen.findByLabelText("模型 ID"), {
      target: { value: "qwen-plus" },
    });

    expect(screen.getByLabelText("模型 ID")).toHaveValue("qwen-plus");
    expect(screen.queryByText("qwen3.7-max")).not.toBeInTheDocument();
  });

  it("offers an editable custom OpenAI-compatible endpoint", async () => {
    const runtime = createTestRuntime();
    vi.spyOn(
      runtime.repositories.modelProvider,
      "getConfiguration",
    ).mockResolvedValue(unconfigured);
    render(
      <QueryClientProvider client={runtime.queryClient}>
        <ModelProviderControl runtime={runtime} />
      </QueryClientProvider>,
    );

    fireEvent.click(
      await screen.findByRole("button", { name: "配置模型服务" }),
    );
    fireEvent.click(screen.getByRole("combobox", { name: "连接方式" }));
    fireEvent.click(
      await screen.findByRole("option", {
        name: "自定义 OpenAI 兼容接口",
      }),
    );

    expect(screen.getByLabelText("Base URL")).not.toHaveAttribute("readonly");
    expect(screen.getByPlaceholderText("输入接口提供的模型 ID")).toBeVisible();
  });

  it("shows deployment-managed configuration without exposing an edit form", async () => {
    renderControl();

    fireEvent.click(
      await screen.findByRole("button", { name: "模型服务已连接" }),
    );

    expect(await screen.findByText("部署环境已配置")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "https://dashscope.aliyuncs.com/compatible-mode/v1",
    );
    expect(screen.queryByLabelText("API 密钥")).not.toBeInTheDocument();
  });
});
