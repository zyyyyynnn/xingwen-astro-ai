import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../src/select";

beforeAll(() => {
  // jsdom does not implement scrollIntoView, which the Radix listbox uses
  // while focusing options.
  Element.prototype.scrollIntoView ??= () => undefined;
});

describe("Select", () => {
  it("keeps the listbox closed until the trigger is activated", () => {
    render(
      <Select defaultValue="dss">
        <SelectTrigger aria-label="背景天图">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="dss">数字化巡天</SelectItem>
          <SelectItem value="gaia">Gaia DR3</SelectItem>
        </SelectContent>
      </Select>,
    );
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getByRole("combobox", { name: "背景天图" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("opens the listbox and commits the chosen option", () => {
    render(
      <Select defaultValue="dss">
        <SelectTrigger aria-label="背景天图">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="dss">数字化巡天</SelectItem>
          <SelectItem value="gaia">Gaia DR3</SelectItem>
        </SelectContent>
      </Select>,
    );

    fireEvent.click(screen.getByRole("combobox", { name: "背景天图" }));
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("option", { name: "Gaia DR3" }));
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(
      screen.getByRole("combobox", { name: "背景天图" }),
    ).toHaveTextContent("Gaia DR3");
  });
});
