const allowedStatuses = new Set([
  "Proposed",
  "Accepted",
  "Superseded",
  "Archived",
  "Reference",
]);

function tableCells(line) {
  const cells = [];
  let current = "";
  let escaped = false;
  let codeTicks = 0;

  for (const character of line.trim()) {
    if (escaped) {
      current += character;
      escaped = false;
    } else if (character === "\\") {
      current += character;
      escaped = true;
    } else if (character === "`") {
      codeTicks = codeTicks === 0 ? 1 : 0;
      current += character;
    } else if (character === "|" && codeTicks === 0) {
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

export function inspectMarkdown(content, { requireSingleH1 = true } = {}) {
  const lines = content.split(/\r?\n/u);
  const errors = [];
  const links = [];
  const mermaidBlocks = [];
  const metadata = {};
  let fence = null;
  let mermaid = null;
  let previousHeading = 0;
  let h1Count = 0;
  let tableColumns = null;

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

    for (const match of line.matchAll(/!?\[[^\]]*\]\(([^)]+)\)/gu)) {
      links.push({ line: lineNumber, target: match[1].trim() });
    }

    const metadataRow = /^\|\s*(Status|Authority)\s*\|\s*(.*?)\s*\|\s*$/u.exec(
      line,
    );
    if (metadataRow) metadata[metadataRow[1]] = metadataRow[2];
  }

  if (fence) errors.push(`line ${fence.line}: code fence is not closed`);
  if (requireSingleH1 && h1Count !== 1) {
    errors.push(`document must contain exactly one H1; found ${h1Count}`);
  }
  if (metadata.Status && !allowedStatuses.has(metadata.Status)) {
    errors.push(`metadata Status is not recognized: ${metadata.Status}`);
  }
  return { errors, links, mermaidBlocks, metadata };
}
