import { safeExternalUrl, type PublicEvidence } from "@xingwen/domain";
import type { EvidenceViewModel } from "@xingwen/research-adapter";
import { Button, Link } from "@xingwen/ui";
import { ExternalLink } from "@xingwen/ui/icons";

const SOURCE_TYPE_LABELS: Readonly<Record<string, string>> = {
  benchmark: "基准数据",
  catalog: "星表",
  database: "数据库",
  fixture: "演示数据",
  gaia_tap: "Gaia 星表",
  paper: "论文",
  paper_metadata: "论文元数据",
  research_input: "研究资料",
  research_input_upload: "用户上传",
  text: "用户输入",
  upload: "用户上传",
  url_fetch: "网页来源",
};

export interface EvidencePresentationModel {
  readonly quote: string;
  readonly locatorFacts: readonly {
    readonly label: string;
    readonly value: string;
  }[];
  readonly sourceType: string;
  readonly retrievedAt: string;
  readonly licenseNote: string;
  readonly sourceUrl: string | null;
  readonly pageIndex: number | null;
}

type EvidencePresentationInput = PublicEvidence | EvidenceViewModel;

function isPublicEvidence(
  evidence: EvidencePresentationInput,
): evidence is PublicEvidence {
  return evidence.locator !== null && "blockId" in evidence.locator;
}

function sourceUrl(metadata: Readonly<Record<string, unknown>>): string | null {
  for (const key of ["source_url", "url", "original_url", "landing_url"]) {
    const value = metadata[key];
    if (typeof value === "string") {
      const safe = safeExternalUrl(value);
      if (safe) return safe;
    }
  }
  return null;
}

function privateLocatorFacts(
  locator: EvidenceViewModel["locator"],
): EvidencePresentationModel["locatorFacts"] {
  if (!locator) return [];
  if (locator.kind === "paper_text") {
    return [
      ...(locator.page === null
        ? []
        : [{ label: "页码", value: String(locator.page + 1) }]),
      ...(locator.section ? [{ label: "章节", value: locator.section }] : []),
      ...(locator.paragraph === null
        ? []
        : [{ label: "段落", value: String(locator.paragraph) }]),
      ...(locator.range ? [{ label: "范围", value: locator.range }] : []),
    ];
  }
  if (locator.kind === "database_cell") {
    return [
      { label: "记录", value: locator.rowKey },
      { label: "字段", value: String(locator.field) },
    ];
  }
  if (locator.kind === "model_extraction") {
    return [{ label: "定位", value: "模型提取来源" }];
  }
  return [{ label: "定位", value: "推理链证据" }];
}

function publicLocatorFacts(
  locator: PublicEvidence["locator"],
): EvidencePresentationModel["locatorFacts"] {
  return [
    ...(locator.page === null
      ? []
      : [{ label: "页码", value: String(locator.page + 1) }]),
    ...(locator.section ? [{ label: "章节", value: locator.section }] : []),
    ...(locator.paragraph === null
      ? []
      : [{ label: "段落", value: String(locator.paragraph) }]),
    ...(locator.textRange ? [{ label: "范围", value: locator.textRange }] : []),
    ...(locator.field ? [{ label: "字段", value: locator.field }] : []),
    ...(locator.rowKey ? [{ label: "记录", value: locator.rowKey }] : []),
  ];
}

export function buildEvidencePresentation(
  evidence: EvidencePresentationInput,
): EvidencePresentationModel {
  const publicEvidence = isPublicEvidence(evidence) ? evidence : null;
  const source = evidence.source;
  return {
    quote: evidence.quoteOrValue ?? "该证据没有可公开展示的原文摘录。",
    locatorFacts: publicEvidence
      ? publicLocatorFacts(publicEvidence.locator)
      : privateLocatorFacts((evidence as EvidenceViewModel).locator),
    sourceType: source
      ? (SOURCE_TYPE_LABELS[source.sourceType] ?? "公开来源")
      : "来源未公开",
    retrievedAt: source?.retrievedAt ?? "",
    licenseNote: source?.licenseNote ?? "",
    sourceUrl: source ? sourceUrl(source.requestMetadata) : null,
    pageIndex:
      evidence.locator && evidence.locator.kind === "paper_text"
        ? evidence.locator.page
        : null,
  };
}

export function EvidencePresentationContent({
  presentation,
  onJumpToPaperPage,
}: {
  readonly presentation: EvidencePresentationModel;
  readonly onJumpToPaperPage?: (pageIndex: number) => void;
}) {
  return (
    <div className="evidence-presentation">
      <section>
        <h3>来源内容</h3>
        <blockquote>{presentation.quote}</blockquote>
      </section>
      {presentation.locatorFacts.length > 0 ? (
        <section>
          <h3>定位</h3>
          <dl>
            {presentation.locatorFacts.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
          {presentation.pageIndex !== null && onJumpToPaperPage ? (
            <Button
              size="small"
              variant="secondary"
              onClick={() => onJumpToPaperPage(presentation.pageIndex ?? 0)}
            >
              在论文中查看
            </Button>
          ) : null}
        </section>
      ) : null}
      <section>
        <h3>来源</h3>
        <p>
          {presentation.sourceType}
          {presentation.retrievedAt
            ? ` · 获取于 ${new Date(presentation.retrievedAt).toLocaleString()}`
            : ""}
        </p>
        {presentation.licenseNote ? <p>{presentation.licenseNote}</p> : null}
        {presentation.sourceUrl ? (
          <Link
            href={presentation.sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            打开原始来源
            <ExternalLink aria-hidden="true" />
          </Link>
        ) : null}
      </section>
    </div>
  );
}
