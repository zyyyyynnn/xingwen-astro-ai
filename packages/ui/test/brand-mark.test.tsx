import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BrandMark } from "../src/brand-mark";

describe("BrandMark", () => {
  it("renders the Chinese primary title", () => {
    render(<BrandMark />);
    expect(screen.getByText("星文智析")).toBeInTheDocument();
  });

  it("hides the English subtitle by default", () => {
    render(<BrandMark />);
    expect(screen.queryByText("XINGWEN ASTRO AI")).not.toBeInTheDocument();
  });

  it("shows the English subtitle when requested", () => {
    render(<BrandMark showSubtitle />);
    expect(screen.getByText("XINGWEN ASTRO AI")).toBeInTheDocument();
  });
});
