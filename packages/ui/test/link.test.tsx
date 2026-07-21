import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Link } from "../src/link";

describe("Link", () => {
  it("renders an anchor with href", () => {
    render(<Link href="/workspace">进入工作台</Link>);
    const link = screen.getByRole("link", { name: "进入工作台" });
    expect(link).toHaveAttribute("href", "/workspace");
  });

  it("adds external attributes when external is set", () => {
    render(
      <Link href="https://example.com" external>
        External
      </Link>,
    );
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("omits external attributes for internal links", () => {
    render(<Link href="/tour">Internal</Link>);
    const link = screen.getByRole("link");
    expect(link).not.toHaveAttribute("target");
  });
});
