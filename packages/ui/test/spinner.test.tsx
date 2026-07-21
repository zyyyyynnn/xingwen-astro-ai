import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Spinner } from "../src/spinner";

describe("Spinner", () => {
  it("renders a status region with default label", () => {
    render(<Spinner />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText("加载中")).toBeInTheDocument();
  });

  it("supports a custom label", () => {
    render(<Spinner label="正在加载项目" />);
    expect(screen.getByText("正在加载项目")).toBeInTheDocument();
  });

  it("hides the dot from assistive tech", () => {
    const { container } = render(<Spinner />);
    expect(container.querySelector(".xw-spinner__dot")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });
});
