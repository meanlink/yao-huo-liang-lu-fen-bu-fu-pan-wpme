"""陶瓷批次良率复盘：分位数、IQR 与可调门限的稳健离散分析。"""
import math
import random
import numpy as np


def metadata():
    return {
        "name": "窑火良率分布复盘", "short": "kiln-yield",
        "tagline": "把窑次的波动，追到可复核的分位数与异常批次。",
        "client": "青禾陶作 · 36 人陶瓷工坊，3 条窑线每周复盘烧成质量",
        "workflow": "质检员在纸表登记合格数，班长手工算平均良率，再凭经验挑出问题窑次。",
        "pains": ["平均数掩盖低尾批次", "不同装窑量被错误等权比较", "异常名单没有统一判定门限"],
        "upstream": "窑次质检明细 kiln_quality_202611.csv",
        "downstream": "烧成班长据此决定复核窑次与工艺试验顺序",
        "entities": ["窑次样本", "分布复盘", "班组复核简报"],
        "dataset_name": "11 月第一周 · 120 窑次质检",
        "columns": [{"key": "batch", "label": "窑次", "type": "string"}, {"key": "line", "label": "窑线", "type": "string"}, {"key": "fired", "label": "烧成件数", "type": "number"}, {"key": "passed", "label": "合格件数", "type": "number"}],
        "parameters": [{"key": "iqr_factor", "label": "异常围栏倍数", "type": "number", "default": 1.5, "min": 0.5, "max": 3}, {"key": "target", "label": "目标良率（%）", "type": "number", "default": 93, "min": 50, "max": 100}],
        "workbench_title": "批次分布复盘", "action_label": "计算分位与复核名单", "unit": "%",
        "accent": "oklch(55% 0.13 42)", "style": "ceramic",
        "seed_story": ["08:10 质检员提交 kiln_quality_202611.csv，共 120 窑次。", "08:25 分析员核对 QH-001 与 QH-120 的烧成、合格件数。", "08:40 选择异常围栏 1.5，目标良率 93%。", "08:45 执行分布复盘，查看加权良率与 P10。", "09:00 打开逐窑结果，复核低于下围栏的窑次。", "09:20 将目标改为 95%，比较未达标名单变化。", "09:40 导出复盘，班长据名单安排工艺复核。"],
        "method": "每窑良率=passed/fired×100；总体良率按烧成件数加权；分位数采用线性插值；IQR=Q3−Q1；下围栏=Q1−k×IQR；MAD 为绝对中位差。",
        "limitations": ["窑次样本描述不构成因果解释", "尚未纳入釉料和炉温的混杂因素", "只提供复核线索，不自动判废"]}


def seed_records():
    rng = random.Random(1001)
    rows = []
    for i in range(120):
        line = ["东窑", "中窑", "西窑"][i % 3]
        fired = rng.randint(180, 280)
        ratio = rng.gauss([0.954, 0.927, 0.966][i % 3], 0.014)
        if i % 23 == 0:
            ratio -= 0.09
        rows.append({"batch": f"QH-{i + 1:03}", "line": line, "fired": fired, "passed": max(0, min(fired, round(fired * ratio)))})
    return rows


def analyze(records, params):
    if not isinstance(records, list) or len(records) < 4:
        raise ValueError("至少需要 4 个有效窑次")
    try:
        factor, target = float(params.get("iqr_factor", 1.5)), float(params.get("target", 93))
    except (TypeError, ValueError):
        raise ValueError("围栏倍数与目标良率必须为数值")
    if not math.isfinite(factor) or not 0.5 <= factor <= 3 or not math.isfinite(target) or not 50 <= target <= 100:
        raise ValueError("围栏倍数范围为 0.5–3，目标范围为 50–100")
    clean = []
    for row in records:
        try:
            fired, passed = float(row["fired"]), float(row["passed"])
            if not all(math.isfinite(v) for v in (fired, passed)) or fired <= 0 or not 0 <= passed <= fired:
                raise ValueError()
            clean.append({"batch": str(row["batch"]), "line": str(row["line"]), "fired": fired, "passed": passed, "yield": passed / fired * 100})
        except (KeyError, TypeError, ValueError):
            raise ValueError("每窑须含批号、窑线及有效件数，且 0≤合格≤烧成")
    vals = np.array([r["yield"] for r in clean])
    p10, q1, median, q3, p90 = [float(v) for v in np.quantile(vals, [.1, .25, .5, .75, .9])]
    iqr = q3 - q1
    lower, upper = q1 - factor * iqr, q3 + factor * iqr
    mad = float(np.median(np.abs(vals - median)))
    weighted = sum(r["passed"] for r in clean) / sum(r["fired"] for r in clean) * 100
    rows = [{"batch": r["batch"], "line": r["line"], "yield": round(r["yield"], 3), "gap": round(r["yield"] - target, 3), "review": "异常复核" if r["yield"] < lower or r["yield"] > upper else "低于目标" if r["yield"] < target else "达标"} for r in sorted(clean, key=lambda r: r["yield"])]
    n_bad = sum(r["review"] == "异常复核" for r in rows)
    hist, edges = np.histogram(vals, bins=8, range=(max(0, float(vals.min()) - 1), min(100, float(vals.max()) + 1)))
    return {"summary": f"{len(rows)} 个窑次的加权良率为 {weighted:.2f}%，{n_bad} 个窑次触发 IQR 复核。",
            "metrics": [{"label": "加权良率", "value": round(weighted, 3), "unit": "%"}, {"label": "P10 低尾", "value": round(p10, 3), "unit": "%"}, {"label": "四分位距", "value": round(iqr, 3), "unit": "百分点"}, {"label": "复核窑次", "value": n_bad, "unit": "窑"}],
            "table": {"columns": [{"key": "batch", "label": "窑次"}, {"key": "line", "label": "窑线"}, {"key": "yield", "label": "良率 %"}, {"key": "gap", "label": "距目标/百分点"}, {"key": "review", "label": "复核建议"}], "rows": rows},
            "chart": {"type": "bar", "labels": [f"{edges[i]:.1f}–{edges[i+1]:.1f}" for i in range(len(hist))], "series": [{"name": "窑次数", "values": hist.tolist()}]},
            "findings": [f"中位数 {median:.2f}%，P90 {p90:.2f}%，MAD {mad:.2f} 个百分点。", f"当前下围栏 {lower:.2f}%，上围栏 {upper:.2f}%；倍数为 {factor:g}。", f"{sum(r['yield'] < target for r in clean)} 个窑次未达到 {target:g}% 目标；异常与未达标是两种口径。"],
            "method": metadata()["method"], "warnings": ["分布围栏用于定位复核对象，不能替代工艺判定。"]}
