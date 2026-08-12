import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Spinner } from "../src/spinner";

describe("Spinner", () => {
  it("renders the registry status icon with an accessible label", () => {
    render(<Spinner />);
    expect(screen.getByRole("status", { name: "加载中" })).toHaveClass(
      "xw-spinner",
    );
  });

  it("allows the consumer to provide its contextual accessible name", () => {
    render(<Spinner aria-label="正在加载项目" />);
    expect(
      screen.getByRole("status", { name: "正在加载项目" }),
    ).toBeInTheDocument();
  });

  it("renders a lucide icon instead of a hand-built loading ring", () => {
    const { container } = render(<Spinner />);
    expect(container.querySelector("svg[data-slot='spinner']")).toBeTruthy();
    expect(container.querySelector(".xw-spinner__dot")).toBeNull();
  });
});
