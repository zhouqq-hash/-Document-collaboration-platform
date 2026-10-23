r"""Run the real AI review loop against an isolated temporary database.

Usage from the repository root:

    .\.venv\Scripts\python.exe tools\run-ai-review-smoke.py

This calls the configured model and writes a JSON evidence report under
``testdata/``. It does not change the normal development database.
"""
import io
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app import create_app, db  # noqa: E402
from app.models import Document  # noqa: E402


SCENARIO_DIR = BACKEND / "demo_data" / "ai_review_scenario"
DRAFT_TITLE = "数据库原理及应用课程教学大纲（待审核）"
REVISED_FILE = "05_数据库原理及应用课程教学大纲_整改稿_v2.docx"
RETURN_NOTE = (
    "请统一总学时与单元学时，将考核比例补齐至 100%，"
    "并为团队协作目标补充项目汇报、分工记录和同伴评价。"
)


def response_data(response, action):
    payload = response.get_json(silent=True) or {}
    if response.status_code not in {200, 201}:
        detail = payload.get("error", {}).get("message") or payload
        raise RuntimeError(f"{action}失败：HTTP {response.status_code}，{detail}")
    return payload.get("data")


def check_results_by_id(review):
    return {
        item.get("rule_id"): item
        for item in review.get("result", {}).get("check_results", [])
        if isinstance(item, dict) and item.get("rule_id")
    }


def main():
    (BACKEND / ".pytest_tmp").mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(prefix="ai_review_smoke_", dir=BACKEND / ".pytest_tmp")
    )
    media_dir = temp_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "ai-review-smoke",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{temp_dir / 'smoke.db'}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "UPLOAD_FOLDER": str(media_dir),
            "AI_AUTO_REVIEW_ENABLED": False,
        }
    )

    report = {
        "started_at": datetime.now().astimezone().isoformat(),
        "model": app.config.get("COSMOS_MODEL"),
        "functional_closed_loop": False,
        "ai_first_review_quality": False,
        "ai_revision_review_quality": False,
        "steps": [],
    }

    try:
        if not app.config.get("COSMOS_API_KEY"):
            raise RuntimeError("backend/.env 未配置 COSMOS_API_KEY")

        seeded = app.test_cli_runner().invoke(args=["seed"])
        if seeded.exit_code != 0:
            raise RuntimeError(f"初始化场景失败：{seeded.output}")
        report["steps"].append("seed scenario")

        with app.app_context():
            document = Document.query.filter_by(title=DRAFT_TITLE).one()
            document_id = document.id

        client = app.test_client()
        response_data(
            client.post(
                "/api/auth/login",
                json={"username": "teacher", "password": "teacher123"},
            ),
            "负责人登录",
        )
        report["steps"].append("login as document owner")

        first_review = response_data(
            client.post(
                f"/api/documents/{document_id}/ai/review",
                json={},
            ),
            "首次 AI 预审",
        )
        first_review_id = first_review["id"]
        first_checks = check_results_by_id(first_review)
        detected_rule_ids = sorted(
            rule_id
            for rule_id, item in first_checks.items()
            if item.get("status") == "fail"
        )
        required_findings = {"hours_total"}
        report["first_review"] = {
            "review_id": first_review_id,
            "verdict": first_review.get("verdict"),
            "failed_rules": detected_rule_ids,
            "summary": first_review.get("result", {}).get("summary", ""),
            "model": first_review.get("model"),
        }
        report["ai_first_review_quality"] = required_findings.issubset(
            set(detected_rule_ids)
        )
        if not report["ai_first_review_quality"]:
            raise RuntimeError(
                "首次预审未识别预设的 hours_total 问题，"
                f"实际失败项为 {detected_rule_ids}"
            )
        report["steps"].append("AI review detected preset issues")

        returned = response_data(
            client.patch(
                f"/api/documents/{document_id}/ai/reviews/{first_review_id}/decision",
                json={"decision": "return", "note": RETURN_NOTE},
            ),
            "人工退回",
        )
        if returned.get("human_decision") != "return":
            raise RuntimeError("人工退回状态未保存")
        report["steps"].append("human reviewer returned the draft")

        revised_bytes = (SCENARIO_DIR / REVISED_FILE).read_bytes()
        uploaded = response_data(
            client.post(
                f"/api/documents/{document_id}/versions",
                data={
                    "changelog": "按预审意见统一学时、补足考核比例并增加团队项目考核",
                    "file": (
                        io.BytesIO(revised_bytes),
                        "数据库原理及应用课程教学大纲_整改稿_v2.docx",
                    ),
                },
                content_type="multipart/form-data",
            ),
            "上传整改稿",
        )
        if uploaded.get("version_number") != 2:
            raise RuntimeError("整改稿未生成 v2")
        report["steps"].append("uploaded corrected v2")

        second_review = response_data(
            client.post(
                f"/api/documents/{document_id}/ai/review",
                json={},
            ),
            "整改复审",
        )
        second_checks = check_results_by_id(second_review)
        second_failed = sorted(
            rule_id
            for rule_id, item in second_checks.items()
            if item.get("status") == "fail"
        )
        previous_issue_checks = second_review.get("result", {}).get(
            "previous_issue_checks", []
        )
        report["revision_review"] = {
            "review_id": second_review["id"],
            "previous_review_id": second_review.get("previous_review_id"),
            "verdict": second_review.get("verdict"),
            "failed_rules": second_failed,
            "previous_issue_checks": previous_issue_checks,
            "summary": second_review.get("result", {}).get("summary", ""),
        }
        report["ai_revision_review_quality"] = bool(
            second_review.get("verdict") == "pass"
            and not second_failed
            and previous_issue_checks
        )
        if not report["ai_revision_review_quality"]:
            raise RuntimeError(
                "整改复审未形成有效的问题复核结果："
                f"failed_rules={second_failed}, "
                f"previous_issue_checks={bool(previous_issue_checks)}"
            )
        report["steps"].append("AI re-review linked and checked prior issues")

        response_data(
            client.patch(
                f"/api/documents/{document_id}/ai/reviews/{second_review['id']}/decision",
                json={"decision": "pass", "note": "整改项已核验，同意发布"},
            ),
            "人工通过",
        )
        detail = response_data(
            client.get(f"/api/documents/{document_id}"),
            "读取最终状态",
        )
        if detail.get("review_state", {}).get("code") != "approved":
            raise RuntimeError(
                f"最终状态不是 approved：{detail.get('review_state')}"
            )
        report["final_review_state"] = detail["review_state"]
        report["functional_closed_loop"] = True
        report["steps"].append("human reviewer approved revised version")
        report["result"] = "passed"
    except Exception as exc:
        report["result"] = "failed"
        report["error"] = str(exc)
    finally:
        report["finished_at"] = datetime.now().astimezone().isoformat()
        report_path = ROOT / "testdata" / "ai-review-smoke-report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        shutil.rmtree(temp_dir, ignore_errors=True)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nreport: {report_path}")
    return 0 if report["functional_closed_loop"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
