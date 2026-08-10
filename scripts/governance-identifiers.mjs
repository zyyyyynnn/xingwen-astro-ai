const taskCodePattern = /\b[A-DX]-(?:\d+|[XN]+)\b/iu;
const repositoryTaskCodePattern =
  /(?:\b[A-DX]-(?:\d+|[XN]+)\b|\b[a-dx]-\d{2,}\b)/u;
const compactTaskCodePattern =
  /(?:(?<![A-Za-z0-9_])(?:[A-D]\d{2,}|X(?!(?:64|86)\b)\d{2,})(?![A-Za-z0-9_])|(?<![A-Za-z0-9])(?:[a-d]\d{2,}|x(?!(?:64|86)\b)\d{2,})(?![A-Za-z0-9]))/u;

const phaseIdentifierPattern =
  /(?:\b(?:Phase|Stage)(?:\s*[-:]\s*|\s+)(?:\d+|[IVXLCDM]+|[A-Z])\b|\bM\d+\b|\bPR\s*[-:]?\s*\d+\s*\/\s*\d+\b|第\s*[一二三四五六七八九十0-9]+\s*(?:阶段|期)|阶段\s*[一二三四五六七八九十0-9]+|(?:^|[\s（(])期\s*[一二三四五六七八九十0-9]+|\bMilestones?\b|里程碑)/iu;
const compactRepositoryPhaseIdentifierPattern =
  /(?<![A-Za-z0-9])phase(?:[_-]?\d+)(?![A-Za-z0-9])/iu;
const priorityPhaseIdentifierPattern = /\bP\d+\b/u;

// Repository pseudo-versions are implementation/work identities, not scientific
// technical versions. Dotted semantic versions (1.2.3 / v1.2.3), explicit
// external action tags and known library-major prose are excluded below.
const separatedPseudoVersionPattern =
  /(?:^|[._-])v\d+(?:_\d+)*(?!\.\d|[A-Za-z0-9])/iu;
const standalonePseudoVersionPattern =
  /(?<![/@A-Za-z0-9])v\d+(?:_\d+)*(?!\.\d|[A-Za-z0-9])/iu;
const camelPseudoVersionPattern = /\b[A-Za-z][A-Za-z0-9]*V\d+(?:_\d+)*\b/u;
const versionedDomainIdentityPattern =
  /\bVersioned\s+(?:[A-Z][A-Za-z]+\s+){0,3}(?:Artifact|Graph|Pipeline|Contract|Workflow)\b/u;

const repositoryProgressWordingPattern =
  /(?:\b(?:client|cache|module|package|boundary|integration)\s+placeholders?\b|\bplaceholders?\s+for\s+(?:later|future)\b|\b(?:later|future)[,\s]+(?:the\s+)?(?:[A-Za-z][\w-]*\s+){0,3}(?:apis?|adapters?|owners?|controls?|runtimes?|services?|clients?|ports?|pipelines?|modules?|tasks?|issues?|integrations?|publishers?|baselines?)\b|\b(?:later|future)\s+(?:quality|source|workspace)\b|\bnot implemented in\b|\bretained for future\b|\bcontract[- ]freeze(?:\s+change)?\b|\bparser contract change\b|\b[A-D]-(?:module|pipeline)\b|\b[A-D]\s+mapping changes?\b|未来.{0,24}(?:边界|消费端|适配器|接口|实现|启用|任务|模块)|后续.{0,16}(?:边界|持久化))/iu;
const repositoryTextPathPattern =
  /\.(?:astro|bat|cmd|conf|csv|css|env|example|html|ini|js|json|md|mjs|ps1|py|sh|sql|svg|toml|ts|tsx|txt|xml|ya?ml)$/iu;
const externalTechnicalIdentifierPattern = new RegExp(
  ["\\bcall_deepseek_v", "3_2\\b"].join(""),
  "giu",
);
const taskCodePathTokenPattern = /^(?:[a-d]\d+|x(?!(?:64|86)$)\d+)$/iu;
const phasePathTokenPattern = /^phase(?:[_-]?\d+)$/iu;

function withoutAllowedDomainIdentifiers(value) {
  return value
    .replace(externalTechnicalIdentifierPattern, "")
    .replace(/https?:\/\/[^\s)\]}>]+/giu, "")
    .replace(
      /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/giu,
      "",
    )
    .replace(/\bd="[^"]*"/giu, "")
    .replace(/(?:\\|%)x[0-9a-f]{2}/giu, "")
    .replace(/\bx(?:64|86)(?:_64)?\b/giu, "")
    .replace(/\bIAU\s+2015\s+Resolution\s+B3\b/giu, "")
    .replace(/\b(?:Messier|梅西耶)\s+M\d+\b/giu, "")
    .replace(/\bCygnus\s+X-\d+\b/giu, "")
    .replace(/\b(?:carbon(?:\s+isotope)?|radiocarbon)\s+C-14\b/giu, "")
    .replace(/\bC-14\s+(?:isotope|dating)\b/giu, "")
    .replace(/碳(?:同位素)?\s*C-14/gu, "")
    .replace(/\bA4\b(?=\s*(?:paper|@))/giu, "")
    .replace(/\bPydantic\s+v\d+\b/giu, "")
    .replace(/\b(?:actions|astral-sh)\/[A-Za-z0-9_.-]+@v\d+(?:\.\d+)*\b/giu, "")
    .replace(/\b[A-Za-z0-9_.-]+@v\d+(?:\.\d+)+\b/giu, "")
    .replace(/\bv\d+\.\d+(?:\.\d+)*(?:[-+][0-9A-Za-z.-]+)?\b/giu, "")
    .replace(
      /\bfailure[\s_-]+stage\s*[-:]?\s*(?:\d+|[IVXLCDM]+|[A-Z])\b/giu,
      "",
    )
    .replace(/失败阶段\s*[一二三四五六七八九十0-9]+/gu, "");
}

export function containsTaskCode(value) {
  const normalized = withoutAllowedDomainIdentifiers(value);
  return (
    taskCodePattern.test(normalized) || compactTaskCodePattern.test(normalized)
  );
}

export function containsRepositoryTaskCode(value) {
  const normalized = withoutAllowedDomainIdentifiers(value);
  return (
    repositoryTaskCodePattern.test(normalized) ||
    compactTaskCodePattern.test(normalized)
  );
}

export function containsRepositoryTaskCodePath(value) {
  return value
    .split(/[\\/_.-]/u)
    .some((token) => taskCodePathTokenPattern.test(token));
}

export function containsRepositoryPhaseIdentifier(value) {
  const normalized = withoutAllowedDomainIdentifiers(value);
  return (
    phaseIdentifierPattern.test(normalized) ||
    compactRepositoryPhaseIdentifierPattern.test(normalized) ||
    priorityPhaseIdentifierPattern.test(normalized)
  );
}

export function containsRepositoryPhaseIdentifierPath(value) {
  return value
    .split(/[\\/.]/u)
    .some((segment) => phasePathTokenPattern.test(segment));
}

export function containsRepositoryVersionLabel(value) {
  const normalized = withoutAllowedDomainIdentifiers(value);
  return (
    separatedPseudoVersionPattern.test(normalized) ||
    standalonePseudoVersionPattern.test(normalized) ||
    camelPseudoVersionPattern.test(normalized) ||
    versionedDomainIdentityPattern.test(normalized)
  );
}

export function containsRepositoryVersionLabelPath(value) {
  const normalized = value
    .replace(/(^|[\\/])api[\\/]v\d+(?=[\\/]|$)/giu, "$1api")
    .replace(/(^|[\\/])vendor(?:ed)?[\\/][^\s]*/giu, "");
  return normalized
    .split(/[\\/]/u)
    .some((segment) => containsRepositoryVersionLabel(segment));
}

export function containsRepositoryProgressWording(value) {
  return repositoryProgressWordingPattern.test(
    withoutAllowedDomainIdentifiers(value),
  );
}

export function isRepositoryTextPath(value) {
  return repositoryTextPathPattern.test(value);
}

export function isIssueOrPullRequestBodyTemplatePath(value) {
  const normalized = value.replaceAll("\\", "/");
  return (
    normalized.startsWith(".github/ISSUE_TEMPLATE/") ||
    normalized === ".github/pull_request_template.md" ||
    normalized.startsWith(".github/PULL_REQUEST_TEMPLATE/")
  );
}

export function containsProductionSchemaStatusWording(value, path) {
  const normalizedPath = path.replaceAll("\\", "/");
  const isProductionSchema =
    normalizedPath.startsWith("apps/api/src/app/schemas/") ||
    normalizedPath.startsWith("packages/schemas/generated/") ||
    normalizedPath.startsWith("packages/contracts/src/generated/");
  return isProductionSchema && /\bstubs?\b/iu.test(value);
}

export function containsPhaseIdentifier(value) {
  return phaseIdentifierPattern.test(withoutAllowedDomainIdentifiers(value));
}
