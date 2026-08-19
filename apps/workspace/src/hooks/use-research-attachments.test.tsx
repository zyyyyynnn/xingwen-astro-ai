import { describe, expect, it } from "vitest";

import { inferInputType } from "./use-research-attachments";

function file(name: string, type: string): File {
  return new File(["content"], name, { type });
}

describe("research attachment input type inference", () => {
  it("maps XLSX mime and extension to xlsx", () => {
    expect(
      inferInputType(
        file(
          "sample.xlsx",
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
      ),
    ).toBe("xlsx");
    expect(inferInputType(file("sample.xlsx", ""))).toBe("xlsx");
  });

  it("maps Parquet mime and extension to parquet", () => {
    expect(
      inferInputType(file("table.parquet", "application/vnd.apache.parquet")),
    ).toBe("parquet");
    expect(inferInputType(file("table.parquet", ""))).toBe("parquet");
  });

  it("maps ZIP to the image_dataset validation boundary", () => {
    expect(inferInputType(file("images.zip", "application/zip"))).toBe(
      "image_dataset",
    );
    expect(inferInputType(file("images.zip", ""))).toBe("image_dataset");
  });

  it("keeps FITS reachable through both mimes and extensions", () => {
    expect(inferInputType(file("frame.fits", "application/fits"))).toBe("fits");
    expect(inferInputType(file("frame.fit", "image/fits"))).toBe("fits");
    expect(inferInputType(file("frame.fts", ""))).toBe("fits");
  });

  it("does not pretend arbitrary archives or binaries are supported", () => {
    expect(inferInputType(file("archive.tar.gz", "application/gzip"))).toBe(
      null,
    );
    expect(inferInputType(file("archive.rar", "application/vnd.rar"))).toBe(
      null,
    );
    expect(
      inferInputType(file("program.exe", "application/octet-stream")),
    ).toBe(null);
  });
});
