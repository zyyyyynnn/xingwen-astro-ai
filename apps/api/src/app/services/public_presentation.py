"""Typed positive-contract projection shared by private and public presentation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import json

from app.schemas.core import (
    ArtifactKind,
    EvidenceDetail,
    PublicArtifactPresentation,
    PublicPresentationEntry,
    PublicPresentationFact,
    PublicPresentationGraphEdge,
    PublicPresentationGraphNode,
    PublicPresentationParagraph,
    PublicPresentationSection,
    PublicPresentationTable,
    PublicPresentationTableCell,
    PublicPresentationTableColumn,
    PublicPresentationTableRow,
    PublicPresentationTrace,
)
from app.schemas.data_artifacts import (
    DeclaredNullValue,
    DatasetArtifactCandidate,
    FieldDictionaryArtifactCandidate,
    MappedCanonicalValue,
    SourceCollectionArtifactCandidate,
)
from app.schemas.graph_artifact import GraphArtifactCandidate
from app.schemas.literature_claim import LiteratureClaimsCandidate
from app.schemas.literature_relation import LiteratureRelationsCandidate
from app.schemas.paper_collection import PaperCollection
from app.schemas.paper_summary import PaperSummaryArtifactContent
from app.schemas.scientific_skills import (
    AnalysisReportArtifactContent,
    LightCurveArtifactContent,
    ModelArtifactContent,
    ModelEvaluationArtifactContent,
    SpectrumArtifactContent,
    VisualizationArtifactContent,
)


class PresentationIntegrityError(ValueError):
    """Persisted Artifact content no longer closes over its Evidence registry."""


_PRESENTATION_TABLE_ROW_LIMIT = 100
_PRESENTATION_TABLE_COLUMN_LIMIT = 24


def _texts(values: Iterable[object]) -> tuple[str, ...]:
    return tuple(text for value in values if (text := str(value).strip()))


def _fact(label: str, *values: object) -> PublicPresentationFact | None:
    visible = _texts(value for value in values if value is not None)
    return PublicPresentationFact(label=label, values=visible) if visible else None


def _facts(
    *values: PublicPresentationFact | None,
) -> tuple[PublicPresentationFact, ...]:
    return tuple(value for value in values if value is not None)


def _evidence_by_target(
    evidence: Sequence[EvidenceDetail],
) -> dict[tuple[str, str], tuple[str, ...]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for item in evidence:
        grouped.setdefault((item.target_type, item.target_id), []).append(item.id)
    return {key: tuple(values) for key, values in grouped.items()}


def _data_evidence_key(
    *, target_id: str, locator: object, quote_or_value: object
) -> tuple[str, str, str]:
    return (
        target_id,
        json.dumps(locator, allow_nan=False, sort_keys=True, separators=(",", ":")),
        json.dumps(
            quote_or_value,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


def _data_persisted_evidence_ids(
    content: DatasetArtifactCandidate,
    evidence: Sequence[EvidenceDetail],
) -> dict[str, tuple[str, ...]]:
    persisted_by_key: dict[tuple[str, str, str], list[str]] = {}
    for item in evidence:
        if (
            item.target_type != "canonical_field"
            or item.evidence_type != "data_transformation"
        ):
            continue
        key = _data_evidence_key(
            target_id=item.target_id,
            locator=item.locator,
            quote_or_value=item.quote_or_value,
        )
        persisted_by_key.setdefault(key, []).append(item.id)

    resolved: dict[str, tuple[str, ...]] = {}
    for item in content.transformation_evidence:
        key = _data_evidence_key(
            target_id=item.canonical_field_id,
            locator=item.locator.model_dump(mode="json"),
            quote_or_value=(
                item.canonical_value
                if item.canonical_value is not None
                else item.raw_value
            ),
        )
        matches = persisted_by_key.get(key, ())
        if not matches:
            raise PresentationIntegrityError(
                "Dataset transformation Evidence mapping is incomplete"
            )
        resolved[item.evidence_id] = tuple(matches)
    return resolved


def _dataset_row_identity(row: object) -> str:
    identity = getattr(row, "canonical_row_identity")
    canonical_identity = getattr(identity, "canonical_identity", None)
    if canonical_identity:
        return str(canonical_identity)
    values = tuple(
        value.normalized_value
        for member in getattr(identity, "member_entities", ())
        for value in member.identity_values
    )
    return " / ".join(dict.fromkeys(values)) or str(getattr(row, "row_id"))


def _dataset_cell_reason(value: object) -> str:
    token = str(value)
    return {
        "not_in_source": "来源未提供",
        "not_measured": "未测量",
        "not_applicable": "不适用",
        "unresolved_conflict": "冲突未解决",
        "below_detection_limit": "低于检出限",
        "crossmatch alignment remains review_required": "交叉匹配待复核",
        "admitted document values conflict without a structured winner": (
            "来源值冲突，尚未确定规范值"
        ),
    }.get(token, token.replace("_", " "))


def _visible_unit(value: object) -> str | None:
    token = str(value)
    return None if token == "none" else token


def _data_type_label(value: object) -> str:
    return {
        "string": "文本",
        "integer": "整数",
        "number": "数值",
    }.get(str(value), "其他")


def _source_member_kind_label(value: object) -> str:
    return {
        "structured": "结构化数据",
        "source_table": "来源表格",
        "document": "文档",
    }.get(str(value), "其他")


def _declared_evidence_ids(
    evidence: Sequence[EvidenceDetail], declared_ids: Iterable[str]
) -> tuple[str, ...]:
    declared = tuple(declared_ids)
    available = {item.id for item in evidence}
    if not set(declared) <= available:
        raise PresentationIntegrityError(
            "Artifact content references Evidence outside its immutable version"
        )
    return declared


def _paper_summary_evidence_ids(
    evidence: Sequence[EvidenceDetail],
    *,
    declared_ids: Iterable[str],
    statement_targets: Mapping[str, frozenset[str]],
) -> tuple[str, ...]:
    by_summary_id: dict[str, str] = {}
    for item in evidence:
        if item.target_type != "paper_summary":
            continue
        summary_id = item.locator.get("summary_evidence_id")
        valid_targets = (
            statement_targets.get(summary_id) if isinstance(summary_id, str) else None
        )
        if (
            valid_targets is None
            or item.target_id not in valid_targets
            or summary_id in by_summary_id
        ):
            raise PresentationIntegrityError(
                "PaperSummary Evidence mapping is incomplete or ambiguous"
            )
        by_summary_id[summary_id] = item.id
    declared = tuple(declared_ids)
    if not set(declared) <= set(by_summary_id):
        raise PresentationIntegrityError(
            "PaperSummary statement references Evidence outside its immutable version"
        )
    return tuple(by_summary_id[item] for item in declared)


def _reason_label(value: object) -> str:
    token = str(value).rsplit(".", 1)[-1]
    return {
        "json_invalid": "返回内容无效",
        "schema_invalid": "结果结构无效",
        "input_artifact_version_unknown": "输入版本不存在",
        "input_schema_version_unsupported": "输入结构版本不受支持",
        "input_content_hash_mismatch": "输入内容校验失败",
        "paper_summary_artifact_version_unknown": "论文摘要版本不存在",
        "claim_not_found": "论点不存在",
        "claim_status_invalid": "论点状态不适用",
        "evidence_missing": "缺少证据",
        "evidence_not_found": "证据不存在",
        "evidence_inconsistent": "证据不一致",
        "source_snapshot_not_found": "来源快照不存在",
        "ownership_mismatch": "项目归属不一致",
        "normalization_unsafe": "规范化结果不安全",
        "duplicate": "内容重复",
        "duplicate_relation": "关系重复",
        "self_pair": "不能关联同一论点",
        "direction_mismatch": "关系方向不一致",
        "conditions_missing": "缺少成立条件",
        "conditions_conflict": "成立条件冲突",
        "object_incomparable": "研究对象不可比",
        "metric_incomparable": "指标不可比",
        "unit_incomparable": "单位不可比",
        "trace_missing": "缺少可核验推导",
        "trace_incomplete": "推导链不完整",
        "trace_unsafe": "推导内容不安全",
        "trace_direction_mismatch": "推导方向不一致",
        "trace_evidence_incomplete": "推导证据不完整",
        "confidence_undefined": "置信度未定义",
        "confidence_definition_unsupported": "置信度定义不受支持",
        "confidence_subject_mismatch": "置信度对象不一致",
        "confidence_decision_mismatch": "置信度结论不一致",
        "confidence_calibration_missing": "缺少置信度校准",
        "claim_not_accepted": "相关论点尚未采纳",
        "conditions_unresolved": "成立条件仍待确认",
        "confidence_not_evaluable": "置信度无法评估",
        "confidence_below_threshold": "置信度低于采纳阈值",
    }.get(token, token.replace("_", " "))


def _comparability(status: object, basis: str) -> str:
    label = {
        "comparable": "可比较",
        "not_applicable": "不适用",
        "incomparable": "不可比较",
    }.get(str(status), str(status))
    return f"{label}：{basis}"


def _token_label(value: object, labels: Mapping[str, str]) -> str:
    token = str(value)
    return labels.get(token, token.replace("_", " "))


_TASK_KIND_LABELS = {
    "classification": "分类",
    "regression": "回归",
    "forecast": "预测",
    "image_classification": "图像分类",
    "time_series_classification": "时间序列分类",
}
_SPLIT_STRATEGY_LABELS = {
    "random": "随机划分",
    "stratified": "分层划分",
    "group": "分组划分",
    "entity": "实体隔离划分",
    "time": "时间顺序划分",
}


def build_artifact_presentation(
    artifact_kind: ArtifactKind,
    raw_content: Mapping[str, object],
    evidence: Sequence[EvidenceDetail],
) -> PublicArtifactPresentation:
    """Validate through the existing Artifact authoring schema, then project.

    Every returned field is explicitly authored below. Unknown raw keys never
    enter the anonymous contract, so safety does not depend on key-name
    heuristics or a recursive JSON sanitizer.
    """

    evidence_by_target = _evidence_by_target(evidence)
    serialized_content = json.dumps(raw_content, allow_nan=False)

    if artifact_kind is ArtifactKind.dataset:
        content = DatasetArtifactCandidate.model_validate_json(serialized_content)
        persisted_evidence_ids = _data_persisted_evidence_ids(content, evidence)
        visible_columns = content.columns[:_PRESENTATION_TABLE_COLUMN_LIMIT]
        visible_column_ids = {column.field.field_id for column in visible_columns}
        return PublicArtifactPresentation(
            kind=artifact_kind,
            facts=_facts(
                _fact("记录", f"{content.row_count} 条"),
                _fact("字段", f"{content.field_count} 个"),
            ),
            entries=tuple(
                PublicPresentationEntry(
                    key=str(column.field.field_id),
                    title=column.field.meaning_zh or column.field.label_en,
                    paragraphs=(column.field.description,),
                    facts=_facts(
                        _fact("数据类型", _data_type_label(column.field.data_type)),
                        _fact("单位", _visible_unit(column.field.canonical_unit)),
                    ),
                    evidence_ids=evidence_by_target.get(
                        ("canonical_field", column.field.field_id), ()
                    ),
                )
                for column in content.columns
            ),
            tables=(
                PublicPresentationTable(
                    title="规范化数据",
                    columns=tuple(
                        PublicPresentationTableColumn(
                            key=column.field.field_id,
                            label=column.field.meaning_zh or column.field.label_en,
                            unit=_visible_unit(column.field.canonical_unit),
                        )
                        for column in visible_columns
                    ),
                    rows=tuple(
                        PublicPresentationTableRow(
                            key=row.row_id,
                            identity=_dataset_row_identity(row),
                            cells=tuple(
                                PublicPresentationTableCell(
                                    column_key=outcome.canonical_field_id,
                                    value=(
                                        outcome.canonical_value
                                        if isinstance(outcome, MappedCanonicalValue)
                                        else None
                                    ),
                                    status=(
                                        "mapped"
                                        if isinstance(outcome, MappedCanonicalValue)
                                        else "missing"
                                        if isinstance(outcome, DeclaredNullValue)
                                        else "unresolved"
                                    ),
                                    reason=(
                                        None
                                        if isinstance(outcome, MappedCanonicalValue)
                                        else _dataset_cell_reason(outcome.reason)
                                    ),
                                    evidence_ids=tuple(
                                        dict.fromkeys(
                                            persisted_id
                                            for evidence_id in outcome.transformation_evidence_ids
                                            for persisted_id in persisted_evidence_ids[
                                                evidence_id
                                            ]
                                        )
                                    ),
                                )
                                for outcome in row.fields
                                if outcome.canonical_field_id in visible_column_ids
                            ),
                        )
                        for row in content.rows[:_PRESENTATION_TABLE_ROW_LIMIT]
                    ),
                    total_row_count=content.row_count,
                    total_column_count=content.field_count,
                ),
            ),
        )
    if artifact_kind is ArtifactKind.field_dictionary:
        content = FieldDictionaryArtifactCandidate.model_validate_json(
            serialized_content
        )
        return PublicArtifactPresentation(
            kind=artifact_kind,
            facts=_facts(_fact("字段", f"{len(content.field_definitions)} 个")),
            entries=tuple(
                PublicPresentationEntry(
                    key=str(field.field_id),
                    title=field.meaning_zh or field.label_en,
                    paragraphs=(field.description,),
                    facts=_facts(
                        _fact("数据类型", _data_type_label(field.data_type)),
                        _fact("单位", _visible_unit(field.canonical_unit)),
                    ),
                    evidence_ids=evidence_by_target.get(
                        ("canonical_field", field.field_id), ()
                    ),
                )
                for field in content.field_definitions
            ),
        )
    if artifact_kind is ArtifactKind.source_collection:
        content = SourceCollectionArtifactCandidate.model_validate_json(
            serialized_content
        )
        return PublicArtifactPresentation(
            kind=artifact_kind,
            facts=_facts(_fact("来源", f"{len(content.members)} 个")),
            entries=tuple(
                PublicPresentationEntry(
                    key=f"source-{index}",
                    title=f"来源 {index + 1}",
                    facts=_facts(
                        _fact("来源类型", _source_member_kind_label(member.member_kind))
                    ),
                )
                for index, member in enumerate(content.members)
            ),
        )
    if artifact_kind is ArtifactKind.paper_collection:
        content = PaperCollection.model_validate_json(serialized_content)
        candidates = content.candidates or ()
        duplicate_counts = {
            group.duplicate_group_id: len(group.candidate_ids)
            for group in content.duplicate_groups
        }
        return PublicArtifactPresentation(
            kind=artifact_kind,
            facts=_facts(
                _fact("检索词", content.query.normalized_query_string),
                _fact("候选论文", f"{content.metrics.candidate_count} 篇"),
                _fact("已选论文", f"{content.metrics.selected_count} 篇"),
                _fact(
                    "来源失败",
                    f"{content.metrics.source_failure_count} 个"
                    if content.metrics.source_failure_count
                    else None,
                ),
            ),
            entries=tuple(
                PublicPresentationEntry(
                    key=str(candidate.candidate_id),
                    title=candidate.title,
                    external_url=(str(candidate.url) if candidate.url else None),
                    status="selected" if candidate.selected else "unselected",
                    assessment=f"相关度 {candidate.relevance_score:.2f}",
                    paragraphs=tuple(
                        value
                        for value in (
                            "、".join(candidate.authors) if candidate.authors else None,
                            str(candidate.year) if candidate.year is not None else None,
                            candidate.selection_reason or candidate.exclusion_reason,
                        )
                        if value
                    ),
                    facts=_facts(
                        _fact("DOI", candidate.doi),
                        _fact("arXiv", candidate.arxiv_id),
                        _fact(
                            "重复候选",
                            f"{duplicate_counts[candidate.duplicate_group_id]} 项"
                            if duplicate_counts.get(candidate.duplicate_group_id, 0) > 1
                            else None,
                        ),
                        _fact(
                            "来源冲突",
                            f"{len(candidate.conflicts)} 项"
                            if candidate.conflicts
                            else None,
                        ),
                    ),
                    evidence_ids=evidence_by_target.get(
                        ("paper_candidate", candidate.candidate_id), ()
                    ),
                )
                for candidate in candidates
            ),
        )
    if artifact_kind is ArtifactKind.paper_summary:
        content = PaperSummaryArtifactContent.model_validate_json(serialized_content)
        statement_targets = {
            evidence_id: frozenset(
                statement.statement_id
                for statement in content.statements()
                if evidence_id in statement.evidence_ids
            )
            for evidence_id in content.evidence_ids
        }
        section_values = (
            ("研究背景", content.background),
            ("研究方法", content.methodology),
            ("数据集", content.dataset),
            ("实验与结果", content.experiments),
            ("讨论", content.discussion),
            ("局限性", content.limitations),
            ("研究问题", content.research_questions),
        )
        sections = tuple(
            PublicPresentationSection(
                title=title,
                paragraphs=tuple(
                    PublicPresentationParagraph(
                        text=statement.text,
                        status=statement.status.value,
                        evidence_ids=_paper_summary_evidence_ids(
                            evidence,
                            declared_ids=statement.evidence_ids,
                            statement_targets=statement_targets,
                        ),
                    )
                    for statement in statements
                ),
            )
            for title, statements in section_values
            if statements
        )
        if content.source_conflicts:
            sections += (
                PublicPresentationSection(
                    title="来源核验",
                    paragraphs=tuple(
                        PublicPresentationParagraph(
                            text="来源信息存在冲突，请结合原始来源核验。",
                            status="unverifiable",
                            evidence_ids=_paper_summary_evidence_ids(
                                evidence,
                                declared_ids=(conflict.evidence_id,),
                                statement_targets=statement_targets,
                            ),
                        )
                        for conflict in content.source_conflicts
                    ),
                ),
            )
        return PublicArtifactPresentation(
            kind=artifact_kind,
            facts=_facts(
                _fact("论文", content.paper.title if content.paper else None),
                _fact(
                    "作者",
                    *(content.paper.authors if content.paper else ()),
                ),
                _fact("年份", content.paper.year if content.paper else None),
            ),
            sections=sections,
        )
    if artifact_kind is ArtifactKind.literature_claims:
        content = LiteratureClaimsCandidate.model_validate_json(serialized_content)
        return PublicArtifactPresentation(
            kind=artifact_kind,
            facts=_facts(_fact("论点", f"{len(content.claims)} 条")),
            entries=tuple(
                PublicPresentationEntry(
                    key=str(claim.claim_id),
                    title=claim.text,
                    status=claim.status.value,
                    assessment=f"{claim.claim_type.value} · {claim.polarity.value}",
                    facts=_facts(
                        _fact("指标", claim.metric),
                        _fact("单位", claim.unit),
                        _fact("不确定性", claim.uncertainty),
                        _fact("比较基准", claim.comparison_basis),
                        _fact("研究对象", *claim.objects),
                        _fact("适用范围", *claim.scope),
                        _fact("成立条件", *claim.conditions),
                        _fact("限定说明", *claim.qualifiers),
                        _fact("限制", *claim.limitations),
                        _fact(
                            "未采纳原因",
                            _reason_label(claim.rejection_reason)
                            if claim.rejection_reason
                            else None,
                        ),
                    ),
                    evidence_ids=evidence_by_target.get(("claim", claim.claim_id), ()),
                )
                for claim in content.claims
            ),
        )
    if artifact_kind is ArtifactKind.literature_relations:
        content = LiteratureRelationsCandidate.model_validate_json(serialized_content)
        claims = {str(claim.claim_id): claim.text for claim in content.claims}
        traces = {str(trace.trace_id): trace for trace in content.reasoning_traces}
        return PublicArtifactPresentation(
            kind=artifact_kind,
            facts=_facts(_fact("关系", f"{len(content.relations)} 条")),
            entries=tuple(
                PublicPresentationEntry(
                    key=str(relation.relation_id),
                    title=(
                        f"{claims.get(str(relation.source_claim_id), '起点论点未公开')} → "
                        f"{claims.get(str(relation.target_claim_id), '终点论点未公开')}"
                    ),
                    status=relation.status.value,
                    assessment=relation.relation_type.value,
                    facts=_facts(
                        _fact("成立条件", *relation.conditions),
                        _fact("条件冲突", *relation.condition_conflicts),
                        _fact("仍待确认", *relation.condition_uncertainties),
                        _fact("方向依据", relation.direction.basis),
                        _fact(
                            "对象可比性",
                            _comparability(
                                relation.comparability.object_status,
                                relation.comparability.object_basis,
                            ),
                        ),
                        _fact(
                            "指标可比性",
                            _comparability(
                                relation.comparability.metric_status,
                                relation.comparability.metric_basis,
                            ),
                        ),
                        _fact(
                            "单位可比性",
                            _comparability(
                                relation.comparability.unit_status,
                                relation.comparability.unit_basis,
                            ),
                        ),
                        _fact(
                            "置信度",
                            (
                                f"{relation.confidence.score:.2f}"
                                f"（采纳阈值 {relation.confidence.acceptance_threshold:.2f}）"
                                if relation.confidence
                                and relation.confidence.score is not None
                                else "无法评估"
                                if relation.confidence
                                else None
                            ),
                        ),
                        _fact(
                            "未采纳原因",
                            _reason_label(relation.rejection_reason)
                            if relation.rejection_reason
                            else None,
                        ),
                        _fact(
                            "待复核原因",
                            _reason_label(relation.review_reason)
                            if relation.review_reason
                            else None,
                        ),
                    ),
                    evidence_ids=evidence_by_target.get(
                        ("relation", relation.relation_id), ()
                    ),
                    reasoning_trace=(
                        PublicPresentationTrace(
                            conclusion=trace.conclusion,
                            steps=tuple(step.statement for step in trace.steps),
                            facts=_facts(
                                _fact("成立条件", *trace.conditions),
                                _fact("冲突", *trace.conflicts),
                                _fact("限制", *trace.limitations),
                            ),
                            evidence_ids=evidence_by_target.get(
                                ("relation", relation.relation_id), ()
                            ),
                        )
                        if relation.reasoning_trace_id is not None
                        and (trace := traces.get(str(relation.reasoning_trace_id)))
                        is not None
                        else None
                    ),
                )
                for relation in content.relations
            ),
        )
    if artifact_kind is ArtifactKind.graph:
        content = GraphArtifactCandidate.model_validate_json(serialized_content)
        return PublicArtifactPresentation(
            kind=artifact_kind,
            facts=_facts(
                _fact("研究对象", f"{len(content.nodes)} 个"),
                _fact("证据关系", f"{len(content.edges)} 条"),
            ),
            graph_nodes=tuple(
                PublicPresentationGraphNode(
                    key=str(node.node_id), kind=node.node_type.value, label=node.label
                )
                for node in content.nodes
            ),
            graph_edges=tuple(
                PublicPresentationGraphEdge(
                    key=str(edge.edge_id),
                    kind=edge.edge_type.value,
                    source_key=str(edge.source_node_id),
                    target_key=str(edge.target_node_id),
                    evidence_ids=evidence_by_target.get(
                        ("graph_edge", edge.edge_id), ()
                    ),
                )
                for edge in content.edges
            ),
        )
    if artifact_kind is ArtifactKind.analysis_report:
        content = AnalysisReportArtifactContent.model_validate_json(serialized_content)
        return PublicArtifactPresentation(
            kind=artifact_kind,
            summary=content.summary,
            facts=tuple(
                PublicPresentationFact(
                    label=metric.label,
                    values=(
                        f"{metric.value}{f' {metric.unit}' if metric.unit else ''}",
                    ),
                )
                for metric in content.metrics
            ),
            entries=tuple(
                PublicPresentationEntry(
                    key=str(finding.finding_id),
                    title=finding.title,
                    status=finding.status.value,
                    paragraphs=(finding.statement,),
                    evidence_ids=_declared_evidence_ids(evidence, finding.evidence_ids),
                )
                for finding in content.findings
            ),
            sections=(
                *(
                    (
                        PublicPresentationSection(
                            title="限制",
                            paragraphs=tuple(
                                PublicPresentationParagraph(text=value)
                                for value in content.limitations
                            ),
                        ),
                    )
                    if content.limitations
                    else ()
                ),
                *(
                    (
                        PublicPresentationSection(
                            title="待人工确认",
                            paragraphs=tuple(
                                PublicPresentationParagraph(text=value)
                                for value in content.human_required
                            ),
                        ),
                    )
                    if content.human_required
                    else ()
                ),
            ),
        )
    if artifact_kind is ArtifactKind.visualization:
        content = VisualizationArtifactContent.model_validate_json(serialized_content)
        return PublicArtifactPresentation(
            kind=artifact_kind,
            summary=content.description or "可视化结果已冻结。",
        )
    if artifact_kind is ArtifactKind.spectrum:
        content = SpectrumArtifactContent.model_validate_json(serialized_content)
        return PublicArtifactPresentation(
            kind=artifact_kind,
            facts=_facts(
                _fact("研究对象", content.object_name),
                _fact("采样", f"{content.sample_count} 点"),
                _fact("检测谱线", f"{len(content.detected_lines)} 条"),
                _fact("信噪比", content.signal_to_noise),
                _fact(
                    "数据单位",
                    f"波长 {content.wavelength_unit}",
                    f"通量 {content.flux_unit}",
                ),
                _fact("静止波长", content.rest_wavelength),
                _fact(
                    "径向速度",
                    f"{content.radial_velocity_km_s} km/s"
                    if content.radial_velocity_km_s is not None
                    else None,
                ),
            ),
            entries=tuple(
                PublicPresentationEntry(
                    key=str(line.line_id),
                    title=(
                        f"{_token_label(line.kind, {'emission': '发射', 'absorption': '吸收'})}谱线"
                    ),
                    facts=_facts(
                        _fact(
                            "观测波长",
                            f"{line.observed_wavelength} {content.wavelength_unit}",
                        ),
                        _fact("显著性", f"{line.significance_sigma} σ"),
                    ),
                )
                for line in content.detected_lines
            ),
        )
    if artifact_kind is ArtifactKind.light_curve:
        content = LightCurveArtifactContent.model_validate_json(serialized_content)
        return PublicArtifactPresentation(
            kind=artifact_kind,
            facts=_facts(
                _fact("研究对象", content.object_name),
                _fact("采样", f"{content.sample_count} 点"),
                _fact("有效采样", content.accepted_sample_count),
                _fact("剔除采样", content.rejected_sample_count),
                _fact("最佳周期", f"{content.best_period} {content.time_unit}"),
                _fact("最佳功率", content.best_power),
                _fact("误报概率", content.false_alarm_probability),
                _fact("时间尺度", content.time_scale.upper()),
                _fact(
                    "数值类型",
                    _token_label(
                        content.value_kind,
                        {
                            "relative_flux": "相对流量",
                            "flux": "流量",
                            "magnitude": "星等",
                        },
                    ),
                ),
                _fact("数值单位", content.value_unit),
                _fact(
                    "规范化",
                    _token_label(
                        content.normalization,
                        {
                            "median_division": "中值相除",
                            "median_subtraction": "中值相减",
                        },
                    ),
                ),
                _fact("持续时间", f"{content.duration} {content.time_unit}"),
                _fact(
                    "中位采样间隔",
                    f"{content.median_cadence} {content.time_unit}",
                ),
            ),
        )
    if artifact_kind is ArtifactKind.model_evaluation:
        content = ModelEvaluationArtifactContent.model_validate_json(serialized_content)
        return PublicArtifactPresentation(
            kind=artifact_kind,
            facts=(
                *_facts(
                    _fact("任务", _token_label(content.task_kind, _TASK_KIND_LABELS)),
                    _fact("算法", content.algorithm),
                    _fact(
                        "训练数据",
                        _token_label(
                            content.training_input.kind,
                            {
                                "dataset_artifact_version": "研究数据集",
                                "source_snapshot": "原始数据来源",
                            },
                        ),
                    ),
                    _fact("目标字段", content.target_field),
                    _fact("特征字段", *content.feature_fields),
                    _fact(
                        "划分方式",
                        _token_label(content.split.strategy, _SPLIT_STRATEGY_LABELS),
                    ),
                    _fact("划分字段", content.split.field),
                    _fact(
                        "交叉验证",
                        f"{content.split.cross_validation_folds} 折"
                        if content.split.cross_validation_folds is not None
                        else None,
                    ),
                    _fact("训练截止", content.split.train_cutoff),
                    _fact(
                        "数据划分",
                        f"训练 {content.split.train_fraction:.0%}",
                        f"验证 {content.split.validation_fraction:.0%}",
                        f"测试 {content.split.test_fraction:.0%}",
                    ),
                ),
                *tuple(
                    PublicPresentationFact(
                        label=metric.label,
                        values=(
                            f"{metric.value}{f' {metric.unit}' if metric.unit else ''}",
                        ),
                    )
                    for metric in content.metrics
                ),
                *tuple(
                    PublicPresentationFact(
                        label=f"基线：{metric.label}",
                        values=(
                            f"{metric.value}{f' {metric.unit}' if metric.unit else ''}",
                        ),
                    )
                    for metric in content.baseline_metrics
                ),
            ),
            sections=(
                PublicPresentationSection(
                    title="限制",
                    paragraphs=tuple(
                        PublicPresentationParagraph(text=value)
                        for value in content.limitations
                    ),
                ),
            )
            if content.limitations
            else (),
        )
    if artifact_kind is ArtifactKind.model_artifact:
        content = ModelArtifactContent.model_validate_json(serialized_content)
        return PublicArtifactPresentation(
            kind=artifact_kind,
            facts=_facts(
                _fact("任务", _token_label(content.task_kind, _TASK_KIND_LABELS)),
                _fact("算法", content.algorithm),
                _fact("输入", content.input_name),
                _fact(
                    "输入形状",
                    " × ".join(
                        "batch" if value is None else str(value)
                        for value in content.input_shape
                    ),
                ),
                _fact("输出", *content.output_names),
                _fact("目标字段", content.target_field),
                _fact("特征字段", *content.feature_fields),
            ),
            sections=(
                PublicPresentationSection(
                    title="限制",
                    paragraphs=tuple(
                        PublicPresentationParagraph(text=value)
                        for value in content.limitations
                    ),
                ),
            )
            if content.limitations
            else (),
        )
    return PublicArtifactPresentation(kind=artifact_kind)


__all__ = ["PresentationIntegrityError", "build_artifact_presentation"]
