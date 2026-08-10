import {
  containsPhaseIdentifier,
  containsTaskCode,
} from "./governance-identifiers.mjs";

const allowedMetadataFields = new Set([
  "Authority",
  "Scope",
  "Authoring source",
  "Applies to",
]);

const lifecycleMetadataFields = new Set([
  "Status",
  "Issue",
  "Superseded by",
  "Time range",
  "Implementation",
  "Current runtime",
  "Target runtime",
  "Current model",
  "Target model",
  "Current",
  "Pending",
  "Progress",
]);

function tableCells(line) {
  const cells = [];
  let current = "";
  let escaped = false;

  for (const character of line.trim()) {
    if (escaped) {
      current += character;
      escaped = false;
    } else if (character === "\\") {
      current += character;
      escaped = true;
    } else if (character === "|") {
      cells.push(current.trim());
      current = "";
    } else {
      current += character;
    }
  }
  cells.push(current.trim());
  if (cells[0] === "") cells.shift();
  if (cells.at(-1) === "") cells.pop();
  return cells;
}

function isDelimiterRow(line) {
  if (!line.includes("|")) return false;
  const cells = tableCells(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/u.test(cell));
}

export function inspectMarkdown(
  content,
  { requireSingleH1 = true, requireAuthority = false } = {},
) {
  const lines = content.split(/\r?\n/u);
  const errors = [];
  const links = [];
  const mermaidBlocks = [];
  const metadata = {};
  const metadataKeys = [];
  let fence = null;
  let mermaid = null;
  let previousHeading = 0;
  let h1Count = 0;
  let tableColumns = null;
  let reachedBody = false;
  let inLeadingMetadataTable = false;
  let leadingMetadataTableDone = false;

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const lineNumber = index + 1;
    const fenceMatch = /^\s*(`{3,}|~{3,})(.*)$/u.exec(line);
    if (fenceMatch) {
      const marker = fenceMatch[1];
      if (!fence) {
        fence = {
          character: marker[0],
          length: marker.length,
          line: lineNumber,
        };
        if (fenceMatch[2].trim().toLowerCase() === "mermaid") {
          mermaid = { line: lineNumber, lines: [] };
        }
      } else if (
        marker[0] === fence.character &&
        marker.length >= fence.length &&
        fenceMatch[2].trim() === ""
      ) {
        if (mermaid) mermaidBlocks.push(mermaid);
        fence = null;
        mermaid = null;
      } else if (mermaid) {
        mermaid.lines.push(line);
      }
      continue;
    }
    if (fence) {
      if (mermaid) mermaid.lines.push(line);
      continue;
    }

    const heading = /^(#{1,6})\s+\S/u.exec(line);
    if (heading) {
      const level = heading[1].length;
      if (level === 1) h1Count += 1;
      if (level >= 2) {
        reachedBody = true;
        if (inLeadingMetadataTable) {
          inLeadingMetadataTable = false;
          leadingMetadataTableDone = true;
        }
      }
      if (previousHeading > 0 && level > previousHeading + 1) {
        errors.push(
          `line ${lineNumber}: heading level jumps from H${previousHeading} to H${level}`,
        );
      }
      previousHeading = level;
    }

    if (index > 0 && isDelimiterRow(line)) {
      tableColumns = tableCells(lines[index - 1]).length;
      if (tableColumns !== tableCells(line).length) {
        errors.push(
          `line ${lineNumber}: table delimiter column count differs from its header`,
        );
      }
      if (!reachedBody && !leadingMetadataTableDone) {
        inLeadingMetadataTable = true;
      }
      continue;
    }
    if (tableColumns !== null) {
      if (line.trim().startsWith("|")) {
        const columns = tableCells(line).length;
        if (columns !== tableColumns) {
          errors.push(
            `line ${lineNumber}: table has ${columns} columns; expected ${tableColumns}`,
          );
        }
      } else if (line.trim() !== "") {
        tableColumns = null;
      }
    }

    if (inLeadingMetadataTable) {
      if (line.trim().startsWith("|")) {
        const cells = tableCells(line);
        if (cells.length >= 2) {
          const key = cells[0];
          metadata[key] = cells[1];
          metadataKeys.push(key);
        }
      } else if (line.trim() !== "") {
        inLeadingMetadataTable = false;
        leadingMetadataTableDone = true;
      }
    }

    for (const match of line.matchAll(/!?\[[^\]]*\]\(([^)]+)\)/gu)) {
      links.push({ line: lineNumber, target: match[1].trim() });
    }
  }

  if (fence) errors.push(`line ${fence.line}: code fence is not closed`);
  if (requireSingleH1 && h1Count !== 1) {
    errors.push(`document must contain exactly one H1; found ${h1Count}`);
  }

  for (const key of metadataKeys) {
    if (lifecycleMetadataFields.has(key)) {
      errors.push(`metadata field belongs to Git/GitHub history or status: ${key}`);
    } else if (!allowedMetadataFields.has(key)) {
      errors.push(`metadata field is not on the stable allowlist: ${key}`);
    }
  }
  if (requireAuthority && !metadata.Authority) {
    errors.push("missing Authority metadata");
  }

  for (const [index, line] of lines.entries()) {
    const lineNumber = index + 1;
    if (containsTaskCode(line)) {
      errors.push(
        `line ${lineNumber}: task code is not allowed in governed Markdown`,
      );
    }
    if (containsPhaseIdentifier(line)) {
      errors.push(
        `line ${lineNumber}: phase identifier is not allowed in governed Markdown`,
      );
    }
    if (/^\s*(?:<<<<<<<|=======|>>>>>>>)\s*$/u.test(line)) {
      errors.push(`line ${lineNumber}: merge-conflict marker is not allowed`);
    }
    if (/\b(?:PR|Issue)\s*#\d+\b/iu.test(line)) {
      errors.push(
        `line ${lineNumber}: PR/Issue work-state reference is not allowed in governed Markdown`,
      );
    }
  }

  return { errors, links, mermaidBlocks, metadata };
}
