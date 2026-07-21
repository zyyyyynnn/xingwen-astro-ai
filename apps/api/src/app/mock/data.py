"""P0 mock data for frontend/API contract integration."""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.dataset import ColumnInfo, DatasetResponse, QualityScore
from app.schemas.enums import (
    ClaimType,
    GraphEdgeType,
    GraphNodeType,
    LiteratureRelationType,
    PaperAcquisitionStatus,
    SourceType,
    StepStatus,
    TaskStatus,
)
from app.schemas.evidence import EvidenceResponse, Locator, SourceSnapshot
from app.schemas.graph import GraphEdge, GraphNode, GraphResponse
from app.schemas.paper import (
    PaperAcquisitionResponse,
    PaperAcquisitionRun,
    PaperCandidate,
    PaperItem,
    PaperSearchQuery,
    PapersResponse,
    PaperSummary,
)
from app.schemas.reasoning import (
    LiteratureClaim,
    LiteratureReasoningResponse,
    LiteratureRelation,
    ReasoningTrace,
    TraceStep,
)
from app.schemas.source import SourceRecordItem, SourcesResponse
from app.schemas.task import StepInfo, TaskStatusResponse

TASK_ID = "task_001"
NOW = datetime(2026, 7, 4, 10, 0, 0, tzinfo=timezone.utc)


def mock_task_status() -> TaskStatusResponse:
    return TaskStatusResponse(
        task_id=TASK_ID,
        goal="我想研究热木星候选体的轨道周期、半径、质量与宿主恒星温度之间的关系",
        case_key="exoplanet_host_star",
        status=TaskStatus.searching_papers,
        progress=55,
        used_cache=False,
        created_at=NOW,
        updated_at=datetime(2026, 7, 4, 10, 2, 30, tzinfo=timezone.utc),
        steps=[
            StepInfo(key="fetching_data", label="获取天文数据", status=StepStatus.completed, message="12个字段已提取"),
            StepInfo(key="cleaning_data", label="数据清洗与字段映射", status=StepStatus.completed, message="字段映射完成"),
            StepInfo(key="searching_papers", label="获取主案例论文", status=StepStatus.running, message="正在检索主案例相关论文候选"),
            StepInfo(key="summarizing_papers", label="生成文献摘要", status=StepStatus.pending, message=""),
            StepInfo(key="reasoning_literature", label="跨文献推理", status=StepStatus.pending, message=""),
            StepInfo(key="building_graph", label="构建学术图谱", status=StepStatus.pending, message=""),
        ],
    )


def mock_dataset() -> DatasetResponse:
    return DatasetResponse(
        dataset_id="dataset_001",
        task_id=TASK_ID,
        name="exoplanet_host_star_dataset",
        case_key="exoplanet_host_star",
        row_count=3,
        field_count=5,
        created_at=datetime(2026, 7, 4, 10, 3, 0, tzinfo=timezone.utc),
        columns=[
            ColumnInfo(name="pl_orbper", label="Orbital Period", unit="day", description="Planet orbital period", data_type="number", required=True, source_ids=["source_nasa_exoplanet_archive"], missing_rate=0.08, mapping_rule="NASA Exoplanet Archive pl_orbper"),
            ColumnInfo(name="pl_rade", label="Planet Radius", unit="R_earth", description="Planet radius", data_type="number", required=True, source_ids=["source_nasa_exoplanet_archive"], missing_rate=0.12, mapping_rule="NASA Exoplanet Archive pl_rade"),
            ColumnInfo(name="pl_bmass", label="Planet Mass", unit="M_earth", description="Planet mass", data_type="number", required=False, source_ids=["source_nasa_exoplanet_archive"], missing_rate=0.25, mapping_rule="NASA Exoplanet Archive pl_bmass"),
            ColumnInfo(name="hostname", label="Host Star Name", unit="", description="Host star identifier", data_type="string", required=True, source_ids=["source_nasa_exoplanet_archive"], missing_rate=0.0, mapping_rule="NASA Exoplanet Archive hostname"),
            ColumnInfo(name="st_teff", label="Stellar Effective Temperature", unit="K", description="Host star effective temperature", data_type="number", required=True, source_ids=["source_nasa_exoplanet_archive"], missing_rate=0.05, mapping_rule="NASA Exoplanet Archive st_teff"),
        ],
        rows=[
            {"object_id": "toi_001", "pl_orbper": 3.52, "pl_rade": 1.32, "pl_bmass": 0.89, "hostname": "TOI-001", "st_teff": 5600},
            {"object_id": "toi_002", "pl_orbper": 7.81, "pl_rade": 0.98, "pl_bmass": 0.65, "hostname": "TOI-002", "st_teff": 5200},
            {"object_id": "toi_003", "pl_orbper": 1.24, "pl_rade": 2.10, "pl_bmass": 3.45, "hostname": "TOI-003", "st_teff": 6100},
        ],
        quality_score=QualityScore(
            task_id=TASK_ID,
            field_coverage=0.86,
            missing_rate=0.14,
            source_completeness=1.0,
            unit_consistency=1.0,
            paper_acquisition_reproducibility=1.0,
            paper_summary_completeness=0.85,
            literature_relation_evidence_rate=1.0,
            graph_evidence_completeness=0.92,
            reproducibility=0.9,
        ),
    )


def mock_sources() -> SourcesResponse:
    return SourcesResponse(
        sources=[
            SourceRecordItem(
                id="source_nasa_exoplanet_archive",
                task_id=TASK_ID,
                type=SourceType.database,
                name="NASA Exoplanet Archive",
                url="https://exoplanetarchive.ipac.caltech.edu/",
                query="SELECT pl_orbper, pl_rade, pl_bmass, hostname, st_teff WHERE default_flag=1",
                retrieved_at=datetime(2026, 7, 4, 10, 1, 0, tzinfo=timezone.utc),
                cached=False,
                license_note="public archive",
            ),
            SourceRecordItem(
                id="source_ads_or_arxiv",
                task_id=TASK_ID,
                type=SourceType.paper_source,
                name="ADS/arXiv",
                url="https://ui.adsabs.harvard.edu/",
                query="exoplanet candidate host star orbital period radius mass temperature",
                retrieved_at=datetime(2026, 7, 4, 10, 5, 0, tzinfo=timezone.utc),
                cached=False,
                license_note=None,
            ),
        ],
    )


def mock_paper_acquisition() -> PaperAcquisitionResponse:
    return PaperAcquisitionResponse(
        query=PaperSearchQuery(
            query_id="paper_query_001",
            task_id=TASK_ID,
            case_key="exoplanet_host_star",
            keywords=["exoplanet candidate", "host star", "orbital period", "planet radius", "stellar temperature"],
            source_types=["paper_source"],
            query_string="exoplanet candidate host star orbital period radius mass temperature",
            filters={"year_from": 2015, "max_results": 20},
            created_at=datetime(2026, 7, 4, 10, 4, 0, tzinfo=timezone.utc),
        ),
        run=PaperAcquisitionRun(
            run_id="paper_run_001",
            task_id=TASK_ID,
            query_id="paper_query_001",
            status=PaperAcquisitionStatus.completed,
            candidate_count=3,
            selected_count=2,
            dedupe_rule="doi_or_title_year",
            used_cache=False,
            started_at=datetime(2026, 7, 4, 10, 4, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 7, 4, 10, 5, 30, tzinfo=timezone.utc),
        ),
        candidates=[
            PaperCandidate(
                candidate_id="paper_candidate_001",
                task_id=TASK_ID,
                run_id="paper_run_001",
                source_record_id="source_ads_or_arxiv",
                external_id="2304.12345",
                title="A Population Study of Hot Jupiter Orbital Parameters and Host Star Properties",
                authors=["Wang, L.", "Chen, X.", "Zhang, Y."],
                year=2023,
                doi="10.1093/mnras/stad1234",
                arxiv_id="2304.12345",
                url="https://arxiv.org/abs/2304.12345",
                abstract="We present a population study of hot Jupiter candidates...",
                relevance_score=0.92,
                dedupe_key="doi:10.1093/mnras/stad1234",
                selected=True,
                selection_reason="Directly studies hot Jupiter orbital period vs host star temperature",
            ),
            PaperCandidate(
                candidate_id="paper_candidate_002",
                task_id=TASK_ID,
                run_id="paper_run_001",
                source_record_id="source_ads_or_arxiv",
                external_id="2405.67890",
                title="The Correlation Between Exoplanet Radius and Stellar Irradiation",
                authors=["Martinez, R.", "Garcia, M."],
                year=2024,
                doi="10.3847/2041-8213/ad5678",
                arxiv_id="2405.67890",
                url="https://arxiv.org/abs/2405.67890",
                abstract="We analyze TESS data to examine the relationship...",
                relevance_score=0.85,
                dedupe_key="doi:10.3847/2041-8213/ad5678",
                selected=True,
                selection_reason="Relevant to planet radius vs stellar parameter analysis",
            ),
        ],
    )


def mock_papers() -> PapersResponse:
    return PapersResponse(
        papers=[
            PaperItem(
                paper_id="paper_001",
                candidate_id="paper_candidate_001",
                task_id=TASK_ID,
                title="A Population Study of Hot Jupiter Orbital Parameters and Host Star Properties",
                authors=["Wang, L.", "Chen, X.", "Zhang, Y."],
                year=2023,
                url="https://arxiv.org/abs/2304.12345",
                source_ids=["source_ads_or_arxiv"],
                summary=PaperSummary(
                    id="summary_001",
                    paper_id="paper_001",
                    research_goal="研究热木星轨道参数与宿主恒星温度的关系",
                    method="对热木星的 TESS 和地面观测数据进行统计分析",
                    dataset="NASA Exoplanet Archive + TESS 观测数据",
                    findings=["热木星轨道周期与宿主恒星温度呈弱负相关"],
                    limitations=["样本局限于太阳邻域，可能存在选择效应"],
                    future_work=["扩展到冷行星样本"],
                    evidence_ids=["evidence_001", "evidence_002"],
                    model_name="fixture",
                    prompt_version="paper-summary-v1",
                ),
                evidence_ids=["evidence_001", "evidence_002"],
            )
        ],
    )


def mock_literature_reasoning() -> LiteratureReasoningResponse:
    return LiteratureReasoningResponse(
        claims=[
            LiteratureClaim(
                claim_id="claim_001",
                task_id=TASK_ID,
                paper_id="paper_001",
                claim_type=ClaimType.finding,
                text="热木星轨道周期与宿主恒星温度呈弱负相关",
                normalized_text="热木星轨道周期与宿主恒星温度呈弱负相关",
                evidence_ids=["evidence_001"],
                confidence=0.85,
            ),
            LiteratureClaim(
                claim_id="claim_002",
                task_id=TASK_ID,
                paper_id="paper_001",
                claim_type=ClaimType.finding,
                text="高温恒星系统中更容易发现短周期热木星",
                normalized_text="高温恒星系统更容易发现短周期热木星",
                evidence_ids=["evidence_002"],
                confidence=0.78,
            ),
        ],
        relations=[
            LiteratureRelation(
                relation_id="relation_001",
                task_id=TASK_ID,
                source_claim_id="claim_001",
                target_claim_id="claim_002",
                relation_type=LiteratureRelationType.supports,
                reasoning_trace_id="trace_001",
                evidence_ids=["evidence_001", "evidence_002"],
                confidence=0.80,
            )
        ],
        traces=[
            ReasoningTrace(
                trace_id="trace_001",
                task_id=TASK_ID,
                relation_id="relation_001",
                steps=[
                    TraceStep(order=1, claim_id="claim_001", rationale="Paper A 报告轨道周期与恒星温度的相关性"),
                    TraceStep(order=2, claim_id="claim_002", rationale="Paper A 进一步指出高温恒星与短周期热木星相关"),
                ],
                evidence_ids=["evidence_001", "evidence_002"],
                model_name="fixture",
                prompt_version="literature-reasoning-v1",
            )
        ],
    )


def mock_graph() -> GraphResponse:
    return GraphResponse(
        nodes=[
            GraphNode(id="node_dataset", type=GraphNodeType.dataset, label="系外行星数据集", ref_id="dataset_001"),
            GraphNode(id="paper_001", type=GraphNodeType.paper, label="Paper A: 热木星轨道参数研究", ref_id="paper_001"),
            GraphNode(id="claim_001", type=GraphNodeType.claim, label="轨道周期与温度弱负相关", ref_id="claim_001"),
            GraphNode(id="claim_002", type=GraphNodeType.claim, label="高温恒星与短周期热木星", ref_id="claim_002"),
        ],
        edges=[
            GraphEdge(id="edge_dataset_paper1", source="node_dataset", target="paper_001", type=GraphEdgeType.provides_field, evidence_ids=["evidence_dataset_001"]),
            GraphEdge(id="edge_p1_c1", source="paper_001", target="claim_001", type=GraphEdgeType.supports_finding, evidence_ids=["evidence_001"]),
            GraphEdge(id="edge_c1_c2", source="claim_001", target="claim_002", type=GraphEdgeType.supports, relation_id="relation_001", reasoning_trace_id="trace_001", evidence_ids=["evidence_001", "evidence_002"]),
        ],
    )


def mock_evidence(eid: str) -> EvidenceResponse | None:
    store = {
        "evidence_dataset_001": EvidenceResponse(
            id="evidence_dataset_001",
            task_id=TASK_ID,
            type="database_query",
            source_id="source_nasa_exoplanet_archive",
            target_type="dataset",
            target_id="dataset_001",
            content="Dataset fields are mapped from NASA Exoplanet Archive query output for the fixed exoplanet host-star case.",
            locator=Locator(kind="query", value="NASA Exoplanet Archive TAP query"),
            quote_or_value="pl_orbper, pl_rade, pl_bmass, hostname, st_teff",
            extraction_method="mock_rule_mapping",
            source_snapshot=SourceSnapshot(retrieved_at=datetime(2026, 7, 4, 10, 1, 0, tzinfo=timezone.utc), query_hash="sha256:dataset-example"),
            confidence=0.95,
            created_at=datetime(2026, 7, 4, 10, 3, 0, tzinfo=timezone.utc),
        ),
        "evidence_001": EvidenceResponse(
            id="evidence_001",
            task_id=TASK_ID,
            type="paper_text",
            source_id="source_ads_or_arxiv",
            paper_id="paper_001",
            target_type="claim",
            target_id="claim_001",
            content="We find a weak negative correlation between orbital period and host star temperature.",
            locator=Locator(kind="abstract", value="abstract"),
            quote_or_value="weak negative correlation",
            extraction_method="mock_model_extraction",
            source_snapshot=SourceSnapshot(retrieved_at=datetime(2026, 7, 4, 10, 5, 0, tzinfo=timezone.utc), query_hash="sha256:paper-search-example"),
            confidence=0.95,
            created_at=datetime(2026, 7, 4, 10, 6, 0, tzinfo=timezone.utc),
        ),
        "evidence_002": EvidenceResponse(
            id="evidence_002",
            task_id=TASK_ID,
            type="paper_text",
            source_id="source_ads_or_arxiv",
            paper_id="paper_001",
            target_type="claim",
            target_id="claim_002",
            content="Systems with host star temperature > 6000K are more likely to host short-period hot Jupiters.",
            locator=Locator(kind="section", value="4. Discussion"),
            quote_or_value="T_eff > 6000K",
            extraction_method="mock_model_extraction",
            source_snapshot=SourceSnapshot(retrieved_at=datetime(2026, 7, 4, 10, 5, 0, tzinfo=timezone.utc), query_hash="sha256:paper-search-example"),
            confidence=0.90,
            created_at=datetime(2026, 7, 4, 10, 6, 30, tzinfo=timezone.utc),
        ),
    }
    return store.get(eid)
