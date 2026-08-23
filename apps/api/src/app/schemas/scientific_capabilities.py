"""Single pure capability authoring source for bounded scientific skills.

This module intentionally imports nothing (not even Pydantic): the runtime
``ScientificSkillRegistry`` in ``services/scientific_skills`` and the contract
admission in ``app.schemas.core`` both consume this table, so there is exactly
one capability truth with multiple projections instead of re-listed skill ids.

Parameter models list the authoritative handler surface: the ``reject_unknown``
allowlist of each skill implementation together with the parameters the
``ScientificInputResolver`` injects for bound inputs. ``produced_artifact_kinds``
uses the public ``ArtifactKind`` values the skill publishes; internal content
shapes stay inside the handler output contract.

``resolved_input_parameters`` is part of the same descriptor and marks the
handler parameters owned by the server-side input resolver. They remain on the
runtime surface but are never exposed to a Planner or accepted from a Contract.
"""

from __future__ import annotations

#: (name, kind, required, description) — kinds mirror ``SkillParameterDescriptor``.
CapabilityParameter = tuple[str, str, bool, str]

CAPABILITY_DESCRIPTORS: dict[str, dict[str, object]] = {
    "catalog_crossmatch": {
        "phase": "analyzing_data",
        "label": "目录交叉匹配",
        "description": "对两个天文星表执行带证据与冲突管理的位置交叉匹配。",
        "accepted_input_kinds": ("crossmatch_input",),
        "produced_artifact_kinds": ("analysis_report",),
        "parameters": (
            ("crossmatch_input", "rows", True, "两个来源星表的记录集合"),
        ),
        "resolved_input_parameters": ("crossmatch_input",),
        "workload_class": "cpu_heavy",
        "requires_dataset_prerequisite": True,
        "produces_source_snapshot": False,
    },
    "data_profile": {
        "phase": "analyzing_data",
        "label": "数据画像",
        "description": "统计字段缺失、类型分布、分类摘要与数值摘要。",
        "accepted_input_kinds": ("tabular_rows",),
        "produced_artifact_kinds": ("analysis_report",),
        "parameters": (
            ("rows", "rows", True, "待画像的数据行"),
        ),
        "resolved_input_parameters": ("rows",),
        "workload_class": "cpu_light",
        "requires_dataset_prerequisite": True,
        "produces_source_snapshot": False,
    },
    "statistical_analysis": {
        "phase": "analyzing_data",
        "label": "统计分析",
        "description": "描述统计、假设检验与效应量。",
        "accepted_input_kinds": ("tabular_rows",),
        "produced_artifact_kinds": ("analysis_report",),
        "parameters": (
            ("rows", "rows", True, "待分析的数据行"),
            ("fields", "string_list", False, "参与统计的字段"),
            ("hypothesis_tests", "rows", False, "假设检验配置"),
            ("alpha", "number", False, "显著性水平"),
        ),
        "resolved_input_parameters": ("rows",),
        "workload_class": "cpu_light",
        "requires_dataset_prerequisite": True,
        "produces_source_snapshot": False,
    },
    "correlation_analysis": {
        "phase": "analyzing_data",
        "label": "相关分析",
        "description": "数值字段之间的 Pearson / Spearman 相关。",
        "accepted_input_kinds": ("tabular_rows",),
        "produced_artifact_kinds": ("analysis_report",),
        "parameters": (
            ("rows", "rows", True, "待分析的数据行"),
            ("fields", "string_list", True, "参与相关分析的字段"),
            ("method", "string", False, "相关方法"),
        ),
        "resolved_input_parameters": ("rows",),
        "workload_class": "cpu_light",
        "requires_dataset_prerequisite": True,
        "produces_source_snapshot": False,
    },
    "clustering_analysis": {
        "phase": "analyzing_data",
        "label": "聚类分析",
        "description": "KMeans / DBSCAN 聚类、轮廓系数与 PCA 投影。",
        "accepted_input_kinds": ("tabular_rows",),
        "produced_artifact_kinds": ("analysis_report", "visualization"),
        "parameters": (
            ("rows", "rows", True, "待聚类的数据行"),
            ("feature_fields", "string_list", True, "聚类特征字段"),
            ("algorithm", "string", False, "聚类算法"),
            ("cluster_count", "integer", False, "KMeans 簇数"),
            ("eps", "number", False, "DBSCAN 邻域半径"),
            ("min_samples", "integer", False, "DBSCAN 最小样本数"),
            ("random_seed", "integer", False, "随机种子"),
        ),
        "resolved_input_parameters": ("rows",),
        "workload_class": "cpu_heavy",
        "requires_dataset_prerequisite": True,
        "produces_source_snapshot": False,
    },
    "anomaly_detection": {
        "phase": "analyzing_data",
        "label": "异常检测",
        "description": "IsolationForest / 稳健 Z 分数异常检测与排序。",
        "accepted_input_kinds": ("tabular_rows",),
        "produced_artifact_kinds": ("analysis_report", "visualization"),
        "parameters": (
            ("rows", "rows", True, "待检测的数据行"),
            ("feature_fields", "string_list", True, "检测特征字段"),
            ("algorithm", "string", False, "检测算法"),
            ("contamination", "number", False, "预期异常比例"),
            ("z_threshold", "number", False, "稳健 Z 分数阈值"),
            ("random_seed", "integer", False, "随机种子"),
        ),
        "resolved_input_parameters": ("rows",),
        "workload_class": "cpu_heavy",
        "requires_dataset_prerequisite": True,
        "produces_source_snapshot": False,
    },
    "chart_visualization": {
        "phase": "building_visualizations",
        "label": "科学图表",
        "description": "由类型化图表契约构建安全的科学图表。",
        "accepted_input_kinds": ("tabular_rows",),
        "produced_artifact_kinds": ("visualization",),
        "parameters": (
            ("rows", "rows", True, "绘图数据行"),
            ("x_field", "string", True, "X 轴字段"),
            ("y_field", "string", True, "Y 轴字段"),
            ("mark", "string", False, "图形类型"),
            ("title", "string", False, "图表标题"),
            ("series_label", "string", False, "序列标签"),
        ),
        "resolved_input_parameters": ("rows",),
        "workload_class": "cpu_light",
        "requires_dataset_prerequisite": True,
        "produces_source_snapshot": False,
    },
    "simbad_lookup": {
        "phase": "acquiring_observations",
        "label": "SIMBAD 查询",
        "description": "按天体名称或区域查询 SIMBAD 天文数据库。",
        "accepted_input_kinds": ("target_name",),
        "produced_artifact_kinds": ("analysis_report",),
        "parameters": (
            ("object_name", "string", True, "目标天体名称"),
            ("radius_arcmin", "number", False, "区域查询半径（角分）"),
        ),
        "workload_class": "network",
        "requires_dataset_prerequisite": False,
        "produces_source_snapshot": True,
    },
    "skyview_fits": {
        "phase": "acquiring_observations",
        "label": "SkyView FITS 获取",
        "description": "从 SkyView 下载指定巡天的 FITS 图像。",
        "accepted_input_kinds": ("sky_coordinates",),
        "produced_artifact_kinds": ("visualization",),
        "parameters": (
            ("position", "string", True, "天区位置表达式"),
            ("survey", "string", True, "巡天名称"),
            ("radius_degrees", "number", False, "检索半径（度）"),
            ("pixels", "integer", False, "输出像素数"),
        ),
        "workload_class": "network",
        "requires_dataset_prerequisite": False,
        "produces_source_snapshot": True,
    },
    "ephemeris": {
        "phase": "acquiring_observations",
        "label": "行星星历",
        "description": "计算太阳系天体在指定时刻的视位置与地平坐标。",
        "accepted_input_kinds": ("target_name",),
        "produced_artifact_kinds": ("analysis_report",),
        "parameters": (
            ("ephemeris_base64", "string", True, "历表文件（由输入解析注入）"),
            ("target", "string", True, "目标天体"),
            ("reference_target", "string", False, "参考天体"),
            ("observed_at", "string", True, "观测时刻（UTC）"),
            ("latitude_degrees", "number", False, "观测点纬度"),
            ("longitude_degrees", "number", False, "观测点经度"),
            ("elevation_meters", "number", False, "观测点海拔"),
            ("location_name", "string", False, "观测地名称"),
        ),
        "resolved_input_parameters": ("ephemeris_base64",),
        "workload_class": "cpu_light",
        "requires_dataset_prerequisite": False,
        "produces_source_snapshot": True,
    },
    "celestial_events": {
        "phase": "acquiring_observations",
        "label": "天象事件",
        "description": "检索升落、月相、四季、日月食、大距等天象事件。",
        "accepted_input_kinds": ("target_name",),
        "produced_artifact_kinds": ("analysis_report",),
        "parameters": (
            ("ephemeris_base64", "string", True, "历表文件（由输入解析注入）"),
            ("event_type", "string", False, "事件类型"),
            ("target", "string", False, "目标天体"),
            ("start_at", "string", False, "起始时刻（UTC）"),
            ("end_at", "string", False, "结束时刻（UTC）"),
            ("latitude_degrees", "number", False, "观测点纬度"),
            ("longitude_degrees", "number", False, "观测点经度"),
            ("elevation_meters", "number", False, "观测点海拔"),
            ("location_name", "string", False, "观测地名称"),
        ),
        "resolved_input_parameters": ("ephemeris_base64",),
        "workload_class": "cpu_light",
        "requires_dataset_prerequisite": False,
        "produces_source_snapshot": True,
    },
    "gaia_cone_search": {
        "phase": "acquiring_observations",
        "label": "Gaia 锥形检索",
        "description": "按天区坐标查询 Gaia DR3 目录。",
        "accepted_input_kinds": ("sky_coordinates",),
        "produced_artifact_kinds": (
            "dataset",
            "field_dictionary",
            "source_collection",
            "analysis_report",
        ),
        "parameters": (
            ("ra_degrees", "number", True, "赤经（度）"),
            ("dec_degrees", "number", True, "赤纬（度）"),
            ("radius_degrees", "number", False, "检索半径（度）"),
            ("fields", "string_list", False, "返回字段"),
            ("max_results", "integer", False, "最大结果数"),
            ("response_format", "string", False, "响应格式"),
        ),
        "workload_class": "network",
        "requires_dataset_prerequisite": False,
        "produces_source_snapshot": True,
    },
    "vizier_tap": {
        "phase": "acquiring_observations",
        "label": "VizieR 目录检索",
        "description": "通过 TAP 服务查询 VizieR 白名单目录。",
        "accepted_input_kinds": ("sky_coordinates",),
        "produced_artifact_kinds": ("analysis_report",),
        "parameters": (
            ("catalog_id", "string", False, "目录标识"),
            ("table_id", "string", False, "数据表标识"),
            ("ra_degrees", "number", True, "赤经（度）"),
            ("dec_degrees", "number", True, "赤纬（度）"),
            ("radius_degrees", "number", False, "检索半径（度）"),
            ("fields", "string_list", False, "返回字段"),
            ("max_results", "integer", False, "最大结果数"),
            ("response_format", "string", False, "响应格式"),
        ),
        "workload_class": "network",
        "requires_dataset_prerequisite": False,
        "produces_source_snapshot": True,
    },
    "fits_image_analysis": {
        "phase": "analyzing_data",
        "label": "FITS 图像分析",
        "description": "背景统计、质心、源检测、分割与孔径/PSF 测光。",
        "accepted_input_kinds": ("fits_image",),
        "produced_artifact_kinds": ("analysis_report",),
        "parameters": (
            ("fits_base64", "string", True, "FITS 图像（由输入解析注入）"),
            ("image", "rows", False, "图像数组"),
            ("operation", "string", False, "分析操作"),
            ("x", "number", False, "目标 X 坐标"),
            ("y", "number", False, "目标 Y 坐标"),
            ("radius_pixels", "number", False, "孔径半径（像素）"),
            ("background", "number", False, "背景值"),
            ("sigma", "number", False, "Sigma 裁剪系数"),
            ("threshold_sigma", "number", False, "检测阈值"),
            ("fwhm_pixels", "number", False, "半高全宽（像素）"),
            ("max_sources", "integer", False, "最大源数"),
            ("npixels", "integer", False, "分割最小像素数"),
        ),
        "resolved_input_parameters": ("fits_base64", "image"),
        "workload_class": "memory_heavy",
        "requires_dataset_prerequisite": False,
        "produces_source_snapshot": False,
    },
    "spectrum_analysis": {
        "phase": "analyzing_data",
        "label": "光谱分析",
        "description": "连续谱拟合、谱线检测、等值宽度与视向速度。",
        "accepted_input_kinds": ("spectrum_series",),
        "produced_artifact_kinds": ("analysis_report", "spectrum"),
        "parameters": (
            ("rows", "rows", True, "光谱数据行"),
            ("wavelength_field", "string", True, "波长字段"),
            ("flux_field", "string", True, "通量字段"),
            ("uncertainty_field", "string", False, "不确定度字段"),
            ("object_name", "string", False, "目标名称"),
            ("wavelength_unit", "string", False, "波长单位"),
            ("flux_unit", "string", False, "通量单位"),
            ("rest_wavelength", "number", False, "静止波长"),
            ("line_sigma", "number", False, "谱线宽度"),
        ),
        "resolved_input_parameters": ("rows",),
        "workload_class": "cpu_light",
        "requires_dataset_prerequisite": True,
        "produces_source_snapshot": False,
    },
    "spectrum_acquisition": {
        "phase": "acquiring_observations",
        "label": "SDSS 光谱获取",
        "description": "按 plate/mjd/fiber 获取并分析 SDSS DR17 光谱。",
        "accepted_input_kinds": ("sky_coordinates",),
        "produced_artifact_kinds": ("spectrum", "analysis_report"),
        "parameters": (
            ("plate", "integer", True, "SDSS plate 编号"),
            ("mjd", "integer", True, "观测 MJD"),
            ("fiber", "integer", True, "光纤编号"),
            ("rest_wavelength", "number", False, "静止波长"),
            ("line_sigma", "number", False, "谱线宽度"),
        ),
        "workload_class": "network",
        "requires_dataset_prerequisite": False,
        "produces_source_snapshot": True,
    },
    "light_curve_analysis": {
        "phase": "analyzing_data",
        "label": "光变曲线分析",
        "description": "归一化、Lomb-Scargle 周期搜索与相位折叠。",
        "accepted_input_kinds": ("light_curve_series",),
        "produced_artifact_kinds": ("analysis_report", "light_curve"),
        "parameters": (
            ("rows", "rows", True, "光变数据行"),
            ("time_field", "string", True, "时间字段"),
            ("value_field", "string", True, "数值字段"),
            ("uncertainty_field", "string", False, "不确定度字段"),
            ("object_name", "string", False, "目标名称"),
            ("time_scale", "string", False, "时间标度"),
            ("time_unit", "string", False, "时间单位"),
            ("value_unit", "string", False, "数值单位"),
            ("value_kind", "string", False, "数值类型"),
            ("sigma_clip", "number", False, "Sigma 裁剪系数"),
            ("minimum_period", "number", False, "最小周期"),
            ("maximum_period", "number", False, "最大周期"),
        ),
        "resolved_input_parameters": ("rows",),
        "workload_class": "cpu_light",
        "requires_dataset_prerequisite": True,
        "produces_source_snapshot": False,
    },
    "light_curve_acquisition": {
        "phase": "acquiring_observations",
        "label": "TESS 光变曲线获取",
        "description": "按 TIC 编号获取并分析 MAST TESS 光变曲线。",
        "accepted_input_kinds": ("target_name",),
        "produced_artifact_kinds": ("light_curve", "analysis_report"),
        "parameters": (
            ("tic_id", "string", True, "TESS 输入目录编号"),
            ("sector", "integer", False, "观测扇区"),
            ("product_filename", "string", True, "数据产品文件名"),
            ("flux_kind", "string", False, "通量类型"),
            ("sigma_clip", "number", False, "Sigma 裁剪系数"),
            ("minimum_period", "number", False, "最小周期"),
            ("maximum_period", "number", False, "最大周期"),
        ),
        "workload_class": "network",
        "requires_dataset_prerequisite": False,
        "produces_source_snapshot": True,
    },
    "tabular_machine_learning": {
        "phase": "training_models",
        "label": "表格机器学习",
        "description": "分类/回归训练、五种数据划分、基线对比与 ONNX 导出。",
        "accepted_input_kinds": ("tabular_rows",),
        "produced_artifact_kinds": ("model_evaluation", "model_artifact"),
        "parameters": (
            ("rows", "rows", True, "训练数据行"),
            ("feature_fields", "string_list", True, "特征字段"),
            ("target_field", "string", True, "目标字段"),
            ("task_kind", "string", False, "任务类型"),
            ("algorithm", "string", False, "算法"),
            ("split_strategy", "string", False, "数据划分策略"),
            ("group_field", "string", False, "分组字段"),
            ("entity_field", "string", False, "实体字段"),
            ("time_field", "string", False, "时间字段"),
            ("test_fraction", "number", False, "测试比例"),
            ("random_seed", "integer", False, "随机种子"),
            ("cv_folds", "integer", False, "交叉验证折数"),
        ),
        "resolved_input_parameters": ("rows",),
        "workload_class": "cpu_heavy",
        "requires_dataset_prerequisite": True,
        "produces_source_snapshot": False,
    },
    "time_series_classification": {
        "phase": "training_models",
        "label": "时间序列分类",
        "description": "有序序列布局下的时间序列分类训练与评估。",
        "accepted_input_kinds": ("time_series_rows",),
        "produced_artifact_kinds": ("model_evaluation", "model_artifact"),
        "parameters": (
            ("rows", "rows", True, "训练数据行"),
            ("series_fields", "string_list", True, "序列字段"),
            ("target_field", "string", True, "目标字段"),
            ("algorithm", "string", False, "算法"),
            ("test_fraction", "number", False, "测试比例"),
            ("random_seed", "integer", False, "随机种子"),
            ("cv_folds", "integer", False, "交叉验证折数"),
        ),
        "resolved_input_parameters": ("rows",),
        "workload_class": "cpu_heavy",
        "requires_dataset_prerequisite": True,
        "produces_source_snapshot": False,
    },
    "time_series_forecast": {
        "phase": "training_models",
        "label": "时间序列预测",
        "description": "滞后特征滚动预测与时间有序评估。",
        "accepted_input_kinds": ("time_series_rows",),
        "produced_artifact_kinds": ("model_evaluation", "model_artifact"),
        "parameters": (
            ("rows", "rows", True, "训练数据行"),
            ("time_field", "string", True, "时间字段"),
            ("target_field", "string", True, "目标字段"),
            ("lags", "integer", False, "滞后阶数"),
            ("horizon", "integer", False, "预测步长"),
            ("test_fraction", "number", False, "测试比例"),
            ("random_seed", "integer", False, "随机种子"),
        ),
        "resolved_input_parameters": ("rows",),
        "workload_class": "cpu_heavy",
        "requires_dataset_prerequisite": True,
        "produces_source_snapshot": False,
    },
    "image_classification": {
        "phase": "training_models",
        "label": "图像分类",
        "description": "图像数据集上的有界分类训练与 ONNX 导出。",
        "accepted_input_kinds": ("image_dataset",),
        "produced_artifact_kinds": ("model_evaluation", "model_artifact"),
        "parameters": (
            ("images", "rows", True, "图像数据（由输入解析注入）"),
            ("image_count", "integer", False, "图像数量（注入）"),
            ("source_total_pixels", "integer", False, "总像素数（注入）"),
            ("image_shape", "string", False, "图像形状（注入）"),
            ("preprocessing", "string", False, "预处理（注入）"),
            ("label_schema", "rows", False, "标签模式（注入）"),
            ("test_fraction", "number", False, "测试比例"),
            ("random_seed", "integer", False, "随机种子"),
        ),
        "resolved_input_parameters": (
            "images",
            "image_count",
            "source_total_pixels",
            "image_shape",
            "preprocessing",
            "label_schema",
        ),
        "workload_class": "memory_heavy",
        "requires_dataset_prerequisite": True,
        "produces_source_snapshot": False,
    },
    "model_inference": {
        "phase": "analyzing_data",
        "label": "模型推理",
        "description": "对已发布 ONNX 模型执行带输入契约校验的推理。",
        "accepted_input_kinds": ("model_artifact", "tabular_rows"),
        "produced_artifact_kinds": ("analysis_report",),
        "parameters": (
            ("model", "rows", True, "模型契约（由输入解析注入）"),
            ("rows", "rows", True, "推理数据行"),
            ("dataset_artifact_version_id", "string", False, "数据集版本（注入）"),
        ),
        "resolved_input_parameters": (
            "model",
            "rows",
            "dataset_artifact_version_id",
        ),
        "workload_class": "cpu_light",
        "requires_dataset_prerequisite": True,
        "produces_source_snapshot": False,
    },
    "wwt_scene": {
        "phase": "building_visualizations",
        "label": "WWT 天图场景",
        "description": "构建声明式世界望远镜天球场景。",
        "accepted_input_kinds": ("sky_coordinates", "fits_image", "source_table"),
        "produced_artifact_kinds": ("visualization",),
        "parameters": (
            ("view", "rows", False, "视图（坐标或跟踪目标）"),
            ("time", "rows", False, "时间控制"),
            ("observer", "rows", False, "观测点"),
            ("background", "string", False, "背景天图"),
            ("foreground", "rows", False, "前景图层"),
            ("solar_system", "rows", False, "太阳系选项"),
            ("coordinate_grids", "rows", False, "坐标网格"),
            ("constellations", "rows", False, "星座叠加"),
            ("precession_chart", "boolean", False, "岁差图"),
            ("fits_layers", "rows", False, "FITS 图层"),
            ("table_layers", "rows", False, "表格图层"),
            ("annotations", "rows", False, "注释"),
            ("tour_steps", "rows", False, "巡览步骤"),
            ("tour_autoplay", "boolean", False, "自动巡览"),
            ("tour_loop", "boolean", False, "循环巡览"),
        ),
        "workload_class": "cpu_light",
        "requires_dataset_prerequisite": False,
        "produces_source_snapshot": False,
    },
}


def capability_for(skill_id: str) -> dict[str, object]:
    """Return the authoritative descriptor for one registered skill."""

    descriptor = CAPABILITY_DESCRIPTORS.get(skill_id)
    if descriptor is None:
        raise ValueError(f"unregistered scientific skill: {skill_id}")
    return descriptor


def scientific_skill_phase(skill_id: str) -> str:
    """Return the canonical Run phase that owns one registered skill."""

    return str(capability_for(skill_id)["phase"])


def produced_artifact_kinds(skill_id: str) -> tuple[str, ...]:
    """Return the public Artifact kinds one registered skill publishes."""

    return tuple(str(kind) for kind in capability_for(skill_id)["produced_artifact_kinds"])  # type: ignore[arg-type]


def capability_parameters(skill_id: str) -> tuple[CapabilityParameter, ...]:
    """Return the authoritative parameter surface for one skill."""

    return tuple(  # type: ignore[return-value]
        capability_for(skill_id)["parameters"]  # type: ignore[index]
    )


def resolved_input_parameter_names(skill_id: str) -> frozenset[str]:
    """Return handler parameters injected exclusively by the input resolver."""

    descriptor = capability_for(skill_id)
    resolved = frozenset(
        str(name) for name in descriptor.get("resolved_input_parameters", ())
    )
    parameter_names = frozenset(
        name for name, _kind, _required, _description in capability_parameters(skill_id)
    )
    if not resolved.issubset(parameter_names):
        raise ValueError(
            f"{skill_id} resolved_input_parameters must belong to parameters"
        )
    return resolved


def contract_parameters(skill_id: str) -> tuple[CapabilityParameter, ...]:
    """Return only parameters a Planner and confirmed Contract may author."""

    resolved = resolved_input_parameter_names(skill_id)
    return tuple(
        parameter
        for parameter in capability_parameters(skill_id)
        if parameter[0] not in resolved
    )


def skills_producing_artifact_kind(artifact_kind: str) -> tuple[str, ...]:
    """Return registered producers from the single capability Authority."""

    return tuple(
        skill_id
        for skill_id in CAPABILITY_DESCRIPTORS
        if artifact_kind in produced_artifact_kinds(skill_id)
    )


def requires_dataset_prerequisite(skill_id: str) -> bool:
    """Whether planning must freeze dataset-producing steps for this skill."""

    return bool(capability_for(skill_id)["requires_dataset_prerequisite"])


def produces_source_snapshot(skill_id: str) -> bool:
    """Whether execution must persist a SourceSnapshot for this skill."""

    return bool(capability_for(skill_id)["produces_source_snapshot"])


def accepts_artifact_version(skill_id: str) -> bool:
    """Whether persisted Dataset/Model ArtifactVersions can satisfy the input."""

    accepted = set(capability_for(skill_id)["accepted_input_kinds"])
    return bool({"tabular_rows", "time_series_rows", "model_artifact"} & accepted)


def planning_capabilities() -> tuple[dict[str, object], ...]:
    """Project the capability Authority into model- and UI-safe catalog rows."""

    return tuple(
        {
            "id": skill_id,
            "label": str(descriptor["label"]),
            "description": str(descriptor["description"]),
            "phase": str(descriptor["phase"]),
            "accepted_input_kinds": list(descriptor["accepted_input_kinds"]),
            "produced_artifact_kinds": list(
                descriptor["produced_artifact_kinds"]
            ),
            "parameters": [
                {
                    "name": name,
                    "kind": kind,
                    "required": required,
                    "description": description,
                }
                for name, kind, required, description in contract_parameters(skill_id)
            ],
        }
        for skill_id, descriptor in CAPABILITY_DESCRIPTORS.items()
    )


__all__ = [
    "CAPABILITY_DESCRIPTORS",
    "CapabilityParameter",
    "accepts_artifact_version",
    "capability_for",
    "capability_parameters",
    "contract_parameters",
    "produced_artifact_kinds",
    "produces_source_snapshot",
    "planning_capabilities",
    "resolved_input_parameter_names",
    "requires_dataset_prerequisite",
    "scientific_skill_phase",
    "skills_producing_artifact_kind",
]
