import { RouterProvider, createMemoryHistory } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { createAppRouter } from "./router";

test("renders a shared deep link without business data access", async () => {
  const history = createMemoryHistory({
    initialEntries: ["/share/demo-token"],
  });
  const testRouter = createAppRouter(history);

  render(<RouterProvider router={testRouter} />);

  expect(
    await screen.findByRole("heading", { name: "共享入口" }),
  ).toBeInTheDocument();
  expect(screen.getByText("入口标识：demo-token")).toBeInTheDocument();
});
