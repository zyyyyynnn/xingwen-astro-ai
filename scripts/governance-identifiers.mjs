const taskCodePattern = /\b[A-DX]-(?:\d+|[XN]+)\b/iu;
const phaseIdentifierPattern =
  /(?:\b(?:Phase|Stage)\s*[-:]?\s*(?:\d+|[IVXLCDM]+|[A-Z])\b|\bM\d\b|\bPR\s*[-:]?\s*\d+\s*\/\s*\d+\b|第\s*[一二三四五六七八九十0-9]+\s*(?:阶段|期)|阶段\s*[一二三四五六七八九十0-9]+|(?:^|[\s（(])期\s*[一二三四五六七八九十0-9]+|\bMilestones?\b|里程碑)/iu;

function withoutStableScientificIdentifiers(value) {
  return value
    .replace(/\b(?:Messier|梅西耶)\s+M\d+\b/giu, "")
    .replace(/\bCygnus\s+X-\d+\b/giu, "")
    .replace(/\b(?:carbon(?:\s+isotope)?|radiocarbon)\s+C-14\b/giu, "")
    .replace(/\bC-14\s+(?:isotope|dating)\b/giu, "")
    .replace(/碳(?:同位素)?\s*C-14/gu, "");
}

export function containsTaskCode(value) {
  return taskCodePattern.test(withoutStableScientificIdentifiers(value));
}

export function containsPhaseIdentifier(value) {
  return phaseIdentifierPattern.test(withoutStableScientificIdentifiers(value));
}
