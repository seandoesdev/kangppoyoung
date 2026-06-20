"""N회 평균 채점용 답변 수집기 (docs/plan/eval_and_retrieval_plan.md Phase A).

eval_set.json 의 각 질문을 통합 검색(POST /api/v1/search)에 N회(기본 10) 호출한다.
검색(코사인)은 결정적이고 합성(gpt-4o)만 변동하므로, N개 답변이 합성 노이즈를 표본한다.
동시 호출로 단축하며, evidence 문서 분포도 함께 수집한다.

사용: python eval/collect.py [N]   (또는 EVAL_RUNS 환경변수)
출력: eval/.answers.json
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
URL = os.environ.get("EVAL_URL", "http://localhost:80/api/v1/search")
N = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("EVAL_RUNS", "10"))
WORKERS = int(os.environ.get("EVAL_WORKERS", "2"))  # 동시 호출(과도하면 백엔드 503)


def docs_of(d: dict) -> list[str]:
    s = set()
    for e in (d.get("evidence") or []):
        t = e.get("docTitle") or ""
        if "변경공고" in t or "(제2026-287" in t:
            s.add("변경공고")
        elif "참고자료" in t:
            s.add("참고자료")
        elif "기초" in t:
            s.add("기초가이드")
        else:
            s.add(t[:16])
    return sorted(s)


def ask(question: str, retries: int = 4) -> dict:
    body = json.dumps({"query": question}).encode("utf-8")
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(URL, data=body,
                                     headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=180).read().decode("utf-8"))
            return {"answer": d.get("answer") or "", "docs": docs_of(d)}
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (502, 503, 504, 429):  # 일시적 과부하 → 백오프 후 재시도
                time.sleep(2 + attempt * 3)
                continue
            raise
        except Exception as e:  # noqa: BLE001 — 연결 리셋 등 일시 오류도 재시도
            last = e
            time.sleep(2 + attempt * 3)
    raise last


def main() -> int:
    eval_set = json.load(open(os.path.join(HERE, "eval_set.json"), encoding="utf-8"))
    tasks = [(item["n"], run, item["question"]) for item in eval_set for run in range(N)]
    results: dict[int, dict[int, dict]] = {}
    errors = 0
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(ask, q): (n, r) for (n, r, q) in tasks}
        for fut in cf.as_completed(futs):
            n, r = futs[fut]
            try:
                results.setdefault(n, {})[r] = fut.result()
            except Exception as e:  # noqa: BLE001
                errors += 1
                results.setdefault(n, {})[r] = {"answer": "", "docs": [], "error": str(e)[:120]}
    out = []
    for item in eval_set:
        runs = [results[item["n"]][r] for r in range(N)]
        out.append({"n": item["n"], "question": item["question"], "runs": runs})
    json.dump(out, open(os.path.join(HERE, ".answers.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    ms = sum(1 for item in out for run in item["runs"] if len(run.get("docs", [])) >= 2)
    print(f"collected: {len(out)} questions x {N} runs = {len(tasks)} answers, errors={errors}")
    print(f"evidence 2+docs: {ms}/{len(tasks)} runs")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
