#!/usr/bin/env python3
"""Generate a public synthetic IR evaluation dataset.

The generator does not use real patient data.  It starts from the public
100-case development set only to learn the allowed label vocabulary and target
distribution, then writes a 1000-case synthetic dataset plus fixed splits.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SEED_INPUT = PROJECT_ROOT / "evaluation" / "ir" / "data" / "eval_cases.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "ir" / "data" / "synthetic"

SPLIT_SIZES = {
    "dev": 300,
    "validation": 200,
    "locked_holdout": 500,
}

QUESTION_PLAN = [
    ("초진", "Q1", 540),
    ("초진", "Q3", 60),
    ("재진", "Q1", 270),
    ("재진", "Q3", 130),
]

DIFFICULTY_PLAN = [
    ("easy", 400),
    ("medium", 400),
    ("hard", 200),
]

PHRASE_BANK: dict[str, dict[str, list[str]]] = {
    "기침": {
        "standard": ["기침이 계속 납니다", "기침이 자주 나옵니다", "마른기침이 반복됩니다"],
        "dialect": ["기침이 자꾸 나와요", "기침이 안 멎는 거 같아요", "콜록거리는 게 계속 있어요"],
    },
    "호흡곤란": {
        "standard": ["숨이 차서 힘듭니다", "가만히 있어도 숨쉬기가 불편합니다", "숨이 부족한 느낌입니다"],
        "dialect": ["숨이 차가 힘들어요", "가만 있어도 숨이 벅차요", "숨이 잘 안 쉬어지는 느낌이에요"],
    },
    "운동 시 호흡곤란": {
        "standard": ["걸을 때 숨이 더 찹니다", "계단을 오르면 숨이 많이 찹니다"],
        "dialect": ["조금만 걸어도 숨이 차요", "계단 오르면 숨이 확 막혀요"],
    },
    "어지러움": {
        "standard": ["머리가 어지럽습니다", "일어설 때 어지럽습니다", "빙빙 도는 느낌이 있습니다"],
        "dialect": ["머리가 핑 돌아요", "일어나면 어질어질해요", "빙 도는 느낌이 있어요"],
    },
    "체중감소": {
        "standard": ["체중이 줄었습니다", "최근 살이 많이 빠졌습니다"],
        "dialect": ["살이 자꾸 빠져요", "몸무게가 좀 줄었어요"],
    },
    "가래": {
        "standard": ["가래가 자주 나옵니다", "목에 가래가 걸립니다"],
        "dialect": ["가래가 자꾸 나와요", "목에 가래가 걸려 있는 거 같아요"],
    },
    "화농성 객담": {
        "standard": ["누런 가래가 나옵니다", "진한 노란 가래가 계속 나옵니다"],
        "dialect": ["누런 가래가 자꾸 나와요", "가래가 노랗고 진해요"],
    },
    "검은색 가래": {
        "standard": ["검은색 가래가 나옵니다", "가래 색이 검게 보입니다"],
        "dialect": ["거무스름한 가래가 나와요", "가래가 좀 까매 보여요"],
    },
    "거품이 섞인 가래": {
        "standard": ["거품 섞인 가래가 나옵니다", "가래에 거품이 보입니다"],
        "dialect": ["거품 낀 가래가 나와요", "가래가 거품처럼 올라와요"],
    },
    "객혈": {
        "standard": ["가래에 피가 섞여 나옵니다", "기침할 때 피가 보입니다"],
        "dialect": ["가래에 피가 좀 묻어 나와요", "기침하면 피가 비쳐요"],
    },
    "코막힘": {
        "standard": ["코가 막혀 답답합니다", "코막힘이 계속됩니다"],
        "dialect": ["코가 꽉 막혀요", "코가 막혀가 답답해요"],
    },
    "콧물": {
        "standard": ["콧물이 계속 흐릅니다", "맑은 콧물이 납니다"],
        "dialect": ["콧물이 줄줄 나와요", "코가 자꾸 흘러요"],
    },
    "재채기": {
        "standard": ["재채기가 자주 납니다", "재채기가 멈추지 않습니다"],
        "dialect": ["재채기가 자꾸 나와요", "재채기를 계속 해요"],
    },
    "가슴 두근거림": {
        "standard": ["가슴이 두근거립니다", "심장이 빨리 뛰는 느낌입니다"],
        "dialect": ["가슴이 막 두근거려요", "심장이 쿵쿵 뛰는 거 같아요"],
    },
    "빈맥": {
        "standard": ["맥이 빠르게 뜁니다", "심박이 빠른 느낌입니다"],
        "dialect": ["맥이 너무 빨리 뛰어요", "심장이 빠르게 뛰는 느낌이에요"],
    },
    "부정맥": {
        "standard": ["심장이 불규칙하게 뜁니다", "맥이 건너뛰는 느낌입니다"],
        "dialect": ["심장이 엇박자로 뛰는 거 같아요", "맥이 들쑥날쑥해요"],
    },
    "가슴 답답": {
        "standard": ["가슴이 답답합니다", "가슴이 막힌 듯 답답합니다"],
        "dialect": ["가슴이 답답해요", "가슴이 꽉 막힌 거 같아요"],
    },
    "흉부압박감": {
        "standard": ["가슴이 눌리는 느낌입니다", "가슴을 꽉 누르는 느낌입니다"],
        "dialect": ["가슴을 누르는 거 같아요", "가슴이 꽉 눌리는 느낌이에요"],
    },
    "흉통": {
        "standard": ["가슴 한쪽이 아픕니다", "숨을 쉴 때 가슴이 결립니다", "가슴이 찌르듯 아픕니다"],
        "dialect": ["가슴이 콕콕 아파요", "숨 쉬면 가슴이 결려요", "가슴 한쪽이 찌릿해요"],
    },
    "방사통": {
        "standard": ["통증이 어깨 쪽으로 뻗칩니다", "가슴 통증이 팔로 퍼집니다"],
        "dialect": ["아픈 게 어깨로 뻗어요", "가슴 아픈 게 팔까지 퍼져요"],
    },
    "기운없음": {
        "standard": ["기운이 없습니다", "몸에 힘이 잘 들어가지 않습니다"],
        "dialect": ["기운이 하나도 없어요", "몸에 힘이 쭉 빠져요"],
    },
    "권태감": {
        "standard": ["몸이 처지고 의욕이 없습니다", "전반적으로 몸이 무겁습니다"],
        "dialect": ["몸이 축 처져요", "괜히 몸이 무겁고 처져요"],
    },
    "피로감": {
        "standard": ["쉬어도 피곤합니다", "피로감이 계속됩니다"],
        "dialect": ["자도자도 피곤해요", "쉬어도 몸이 피곤해요"],
    },
    "근력 약화": {
        "standard": ["팔다리에 힘이 잘 들어가지 않습니다", "근력이 약해진 느낌입니다"],
        "dialect": ["팔다리에 힘이 잘 안 들어가요", "힘이 부쩍 약해진 거 같아요"],
    },
    "근육통": {
        "standard": ["온몸 근육이 쑤십니다", "몸살처럼 근육통이 있습니다"],
        "dialect": ["몸이 여기저기 쑤셔요", "근육이 욱신거려요"],
    },
    "오한": {
        "standard": ["오한이 있습니다", "몸이 춥고 떨립니다"],
        "dialect": ["몸이 으슬으슬해요", "추워가 몸이 떨려요"],
    },
    "온몸이 떨림": {
        "standard": ["온몸이 떨립니다", "몸이 심하게 떨리는 느낌입니다"],
        "dialect": ["몸이 막 떨려요", "온몸이 덜덜 떨려요"],
    },
    "발한": {
        "standard": ["땀이 많이 납니다", "식은땀이 납니다"],
        "dialect": ["땀이 자꾸 나요", "식은땀이 흘러요"],
    },
    "피부홍조": {
        "standard": ["얼굴이 붉어집니다", "피부가 달아오르는 느낌입니다"],
        "dialect": ["얼굴이 확 달아올라요", "피부가 빨개져요"],
    },
    "목의 통증": {
        "standard": ["목이 아픕니다", "목이 따갑고 아픕니다"],
        "dialect": ["목이 칼칼하고 아파요", "목이 따가워요"],
    },
    "목소리 변화": {
        "standard": ["목소리가 쉬었습니다", "목소리가 잘 나오지 않습니다"],
        "dialect": ["목소리가 쉬어 버렸어요", "목소리가 잘 안 나와요"],
    },
    "천명음": {
        "standard": ["숨쉴 때 쌕쌕거리는 소리가 납니다", "가슴에서 쌕쌕 소리가 납니다"],
        "dialect": ["숨 쉴 때 쌕쌕거려요", "가슴에서 쌕쌕 소리가 나요"],
    },
    "두통": {
        "standard": ["머리가 아픕니다", "머리가 지끈거립니다"],
        "dialect": ["머리가 지끈지끈해요", "머리가 깨질 듯 아파요"],
    },
    "눈이 무거운 느낌": {
        "standard": ["눈이 무겁게 느껴집니다", "눈꺼풀이 무겁습니다"],
        "dialect": ["눈이 무거워요", "눈꺼풀이 축 처지는 느낌이에요"],
    },
    "눈의 충혈": {
        "standard": ["눈이 빨갛게 충혈됐습니다", "눈이 붉어졌습니다"],
        "dialect": ["눈이 빨개졌어요", "눈이 벌겋게 됐어요"],
    },
    "눈꼽": {
        "standard": ["눈곱이 자주 낍니다", "아침마다 눈꼽이 많이 낍니다"],
        "dialect": ["눈꼽이 자꾸 껴요", "눈곱이 많이 붙어요"],
    },
    "하지부종": {
        "standard": ["다리가 붓습니다", "종아리가 붓는 느낌입니다"],
        "dialect": ["다리가 퉁퉁 부어요", "종아리가 자꾸 부어요"],
    },
    "사지 부종": {
        "standard": ["손발이 붓습니다", "팔다리가 붓는 느낌입니다"],
        "dialect": ["손발이 자꾸 부어요", "팔다리가 붓는 거 같아요"],
    },
    "복부팽만감": {
        "standard": ["배가 더부룩하고 부풀어 있습니다", "복부가 팽팽한 느낌입니다"],
        "dialect": ["배가 빵빵해요", "속이 더부룩하고 배가 불러요"],
    },
    "복부 통증": {
        "standard": ["배가 아픕니다", "복부 통증이 있습니다"],
        "dialect": ["배가 콕콕 아파요", "속이 아파요"],
    },
    "설사": {
        "standard": ["묽은 변을 자주 봅니다", "설사가 계속됩니다"],
        "dialect": ["묽은 변을 몇 번씩 봐요", "배가 아프고 설사를 해요"],
    },
    "구토": {
        "standard": ["토할 것 같습니다", "구토가 있었습니다"],
        "dialect": ["속이 울렁거려 토할 거 같아요", "토를 했어요"],
    },
    "사래걸림": {
        "standard": ["먹을 때 사래가 자주 걸립니다", "물을 마시면 자주 사레가 듭니다"],
        "dialect": ["먹다가 자꾸 사래가 걸려요", "물 마시면 사레가 잘 들어요"],
    },
    "삼키기 곤란": {
        "standard": ["음식이 잘 넘어가지 않습니다", "삼키기가 어렵습니다"],
        "dialect": ["음식이 목에 걸려 잘 안 넘어가요", "삼키기가 힘들어요"],
    },
    "불안": {
        "standard": ["괜히 불안합니다", "불안감이 계속됩니다"],
        "dialect": ["괜히 불안해요", "마음이 자꾸 불안해요"],
    },
    "창백": {
        "standard": ["얼굴이 창백해졌습니다", "안색이 창백합니다"],
        "dialect": ["얼굴빛이 창백해 보여요", "안색이 하얗게 질렸어요"],
    },
    "감기 증상": {
        "standard": ["감기 기운이 있습니다", "감기 증상이 이어집니다"],
        "dialect": ["감기 기운이 좀 있어요", "감기 몸살 같은 느낌이에요"],
    },
}


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    seed_cases = load_cases(args.seed_input)
    symptom_pool = sorted({symptom for case in seed_cases for symptom in case.get("gold_symptoms", [])})
    if not symptom_pool:
        raise RuntimeError("Seed dataset has no gold symptoms.")

    blueprint = build_blueprint(args.count, symptom_pool, rng)
    cases = [render_case(item, rng) for item in blueprint]
    validate_generated(cases)
    assign_splits(cases)
    write_outputs(cases, blueprint, args.output_dir, args.seed)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate public synthetic IR eval data.")
    parser.add_argument("--seed-input", type=Path, default=DEFAULT_SEED_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260626)
    return parser.parse_args()


def load_cases(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return [row for row in data["data"] if isinstance(row, dict)]
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    raise RuntimeError(f"Unsupported seed dataset shape: {path}")


def expand_plan(plan: list[tuple[str, ...]], total: int, rng: random.Random) -> list[tuple[str, ...]]:
    values: list[tuple[str, ...]] = []
    for row in plan:
        *fields, count = row
        values.extend([tuple(fields)] * int(count))
    if len(values) != total:
        raise RuntimeError(f"Plan size mismatch: expected {total}, got {len(values)}")
    rng.shuffle(values)
    return values


def build_blueprint(count: int, symptom_pool: list[str], rng: random.Random) -> list[dict[str, Any]]:
    if count != 1000:
        raise RuntimeError("This public release pipeline currently fixes count at 1000.")
    question_slots = expand_plan(QUESTION_PLAN, count, rng)
    difficulties = [row[0] for row in expand_plan(DIFFICULTY_PLAN, count, rng)]
    dialects = ["standard"] * (count // 2) + ["dialect"] * (count - count // 2)
    rng.shuffle(dialects)

    symptom_cycle = symptom_pool[:]
    rng.shuffle(symptom_cycle)

    blueprint: list[dict[str, Any]] = []
    for index in range(count):
        visit_type, question_id = question_slots[index]
        difficulty = difficulties[index]
        dialect_type = dialects[index]
        gold_count = 1 if index % 10 < 6 else 2 if index % 10 < 9 else 3
        gold = pick_symptoms(symptom_cycle, index, gold_count)
        negative: list[str] = []
        if index % 4 == 0:
            negative = pick_negative(symptom_cycle, index, gold)
        blueprint.append(
            {
                "case_id": f"syn_{index + 1:04d}",
                "visit_type": visit_type,
                "question_id": question_id,
                "dialect_type": dialect_type,
                "difficulty": difficulty,
                "gold_symptoms": gold,
                "negative_symptoms": negative,
            }
        )
    return blueprint


def pick_symptoms(symptoms: list[str], index: int, count: int) -> list[str]:
    result: list[str] = []
    for offset in range(count):
        result.append(symptoms[(index + offset * 13) % len(symptoms)])
    return result


def pick_negative(symptoms: list[str], index: int, gold: list[str]) -> list[str]:
    for offset in range(1, len(symptoms) + 1):
        candidate = symptoms[(index * 7 + offset) % len(symptoms)]
        if candidate not in gold:
            return [candidate]
    return []


def render_case(item: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    gold = list(item["gold_symptoms"])
    negative = list(item["negative_symptoms"])
    dialect_type = item["dialect_type"]
    clauses = [positive_clause(symptom, dialect_type, rng) for symptom in gold]
    negative_clauses = [negative_clause(symptom, dialect_type, rng) for symptom in negative]
    text = compose_text(
        visit_type=item["visit_type"],
        question_id=item["question_id"],
        dialect_type=dialect_type,
        difficulty=item["difficulty"],
        clauses=clauses,
        negative_clauses=negative_clauses,
        rng=rng,
    )
    text = add_context_variation(text, item["case_id"], dialect_type)
    return {
        "case_id": item["case_id"],
        "visit_type": item["visit_type"],
        "dialect_type": dialect_type,
        "question_id": item["question_id"],
        "text": text,
        "gold_symptoms": gold,
        "negative_symptoms": negative,
        "metadata": {
            "source": "synthetic_public_v1",
            "difficulty": item["difficulty"],
            "generator": "blueprint_template_v1",
        },
    }


def positive_clause(symptom: str, dialect_type: str, rng: random.Random) -> str:
    bank = PHRASE_BANK.get(symptom)
    if bank:
        return rng.choice(bank.get(dialect_type) or bank["standard"])
    suffix = "있어요" if dialect_type == "dialect" else "있습니다"
    return f"{symptom}이 {suffix}"


def negative_clause(symptom: str, dialect_type: str, rng: random.Random) -> str:
    if dialect_type == "dialect":
        templates = [
            f"{symptom}은 이제 거의 없어요",
            f"{symptom}은 좀 나아졌어요",
            f"{symptom}은 지금은 괜찮아요",
        ]
    else:
        templates = [
            f"{symptom}은 현재 없습니다",
            f"{symptom}은 호전되었습니다",
            f"{symptom}은 지금은 괜찮습니다",
        ]
    return rng.choice(templates)


def compose_text(
    *,
    visit_type: str,
    question_id: str,
    dialect_type: str,
    difficulty: str,
    clauses: list[str],
    negative_clauses: list[str],
    rng: random.Random,
) -> str:
    positives = join_clauses(clauses, dialect_type)
    negatives = join_clauses(negative_clauses, dialect_type)
    onset = rng.choice(["어제부터", "오늘 아침부터", "며칠 전부터", "최근에"])
    if dialect_type == "dialect":
        if visit_type == "초진" and question_id == "Q1":
            templates = [
                f"{onset} {positives}.",
                f"{positives} 그래서 좀 불편해요.",
                f"{negatives} 근데 {positives}.",
            ]
        elif visit_type == "초진" and question_id == "Q3":
            templates = [
                f"약은 아직 따로 안 먹고 있고 {positives}.",
                f"집에 있던 약 조금 먹었는데도 {positives}.",
                f"{negatives} 근데 약 먹어도 {positives}.",
            ]
        elif visit_type == "재진" and question_id == "Q1":
            templates = [
                f"지난번보다 {positives}.",
                f"{negatives} 근데 아직 {positives}.",
                f"치료하고 나서도 {positives}.",
            ]
        else:
            templates = [
                f"이번에 새로 {positives}.",
                f"약 먹는 중인데 {positives}.",
                f"{negatives} 근데 새로 {positives}.",
            ]
    else:
        if visit_type == "초진" and question_id == "Q1":
            templates = [
                f"{onset} {positives}.",
                f"{positives} 그래서 진료를 보러 왔습니다.",
                f"{negatives} 그러나 {positives}.",
            ]
        elif visit_type == "초진" and question_id == "Q3":
            templates = [
                f"현재 복용 중인 약은 없고 {positives}.",
                f"약을 먹어도 {positives}.",
                f"{negatives} 그러나 복용 중에도 {positives}.",
            ]
        elif visit_type == "재진" and question_id == "Q1":
            templates = [
                f"지난 진료 이후 {positives}.",
                f"{negatives} 그러나 아직 {positives}.",
                f"치료 후에도 {positives}.",
            ]
        else:
            templates = [
                f"이번에는 새로 {positives}.",
                f"약을 복용하는 중에 {positives}.",
                f"{negatives} 그러나 새로 {positives}.",
            ]
    if not negative_clauses:
        templates = [template for template in templates if "{negatives}" not in template and not template.startswith(" 근데")]
        templates = [template for template in templates if "그러나" not in template or not template.startswith(" 그러나")]
    if difficulty == "easy":
        selected = templates[0]
    elif difficulty == "medium":
        selected = templates[min(1, len(templates) - 1)]
    else:
        selected = templates[-1]
    if negative_clauses and negatives and negatives not in selected:
        bridge = "근데" if dialect_type == "dialect" else "그러나"
        selected = f"{negatives} {bridge} {selected}"
    return selected


def join_clauses(clauses: list[str], dialect_type: str) -> str:
    if not clauses:
        return ""
    if len(clauses) == 1:
        return clauses[0]
    connector = " 그리고 " if dialect_type == "standard" else " 그리고 "
    return connector.join(clauses)


def add_context_variation(text: str, case_id: str, dialect_type: str) -> str:
    """Attach a small neutral context phrase to avoid template duplicates."""
    try:
        index = int(str(case_id).split("_")[-1])
    except ValueError:
        index = 0
    standard_contexts = [
        "하루 정도 이어졌습니다.",
        "이틀째 반복됩니다.",
        "사흘 전부터 이어집니다.",
        "아침에 더 느껴집니다.",
        "밤에 더 불편합니다.",
        "움직이면 더 신경 쓰입니다.",
        "쉬어도 크게 줄지 않습니다.",
        "간헐적으로 반복됩니다.",
        "점점 더 신경 쓰입니다.",
        "진료 전에 확인받고 싶습니다.",
        "일상생활 중에도 느껴집니다.",
        "누워 있을 때도 남아 있습니다.",
        "식사 후에도 이어집니다.",
        "기침하거나 움직일 때 더 느껴집니다.",
        "최근 들어 더 잦아졌습니다.",
        "오전보다 오후에 더 뚜렷합니다.",
        "물을 마셔도 크게 달라지지 않습니다.",
        "가끔 심해졌다가 조금 줄어듭니다.",
        "예전보다 더 자주 느낍니다.",
        "오늘은 특히 불편합니다.",
    ]
    dialect_contexts = [
        "하루 정도 됐어요.",
        "이틀째 그래요.",
        "사흘 전부터 그래요.",
        "아침에 더 그래요.",
        "밤에 더 불편해요.",
        "움직이면 더 신경 쓰여요.",
        "쉬어도 별로 안 줄어요.",
        "왔다 갔다 반복돼요.",
        "점점 더 신경 쓰여요.",
        "진료 전에 확인받고 싶어요.",
        "평소에도 자꾸 느껴져요.",
        "누워 있어도 남아 있어요.",
        "밥 먹고 나서도 그래요.",
        "기침하거나 움직이면 더 그래요.",
        "요즘 들어 더 잦아졌어요.",
        "오후에 더 뚜렷해요.",
        "물 마셔도 별로 안 달라져요.",
        "가끔 심했다가 조금 줄어요.",
        "전보다 더 자주 느껴져요.",
        "오늘은 특히 불편해요.",
    ]
    contexts = dialect_contexts if dialect_type == "dialect" else standard_contexts
    context = contexts[index % len(contexts)]
    days = index % 31 + 1
    repeats = index % 7 + 1
    if dialect_type == "dialect":
        cadence = f"최근 {days}일 사이에 {repeats}번쯤 반복됐어요."
    else:
        cadence = f"최근 {days}일 사이에 {repeats}번 정도 반복됐습니다."
    return f"{text} {context} {cadence}"


def normalize_for_duplicate(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def validate_generated(cases: list[dict[str, Any]]) -> None:
    seen_ids: set[str] = set()
    seen_texts: set[str] = set()
    for case in cases:
        case_id = str(case.get("case_id") or "")
        if case_id in seen_ids:
            raise RuntimeError(f"duplicate case_id: {case_id}")
        seen_ids.add(case_id)
        text = str(case.get("text") or "")
        if not text.strip():
            raise RuntimeError(f"empty text: {case_id}")
        text_key = normalize_for_duplicate(text)
        if text_key in seen_texts:
            raise RuntimeError(f"duplicate text: {case_id}: {text}")
        seen_texts.add(text_key)
        gold = set(case.get("gold_symptoms") or [])
        negative = set(case.get("negative_symptoms") or [])
        if not gold:
            raise RuntimeError(f"empty gold symptoms: {case_id}")
        overlap = gold & negative
        if overlap:
            raise RuntimeError(f"gold/negative overlap in {case_id}: {sorted(overlap)}")


def assign_splits(cases: list[dict[str, Any]]) -> None:
    start = 0
    for split, size in SPLIT_SIZES.items():
        for case in cases[start : start + size]:
            case["metadata"]["split"] = split
        start += size
    if start != len(cases):
        raise RuntimeError(f"Split sizes do not add up to case count: {start} != {len(cases)}")


def summarize(cases: list[dict[str, Any]], seed: int) -> dict[str, Any]:
    visits = Counter(case["visit_type"] for case in cases)
    questions = Counter(case["question_id"] for case in cases)
    dialects = Counter(case["dialect_type"] for case in cases)
    difficulties = Counter(case["metadata"]["difficulty"] for case in cases)
    splits = Counter(case["metadata"]["split"] for case in cases)
    gold = Counter(symptom for case in cases for symptom in case.get("gold_symptoms", []))
    negative = Counter(symptom for case in cases for symptom in case.get("negative_symptoms", []))
    multi_gold = sum(1 for case in cases if len(case.get("gold_symptoms", [])) > 1)
    return {
        "generator": "blueprint_template_v1",
        "seed": seed,
        "case_count": len(cases),
        "split_counts": dict(splits),
        "visit_counts": dict(visits),
        "question_counts": dict(questions),
        "dialect_counts": dict(dialects),
        "difficulty_counts": dict(difficulties),
        "multi_gold_case_count": multi_gold,
        "negative_case_count": sum(1 for case in cases if case.get("negative_symptoms")),
        "unique_gold_symptom_count": len(gold),
        "unique_negative_symptom_count": len(negative),
        "top_gold_symptoms": dict(gold.most_common(20)),
        "top_negative_symptoms": dict(negative.most_common(20)),
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_outputs(cases: list[dict[str, Any]], blueprint: list[dict[str, Any]], output_dir: Path, seed: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "name": "synthetic_public_ir_1000",
        "description": "Public synthetic IR evaluation dataset generated from a fixed blueprint. Not real patient data.",
        "generator": "blueprint_template_v1",
        "seed": seed,
        "split_policy": SPLIT_SIZES,
    }
    write_json(output_dir / "blueprint_1000.json", {"meta": meta, "data": blueprint})
    write_json(output_dir / "synthetic_1000.json", {"meta": meta, "data": cases})
    for split, size in SPLIT_SIZES.items():
        split_cases = [case for case in cases if case["metadata"]["split"] == split]
        if len(split_cases) != size:
            raise RuntimeError(f"Wrong split size for {split}: {len(split_cases)}")
        write_json(output_dir / f"synthetic_{split}_{size}.json", {"meta": {**meta, "split": split}, "data": split_cases})
    write_json(output_dir / "synthetic_summary.json", summarize(cases, seed))
    print(f"wrote {len(cases)} cases to {output_dir}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
