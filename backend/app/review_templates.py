"""Versioned AI review templates.

Templates are data, not per-document prompts. A review stores a snapshot of the
selected checklist so historical results remain explainable after a template
changes.
"""
from copy import deepcopy


GENERIC_TEMPLATE_KEY = "generic_document_v1"


COMMON_RULES = [
    {
        "id": "basic_completeness",
        "title": "核心内容完整",
        "kind": "presence",
        "severity": "high",
        "required": True,
        "requires_reference": False,
        "instruction": (
            "检查文档是否具备支撑理解和使用所需的核心章节与要素；"
            "不要求标题名称完全一致。"
        ),
    },
    {
        "id": "internal_consistency",
        "title": "关键数据前后一致",
        "kind": "consistency",
        "severity": "high",
        "required": True,
        "requires_reference": False,
        "instruction": (
            "检查时间、数量、比例、名称等关键数据在不同章节是否一致；"
            "发现冲突时给出两处原文依据。"
        ),
    },
    {
        "id": "version_changes",
        "title": "版本变化清晰且无关键内容误删",
        "kind": "change",
        "severity": "medium",
        "required": False,
        "requires_reference": False,
        "instruction": (
            "比较当前版本与上一版本，说明新增、修改和删除是否清楚；"
            "首版返回 unknown。"
        ),
    },
    {
        "id": "source_grounding",
        "title": "结论有材料依据",
        "kind": "consistency",
        "severity": "medium",
        "required": True,
        "requires_reference": False,
        "instruction": (
            "所有判断必须引用正文或参考规范中的短语；无法取得可靠依据时"
            "返回 unknown。"
        ),
    },
]


SYLLABUS_RULES = [
    {
        "id": "syllabus_required_sections",
        "title": "教学大纲必填章节齐全",
        "kind": "presence",
        "severity": "high",
        "required": True,
        "requires_reference": True,
        "instruction": (
            "检查课程性质、课程目标、教学内容、学时分配、考核方式等"
            "必填章节是否齐全。"
        ),
    },
    {
        "id": "hours_total",
        "title": "总学时与教学单元学时一致",
        "kind": "calculation",
        "severity": "high",
        "required": True,
        "requires_reference": True,
        "instruction": (
            "抽取总学时和各教学单元学时，计算合计并比较；"
            "必须展示参与计算的数字，无法可靠抽取时返回 unknown。"
        ),
    },
    {
        "id": "objective_content",
        "title": "课程目标有教学内容支撑",
        "kind": "mapping",
        "severity": "high",
        "required": True,
        "requires_reference": True,
        "instruction": (
            "逐项检查每个课程目标是否能找到对应的教学内容；"
            "列出未获得支撑的课程目标。"
        ),
    },
    {
        "id": "objective_assessment",
        "title": "课程目标有考核方式支撑",
        "kind": "mapping",
        "severity": "high",
        "required": True,
        "requires_reference": True,
        "instruction": (
            "逐项检查每个课程目标是否有明确的考核环节支撑；"
            "团队协作、实践能力等目标不能只由闭卷考试支撑。"
        ),
    },
    {
        "id": "grading_total",
        "title": "考核比例合计为100%",
        "kind": "calculation",
        "severity": "high",
        "required": True,
        "requires_reference": True,
        "instruction": (
            "提取过程性考核和终结性考核比例，核对合计是否为100%；"
            "未写明比例时返回 unknown。"
        ),
    },
    {
        "id": "template_fields",
        "title": "模板固定字段符合要求",
        "kind": "format",
        "severity": "medium",
        "required": False,
        "requires_reference": True,
        "instruction": (
            "对照学校模板和规范检查固定字段、命名和必填说明；"
            "仅能检查正文内容，不判断颜色、字体等视觉样式。"
        ),
    },
]


TEMPLATES = {
    GENERIC_TEMPLATE_KEY: {
        "key": GENERIC_TEMPLATE_KEY,
        "version": "1.0",
        "name": "通用文档质量检查",
        "description": "没有专用模板时的兜底检查，不声明符合特定业务规范。",
        "rules": COMMON_RULES,
    },
    "syllabus_v1": {
        "key": "syllabus_v1",
        "version": "1.0",
        "name": "教学大纲规范检查",
        "description": "面向高校课程教学大纲的学时、目标、内容、考核一致性检查。",
        "rules": COMMON_RULES + SYLLABUS_RULES,
    },
}


def get_template(key):
    """Return a defensive copy; callers may safely store it as a snapshot."""
    selected = TEMPLATES.get(key) or TEMPLATES[GENERIC_TEMPLATE_KEY]
    return deepcopy(selected)


def normalize_template_key(value):
    key = (value or "").strip()
    if key in TEMPLATES:
        return key
    return GENERIC_TEMPLATE_KEY


def resolve_template(category):
    key = normalize_template_key(
        getattr(category, "review_template_key", None)
    )
    return get_template(key)


def list_templates():
    return [
        {
            "key": template["key"],
            "version": template["version"],
            "name": template["name"],
            "description": template["description"],
            "rule_count": len(template["rules"]),
        }
        for template in sorted(
            TEMPLATES.values(), key=lambda item: item["key"]
        )
    ]


def validate_template_key(value):
    key = (value or "").strip()
    if key not in TEMPLATES:
        raise ValueError("不支持的预审模板")
    return key
