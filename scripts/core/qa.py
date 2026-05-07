"""
qa.py — QA Reviewer: rule-based checks + LLM semantic sampling.
Outputs workspace/qa_report.json.
"""

import json
import re
import sqlite3
from pathlib import Path

import config
from engine import _call_api_raw


def _rule_check(rows: list, glossary: list) -> list:
    """Rule-based checks. Returns list of flagged rows with issues."""
    from engine import find_matching_terms
    flagged = []
    for r in rows:
        issues = []
        src = str(r.get("source") or "")
        opt = str(r.get("translation") or "")
        draft = str(r.get("draft") or "")
        row_num = r.get("row_num", 0)

        # 1. Terminology check (only matched terms, not full glossary scan)
        if glossary:
            matched = find_matching_terms(src, glossary)
            opt_lower = opt.lower()
            for st, tt in matched:
                variants = {tt.lower()}
                if tt.lower().startswith("the "):
                    variants.add(tt.lower()[4:])
                else:
                    variants.add("the " + tt.lower())
                if not any(v in opt_lower for v in variants):
                    issues.append(f"术语缺失: {st} -> {tt}")

        # 2. Tag integrity
        tags = re.findall(r'<(color|i|b|size|font)[^>]*>', src)
        for tag in set(tags):
            opt_opens = opt.count(f'<{tag}')
            opt_closes = len(re.findall(rf'</{tag}>', opt))
            if opt_opens != opt_closes:
                issues.append(f"标签不成对: <{tag}>")

        # 3. Placeholder preservation
        placeholders = re.findall(r'\{[^}]+\}|%[sdif]|\$\w+', src)
        for ph in placeholders:
            if ph not in opt:
                issues.append(f"占位符丢失: {ph}")

        # 4. Length constraint (if max_length metadata exists in DB)
        max_len = r.get("max_length") or ""
        if max_len:
            try:
                if len(opt) > int(max_len):
                    issues.append(f"长度超限: {len(opt)} > {max_len}")
            except ValueError:
                pass

        if issues:
            flagged.append({
                "row_num": row_num,
                "source": src,
                "draft": draft,
                "optimized": opt,
                "issues": issues,
            })

    return flagged


def _semantic_score(sample_rows: list, style_anchor: str = "") -> list:
    """Call LLM to score semantic quality and give actionable feedback."""
    if not sample_rows:
        return []

    system = (
        "你是 QA Reviewer，游戏本地化质量检查专家。"
        "对每行翻译进行深度分析，输出评分 + 具体问题 + 可执行的修改建议。"
        "修改建议必须具体到 Translator 可以直接按此修改（如'将X改为Y'）。"
    )

    blocks = []
    for r in sample_rows:
        blocks.append(
            f"[{r['row_num']}]\nSOURCE: {r['source'][:200]}\n"
            f"DRAFT: {r['draft'][:200]}\nOPTIMIZED: {r['optimized'][:200]}\n"
            f"脚本已发现问题: {', '.join(r['issues'])}"
        )

    style_hint = f"\n风格锚定: {style_anchor}\n" if style_anchor else ""

    user = (
        f"请对以下行进行深度质量分析：{style_hint}\n\n"
        + "\n---\n".join(blocks)
        + "\n\n对每行输出：\n"
        "- score: 0.0–1.0\n"
        "- issues: 具体问题列表（语义/风格/语法层面）\n"
        "- suggestions: 可执行的修改建议（Translator 可直接按此修改）\n"
        "- pass: true/false（score>=0.9 且 issues 为空则 true）\n\n"
        "输出格式: [{\"row_num\": 1, \"score\": 0.95, \"issues\": [], \"suggestions\": [], \"pass\": true}, ...]"
        "\n仅输出合法 JSON 数组，不要 markdown 代码块。"
    )

    raw = _call_api_raw([{"role": "system", "content": system}, {"role": "user", "content": user}])
    if not raw:
        print("[qa] Semantic scoring API call failed.")
        return []

    try:
        scores = json.loads(raw.strip().strip("```json").strip("```").strip())
        if isinstance(scores, dict):
            scores = list(scores.values())
        return scores if isinstance(scores, list) else []
    except json.JSONDecodeError:
        print(f"[qa] JSON parse failed. Raw:\n{raw[:500]}")
        return []


def run_qa(glossary_file: str = None) -> dict:
    """Run QA and write report to workspace/qa_report.json."""
    from ingest import load_glossary

    db_path = str(config.WORKSPACE_DIR / "workspace.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Gracefully handle missing columns (max_length, gender may not exist in old DBs)
    try:
        rows = conn.execute(
            "SELECT row_num, source, draft, translation, max_length, gender, locked, status FROM rows"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute(
            "SELECT row_num, source, draft, translation, locked, status FROM rows"
        ).fetchall()
    conn.close()
    rows = [dict(r) for r in rows]

    # Load glossary
    glossary = []
    if glossary_file:
        glossary = load_glossary(glossary_file)

    # Step 1: Rule-based checks
    flagged = _rule_check(rows, glossary)
    print(f"[qa] Rule check: {len(flagged)} rows flagged")

    # Step 2: Semantic scoring for flagged rows (sample up to 30)
    semantic_sample = flagged[:30]
    style_anchor = ""
    scout_path = config.WORKSPACE_DIR / "scout_report.json"
    if scout_path.exists():
        try:
            scout_data = json.loads(scout_path.read_text(encoding="utf-8"))
            style_anchor = scout_data.get("style_anchor", "")
        except Exception:
            pass
    scores = _semantic_score(semantic_sample, style_anchor) if semantic_sample else []
    score_map = {s.get("row_num"): s for s in scores if isinstance(s, dict)}

    # Build report
    report_rows = []
    for r in rows:
        row_num = r["row_num"]
        flag = next((f for f in flagged if f["row_num"] == row_num), None)
        score_data = score_map.get(row_num, {})
        score = score_data.get("score", 1.0 if not flag else 0.75)
        semantic_issues = score_data.get("issues", [])
        suggestions = score_data.get("suggestions", [])

        all_issues = (flag["issues"] if flag else []) + semantic_issues

        report_rows.append({
            "row_num": row_num,
            "score": round(score, 2),
            "issues": all_issues,
            "suggestions": suggestions,
            "pass": score >= 0.9 and not all_issues,
        })

    # Only count non-locked, done rows for score calculation
    eligible = [r for r in rows if not r.get("locked") and r.get("status") == "done"]
    eligible_nums = {r["row_num"] for r in eligible}
    done_count = len(eligible)
    passed_count = sum(1 for rr in report_rows if rr["pass"] and rr["row_num"] in eligible_nums)
    failed_rows = [rr["row_num"] for rr in report_rows if not rr["pass"] and rr["row_num"] in eligible_nums]
    overall = passed_count / max(done_count, 1)

    report = {
        "overall_score": round(overall, 2),
        "total_rows": len(rows),
        "done_rows": done_count,
        "passed_rows": passed_count,
        "failed_rows": failed_rows,
        "rows": report_rows,
        "summary": f"{passed_count}/{done_count} passed, {len(failed_rows)} failed",
    }

    report_path = config.WORKSPACE_DIR / "qa_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[qa] Report -> {report_path}")
    return report
