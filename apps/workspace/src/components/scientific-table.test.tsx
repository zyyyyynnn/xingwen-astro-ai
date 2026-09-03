import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { formatScientificUnit, ScientificTable } from "./scientific-table";

afterEach(cleanup);

it("presents live canonical units consistently in headers and evidence cells", () => {
  render(
    <ScientificTable
      caption="NASA 数据"
      maxRows={10}
      maxColumns={10}
      columns={[
        { key: "name", label: "名称", unit: "none", variant: "identity" },
        {
          key: "radius",
          label: "行星半径",
          unit: "earth_radius",
          variant: "numeric",
        },
        {
          key: "mass",
          label: "恒星质量",
          unit: "solar_mass",
          variant: "numeric",
        },
      ]}
      rows={[
        {
          id: "host",
          cells: {
            name: { value: "GJ 806", unit: "none" },
            radius: { value: "1.331", unit: "earth_radius" },
            mass: { value: "0.413", unit: "solar_mass" },
          },
        },
      ]}
    />,
  );
  expect(
    screen.getByRole("columnheader", { name: "名称" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "行星半径 (R⊕)" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "恒星质量 (M☉)" }),
  ).toBeInTheDocument();
  const table = screen.getByRole("table", { name: "NASA 数据" });
  expect(
    within(table).getByRole("cell", { name: /1\.331\s*R⊕/u }),
  ).toBeInTheDocument();
  expect(table).not.toHaveTextContent(/none|earth_radius|solar_mass/u);
});

it("formats supported canonical units without concealing unknown scientific units", () => {
  expect(
    [
      "none",
      "earth_radius",
      "earth_mass",
      "solar_radius",
      "solar_mass",
      "jupiter_radius",
      "jupiter_mass",
      "kelvin",
      "day",
      "degree",
      "dex",
    ].map(formatScientificUnit),
  ).toEqual(["", "R⊕", "M⊕", "R☉", "M☉", "R♃", "M♃", "K", "天", "°", "dex"]);
  expect(formatScientificUnit("erg/s/cm²")).toBe("erg/s/cm²");
});
