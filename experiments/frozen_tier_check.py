# -*- coding: utf-8 -*-
"""用引擎现在的三档判定，重新给冻结集 60 题分档。

注意：冻结集已经跑过一次（run_count=1），这里**不是**再跑一次冻结测试，
而是拿同一批题看「三档判定上线后，哪些题从『照常作答』变成了『提示/拒答』」。
所以结论只能当回归对照，不能当新的证据。
"""
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)

from rag_engine import load_engine_with_handbook  # noqa: E402

data = json.loads((ROOT / "frozen_testset.json").read_text(encoding="utf-8"))
print(
    "载入冻结题:"
    f"正例 {len(data['positives'])} / "
    f"离题负例 {len(data['negatives_offtopic'])} / "
    f"话题内缺失负例 {len(data['negatives_in_domain'])}"
)
engine = load_engine_with_handbook()


def bucket(t):
    return {"high": "高置信", "medium": "低置信", "low": "无依据"}[t]


groups = {
    "正例": [c["q"] for c in data["positives"]],
    "离题负例": [c["q"] for c in data["negatives_offtopic"]],
    "话题内缺失负例": [c["q"] for c in data["negatives_in_domain"]],
}

print("三档判定（matched：≥2 高置信 / =1 低置信 / =0 无依据）在冻结集上的落档")
for name, qs in groups.items():
    cnt = {"高置信": 0, "低置信": 0, "无依据": 0}
    details = []
    for q in qs:
        r = engine.ask(q)
        cnt[bucket(r.tier)] += 1
        if r.tier != "high":
            details.append(f"    · [{bucket(r.tier)}] {q}")
    print(f"\n{name}（{len(qs)} 条）：高置信 {cnt['高置信']} / 低置信 {cnt['低置信']} / 无依据 {cnt['无依据']}")
    for d in details:
        print(d)

print("\n对照：同一批题在改动前是「11/15 话题内缺失被照常作答、0/15 离题被拒」。")
print("这次只看档位怎么变，不能叫冻结测试结果（同一批题第二次跑）。")
