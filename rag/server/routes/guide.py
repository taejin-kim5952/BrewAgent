from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from loguru import logger
from pydantic import BaseModel

from ..dependencies import AppContainer, get_container
from ...dataset.guide_store import GuideRecord, RuleRecord, GeneratedQARecord
from ...llm_router.backends.base import GenerateParams
from ...llm_router.prompts.rule_extraction import (
    RULE_EXTRACTION_SYSTEM,
    build_user_prompt,
    parse_llm_response,
)
from ...llm_router.prompts.qa_generation import (
    QA_GENERATION_SYSTEM,
    build_user_prompt as build_qa_prompt,
    parse_qa_response,
    normalize_qa_type,
)

router = APIRouter()


# ─── 그룹핑 / 컨텍스트 한계 ────────────────────────────
MAX_GROUP_CHARS = 4000   # LLM 한 번에 보낼 최대 문자수
MAX_CHUNK_PER_GROUP = 6  # 그룹당 최대 청크 수


# ─── Pydantic 모델 ────────────────────────────────────

class GuideUploadResponse(BaseModel):
    guide_id: str
    name: str
    status: str


class GuideSummary(BaseModel):
    guide_id: str
    name: str
    source_file: str
    page_count: int
    status: str
    progress: int
    error_msg: str
    rule_count: int
    created_at: str


class GuideListResponse(BaseModel):
    total: int
    items: list[GuideSummary]


class RuleItem(BaseModel):
    rule_id: str
    guide_id: str
    section_label: str
    title: str
    body: str
    category: str
    severity: str
    code_bad: str
    code_good: str
    source_pages: str
    order_index: int
    reviewed: int
    user_edited: int


class RuleListResponse(BaseModel):
    guide_id: str
    total: int
    items: list[RuleItem]


class RuleUpdateRequest(BaseModel):
    section_label: str | None = None
    title: str | None = None
    body: str | None = None
    category: str | None = None
    severity: str | None = None
    code_bad: str | None = None
    code_good: str | None = None
    reviewed: int | None = None


class ManualRuleRequest(BaseModel):
    section_label: str = ""
    title: str
    body: str
    category: str = "기타"
    severity: str = "unknown"
    code_bad: str = ""
    code_good: str = ""


class SplitRuleRequest(BaseModel):
    parts: list[ManualRuleRequest]  # 분할 결과 N개


class MergeRulesRequest(BaseModel):
    rule_ids: list[str]
    merged_title: str
    merged_body: str
    category: str = "기타"
    severity: str = "unknown"


class QAGenerationRequest(BaseModel):
    count_per_rule: int = 5            # 규칙당 생성 개수
    only_reviewed: bool = False        # True면 reviewed=1 규칙만
    overwrite: bool = False            # True면 기존 pending Q&A 삭제 후 재생성


class QAItem(BaseModel):
    qa_id: str
    rule_id: str
    guide_id: str
    qa_type: str
    instruction: str
    output: str
    status: str
    user_edited: int
    created_at: str
    rule_section_label: str = ""
    rule_title: str = ""
    rule_category: str = ""


class QAListResponse(BaseModel):
    guide_id: str
    total: int
    pending: int
    approved: int
    rejected: int
    items: list[QAItem]


class QAUpdateRequest(BaseModel):
    instruction: str | None = None
    output: str | None = None
    qa_type: str | None = None
    status: str | None = None         # pending / approved / rejected


class QABulkActionRequest(BaseModel):
    qa_ids: list[str]
    action: str                        # approve / reject / delete


# ─── 엔드포인트 ────────────────────────────────────────

@router.post("/v1/guide/upload", response_model=GuideUploadResponse)
async def upload_guide(
    name: str = Form(...),
    file: UploadFile = File(...),
    container: AppContainer = Depends(get_container),
):
    """가이드 파일 업로드 + 백그라운드 규칙 추출 시작."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="파일이 비어있습니다.")

    # 임시 디렉터리에 영구 보관 (백그라운드가 처리 후 정리)
    persist_dir = Path(tempfile.mkdtemp(prefix="rag_guide_"))
    persist_path = persist_dir / file.filename
    with open(persist_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    guide_id = await container.guide_store.create_guide(
        name=name.strip() or file.filename,
        source_file=file.filename,
    )
    logger.info(f"가이드 업로드: {guide_id} - {file.filename}")

    # 백그라운드로 분석 시작
    asyncio.create_task(
        _extract_rules_background(container, guide_id, persist_path, persist_dir)
    )

    return GuideUploadResponse(guide_id=guide_id, name=name, status="parsing")


@router.get("/v1/guide/list", response_model=GuideListResponse)
async def list_guides(container: AppContainer = Depends(get_container)):
    guides = await container.guide_store.list_guides()
    items = []
    for g in guides:
        rule_count = await container.guide_store.count_rules(g.guide_id)
        items.append(GuideSummary(
            guide_id=g.guide_id,
            name=g.name,
            source_file=g.source_file,
            page_count=g.page_count,
            status=g.status,
            progress=g.progress,
            error_msg=g.error_msg,
            rule_count=rule_count,
            created_at=g.created_at,
        ))
    return GuideListResponse(total=len(items), items=items)


@router.get("/v1/guide/{guide_id}", response_model=GuideSummary)
async def get_guide(guide_id: str, container: AppContainer = Depends(get_container)):
    g = await container.guide_store.get_guide(guide_id)
    if not g:
        raise HTTPException(status_code=404, detail="가이드를 찾을 수 없습니다.")
    rule_count = await container.guide_store.count_rules(guide_id)
    return GuideSummary(
        guide_id=g.guide_id, name=g.name, source_file=g.source_file,
        page_count=g.page_count, status=g.status, progress=g.progress,
        error_msg=g.error_msg, rule_count=rule_count, created_at=g.created_at,
    )


@router.delete("/v1/guide/{guide_id}")
async def delete_guide(guide_id: str, container: AppContainer = Depends(get_container)):
    deleted = await container.guide_store.delete_guide(guide_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="가이드를 찾을 수 없습니다.")
    return {"guide_id": guide_id, "status": "deleted"}


@router.get("/v1/guide/{guide_id}/rules", response_model=RuleListResponse)
async def list_rules(
    guide_id: str,
    category: str | None = None,
    severity: str | None = None,
    container: AppContainer = Depends(get_container),
):
    rules = await container.guide_store.list_rules(
        guide_id=guide_id, category=category, severity=severity
    )
    items = [_to_rule_item(r) for r in rules]
    return RuleListResponse(guide_id=guide_id, total=len(items), items=items)


@router.post("/v1/guide/{guide_id}/rules", response_model=RuleItem)
async def add_manual_rule(
    guide_id: str,
    req: ManualRuleRequest,
    container: AppContainer = Depends(get_container),
):
    g = await container.guide_store.get_guide(guide_id)
    if not g:
        raise HTTPException(status_code=404, detail="가이드를 찾을 수 없습니다.")
    rule = RuleRecord(
        rule_id=str(uuid.uuid4()),
        guide_id=guide_id,
        section_label=req.section_label,
        title=req.title,
        body=req.body,
        category=req.category,
        severity=req.severity,
        code_bad=req.code_bad,
        code_good=req.code_good,
        order_index=999_999,  # 끝에
        user_edited=1,
    )
    await container.guide_store.insert_rule(rule)
    return _to_rule_item(rule)


@router.patch("/v1/guide/rules/{rule_id}", response_model=RuleItem)
async def update_rule(
    rule_id: str,
    req: RuleUpdateRequest,
    container: AppContainer = Depends(get_container),
):
    fields = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")
    fields["user_edited"] = 1
    ok = await container.guide_store.update_rule(rule_id, **fields)
    if not ok:
        raise HTTPException(status_code=404, detail="규칙을 찾을 수 없습니다.")
    rule = await container.guide_store.get_rule(rule_id)
    return _to_rule_item(rule)


@router.delete("/v1/guide/rules/{rule_id}")
async def delete_rule(rule_id: str, container: AppContainer = Depends(get_container)):
    ok = await container.guide_store.delete_rule(rule_id, soft=True)
    if not ok:
        raise HTTPException(status_code=404, detail="규칙을 찾을 수 없습니다.")
    return {"rule_id": rule_id, "status": "deleted"}


@router.post("/v1/guide/rules/{rule_id}/split", response_model=RuleListResponse)
async def split_rule(
    rule_id: str,
    req: SplitRuleRequest,
    container: AppContainer = Depends(get_container),
):
    if len(req.parts) < 2:
        raise HTTPException(status_code=400, detail="2개 이상으로 분할해야 합니다.")
    original = await container.guide_store.get_rule(rule_id)
    if not original:
        raise HTTPException(status_code=404, detail="규칙을 찾을 수 없습니다.")

    # 원본은 소프트 삭제
    await container.guide_store.delete_rule(rule_id, soft=True)

    # 새 규칙들 삽입 (원본 order 다음 순서)
    base_order = original.order_index
    new_rules: list[RuleRecord] = []
    for i, p in enumerate(req.parts):
        nr = RuleRecord(
            rule_id=str(uuid.uuid4()),
            guide_id=original.guide_id,
            section_label=p.section_label or original.section_label,
            title=p.title,
            body=p.body,
            category=p.category or original.category,
            severity=p.severity or original.severity,
            code_bad=p.code_bad,
            code_good=p.code_good,
            source_pages=original.source_pages,
            order_index=base_order * 10 + i,  # 안정적인 정렬
            user_edited=1,
        )
        await container.guide_store.insert_rule(nr)
        new_rules.append(nr)

    return RuleListResponse(
        guide_id=original.guide_id,
        total=len(new_rules),
        items=[_to_rule_item(r) for r in new_rules],
    )


@router.post("/v1/guide/rules/merge", response_model=RuleItem)
async def merge_rules(
    req: MergeRulesRequest,
    container: AppContainer = Depends(get_container),
):
    if len(req.rule_ids) < 2:
        raise HTTPException(status_code=400, detail="2개 이상의 규칙을 선택해야 합니다.")

    rules: list[RuleRecord] = []
    for rid in req.rule_ids:
        r = await container.guide_store.get_rule(rid)
        if not r:
            raise HTTPException(status_code=404, detail=f"규칙 {rid} 없음")
        rules.append(r)

    guide_ids = {r.guide_id for r in rules}
    if len(guide_ids) != 1:
        raise HTTPException(status_code=400, detail="동일 가이드의 규칙끼리만 병합 가능합니다.")
    guide_id = rules[0].guide_id

    merged_code_bad = "\n\n".join(r.code_bad for r in rules if r.code_bad).strip()
    merged_code_good = "\n\n".join(r.code_good for r in rules if r.code_good).strip()
    merged_pages = ",".join(sorted({p for r in rules for p in r.source_pages.split(",") if p}))
    merged_section = " / ".join(sorted({r.section_label for r in rules if r.section_label}))

    new_rule = RuleRecord(
        rule_id=str(uuid.uuid4()),
        guide_id=guide_id,
        section_label=merged_section,
        title=req.merged_title,
        body=req.merged_body,
        category=req.category,
        severity=req.severity,
        code_bad=merged_code_bad,
        code_good=merged_code_good,
        source_pages=merged_pages,
        order_index=min(r.order_index for r in rules),
        user_edited=1,
    )
    await container.guide_store.insert_rule(new_rule)

    # 원본들 소프트 삭제
    for r in rules:
        await container.guide_store.delete_rule(r.rule_id, soft=True)

    return _to_rule_item(new_rule)


@router.post("/v1/guide/{guide_id}/finalize")
async def finalize_guide(
    guide_id: str,
    container: AppContainer = Depends(get_container),
):
    g = await container.guide_store.get_guide(guide_id)
    if not g:
        raise HTTPException(status_code=404, detail="가이드를 찾을 수 없습니다.")
    rule_count = await container.guide_store.count_rules(guide_id)
    return {
        "guide_id": guide_id,
        "rule_count": rule_count,
        "status": "finalized",
        "message": f"구조 확정됨. {rule_count}개 규칙으로 Q&A 생성을 시작할 수 있습니다.",
    }


# ─── Q&A 생성/검수 엔드포인트 ────────────────────────────────

@router.post("/v1/guide/{guide_id}/generate_qa")
async def generate_qa(
    guide_id: str,
    req: QAGenerationRequest,
    container: AppContainer = Depends(get_container),
):
    """확정된 규칙들을 기반으로 Q&A 자동 생성 (백그라운드 처리)."""
    g = await container.guide_store.get_guide(guide_id)
    if not g:
        raise HTTPException(status_code=404, detail="가이드를 찾을 수 없습니다.")

    rules = await container.guide_store.list_rules(guide_id=guide_id)
    if req.only_reviewed:
        rules = [r for r in rules if r.reviewed == 1]
    if not rules:
        raise HTTPException(
            status_code=400,
            detail="대상 규칙이 없습니다. (only_reviewed=True인 경우 검수된 규칙이 필요)"
        )

    asyncio.create_task(
        _generate_qa_background(container, guide_id, rules, req.count_per_rule, req.overwrite)
    )

    estimated_total = len(rules) * req.count_per_rule
    return {
        "guide_id": guide_id,
        "rule_count": len(rules),
        "count_per_rule": req.count_per_rule,
        "estimated_total": estimated_total,
        "status": "generating",
        "message": f"{len(rules)}개 규칙 × {req.count_per_rule}개 = 약 {estimated_total}개 Q&A 생성 시작",
    }


@router.get("/v1/guide/{guide_id}/qa", response_model=QAListResponse)
async def list_qa(
    guide_id: str,
    qa_type: str | None = None,
    status: str | None = None,
    rule_id: str | None = None,
    container: AppContainer = Depends(get_container),
):
    """가이드의 Q&A 목록 조회."""
    g = await container.guide_store.get_guide(guide_id)
    if not g:
        raise HTTPException(status_code=404, detail="가이드를 찾을 수 없습니다.")

    qa_records = await container.guide_store.list_qa(
        guide_id=guide_id, qa_type=qa_type, status=status, rule_id=rule_id,
    )

    rules = await container.guide_store.list_rules(guide_id=guide_id, include_deleted=True)
    rule_map = {r.rule_id: r for r in rules}

    items = []
    for q in qa_records:
        r = rule_map.get(q.rule_id)
        items.append(QAItem(
            qa_id=q.qa_id, rule_id=q.rule_id, guide_id=q.guide_id,
            qa_type=q.qa_type, instruction=q.instruction, output=q.output,
            status=q.status, user_edited=q.user_edited, created_at=q.created_at,
            rule_section_label=r.section_label if r else "",
            rule_title=r.title if r else "",
            rule_category=r.category if r else "",
        ))

    pending = await container.guide_store.count_qa(guide_id, "pending")
    approved = await container.guide_store.count_qa(guide_id, "approved")
    rejected = await container.guide_store.count_qa(guide_id, "rejected")

    return QAListResponse(
        guide_id=guide_id, total=len(items),
        pending=pending, approved=approved, rejected=rejected,
        items=items,
    )


@router.patch("/v1/guide/qa/{qa_id}", response_model=QAItem)
async def update_qa(
    qa_id: str,
    req: QAUpdateRequest,
    container: AppContainer = Depends(get_container),
):
    fields = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")

    if "status" in fields and fields["status"] not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="status는 pending/approved/rejected 중 하나여야 합니다.")

    if "instruction" in fields or "output" in fields:
        fields["user_edited"] = 1

    ok = await container.guide_store.update_qa(qa_id, **fields)
    if not ok:
        raise HTTPException(status_code=404, detail="Q&A를 찾을 수 없습니다.")

    qa = await container.guide_store.get_qa(qa_id)
    rule = await container.guide_store.get_rule(qa.rule_id) if qa else None
    return QAItem(
        qa_id=qa.qa_id, rule_id=qa.rule_id, guide_id=qa.guide_id,
        qa_type=qa.qa_type, instruction=qa.instruction, output=qa.output,
        status=qa.status, user_edited=qa.user_edited, created_at=qa.created_at,
        rule_section_label=rule.section_label if rule else "",
        rule_title=rule.title if rule else "",
        rule_category=rule.category if rule else "",
    )


@router.delete("/v1/guide/qa/{qa_id}")
async def delete_qa(qa_id: str, container: AppContainer = Depends(get_container)):
    ok = await container.guide_store.delete_qa(qa_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Q&A를 찾을 수 없습니다.")
    return {"qa_id": qa_id, "status": "deleted"}


@router.post("/v1/guide/qa/bulk")
async def bulk_qa_action(
    req: QABulkActionRequest,
    container: AppContainer = Depends(get_container),
):
    if req.action not in {"approve", "reject", "delete"}:
        raise HTTPException(status_code=400, detail="action은 approve/reject/delete")
    if not req.qa_ids:
        raise HTTPException(status_code=400, detail="qa_ids가 비어있습니다.")

    affected = 0
    for qa_id in req.qa_ids:
        if req.action == "delete":
            if await container.guide_store.delete_qa(qa_id):
                affected += 1
        else:
            new_status = "approved" if req.action == "approve" else "rejected"
            if await container.guide_store.update_qa(qa_id, status=new_status):
                affected += 1
    return {"action": req.action, "affected": affected}


@router.post("/v1/guide/rules/{rule_id}/regenerate_qa")
async def regenerate_qa_for_rule(
    rule_id: str,
    count: int = 5,
    container: AppContainer = Depends(get_container),
):
    """특정 규칙의 Q&A만 다시 생성."""
    rule = await container.guide_store.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="규칙을 찾을 수 없습니다.")

    # 기존 pending Q&A 삭제
    await container.guide_store.delete_qa_by_rule(rule_id)

    asyncio.create_task(
        _generate_qa_background(container, rule.guide_id, [rule], count, overwrite=False)
    )
    return {
        "rule_id": rule_id,
        "guide_id": rule.guide_id,
        "estimated_count": count,
        "status": "generating",
    }


# ─── 백그라운드 추출 ────────────────────────────────────

async def _extract_rules_background(
    container: AppContainer,
    guide_id: str,
    file_path: Path,
    cleanup_dir: Path,
) -> None:
    """파일 파싱 → LLM 호출 → rules 테이블 INSERT.

    chat.py 의 _log_and_eval 패턴과 동일한 fire-and-forget 방식.
    """
    import time
    short_id = guide_id[:8]
    t0 = time.time()
    try:
        # 1. 파싱
        logger.info(f"[guide {short_id}] 파싱 시작: {file_path.name}")
        parse_result = container.pipeline.dispatcher.parse(str(file_path))
        if not parse_result.chunks:
            err = parse_result.errors or ['청크 없음']
            logger.error(f"[guide {short_id}] 파싱 실패: {err}")
            await container.guide_store.update_guide_status(
                guide_id, status="failed",
                error_msg=f"문서 파싱 실패: {err}",
            )
            return

        # 페이지 수 추정 (page_or_line 의 max)
        page_numbers = [c.page_or_line for c in parse_result.chunks if c.page_or_line]
        page_count = max(page_numbers) if page_numbers else len(parse_result.chunks)
        logger.info(
            f"[guide {short_id}] 파싱 완료: {len(parse_result.chunks)} 청크, "
            f"{page_count} 페이지 ({time.time() - t0:.1f}s)"
        )

        await container.guide_store.update_guide_status(
            guide_id, status="extracting", page_count=page_count, progress=5,
        )

        # 2. 청크 그룹핑
        groups = _group_chunks(parse_result.chunks)
        total_groups = len(groups)
        if total_groups == 0:
            logger.error(f"[guide {short_id}] 그룹 0개")
            await container.guide_store.update_guide_status(
                guide_id, status="failed", error_msg="처리할 청크가 없습니다.",
            )
            return

        backend = container.llm_router.full_backend
        logger.info(
            f"[guide {short_id}] 추출 시작: {total_groups} 그룹, "
            f"모델={backend.model_name}"
        )
        params = GenerateParams(
            temperature=0.2, max_tokens=2500,
            system_prompt=RULE_EXTRACTION_SYSTEM,
        )

        order_counter = 0
        auto_counter = 0
        total_rules_inserted = 0

        # 3. 그룹별 LLM 호출
        for idx, group in enumerate(groups):
            text = "\n\n".join(c.content for c in group)
            pages = sorted({c.page_or_line for c in group if c.page_or_line})
            page_range = f"{pages[0]}-{pages[-1]}" if pages else ""
            page_str = ",".join(str(p) for p in pages)

            tg = time.time()
            logger.info(
                f"[guide {short_id}] 그룹 {idx+1}/{total_groups} 처리 중 "
                f"(페이지 {page_range or '?'}, {len(text)}자)"
            )

            prompt = build_user_prompt(text, page_range)

            extracted: list[dict] = []
            llm_error = None
            for attempt in range(2):  # 최대 2회 시도
                try:
                    response = await backend.generate(prompt, params)
                    extracted = parse_llm_response(response)
                    if extracted or attempt == 1:
                        break
                    logger.warning(
                        f"[guide {short_id}] 그룹 {idx+1} 시도 {attempt+1}: "
                        f"JSON 파싱 실패, 재시도"
                    )
                except Exception as e:
                    llm_error = str(e)
                    logger.warning(
                        f"[guide {short_id}] 그룹 {idx+1} 시도 {attempt+1} 실패: {e}"
                    )
                    if attempt == 1:
                        break

            # 4. 규칙 저장
            inserted_in_group = 0
            for r in extracted:
                if not isinstance(r, dict):
                    continue
                title = (r.get("title") or "").strip()
                body = (r.get("body") or "").strip()
                if not title or not body:
                    continue

                section_label = (r.get("section_label") or "").strip()
                if not section_label:
                    auto_counter += 1
                    section_label = f"AUTO-{auto_counter:03d}"

                rule = RuleRecord(
                    rule_id=str(uuid.uuid4()),
                    guide_id=guide_id,
                    section_label=section_label,
                    title=title[:200],
                    body=body,
                    category=_normalize_category(r.get("category")),
                    severity=_normalize_severity(r.get("severity")),
                    code_bad=(r.get("code_bad") or "").strip(),
                    code_good=(r.get("code_good") or "").strip(),
                    source_pages=page_str,
                    order_index=order_counter,
                )
                order_counter += 1
                try:
                    await container.guide_store.insert_rule(rule)
                    inserted_in_group += 1
                    total_rules_inserted += 1
                except Exception as e:
                    logger.warning(f"[guide {short_id}] insert 실패: {e}")

            elapsed_g = time.time() - tg
            if extracted:
                logger.info(
                    f"[guide {short_id}] 그룹 {idx+1}/{total_groups} 완료: "
                    f"{inserted_in_group}/{len(extracted)} 규칙 저장 ({elapsed_g:.1f}s)"
                )
            else:
                logger.warning(
                    f"[guide {short_id}] 그룹 {idx+1}/{total_groups} 결과 없음 "
                    f"({elapsed_g:.1f}s){' - LLM 오류: ' + llm_error if llm_error else ''}"
                )

            # 진행률 업데이트 (5% ~ 95%)
            progress = 5 + int(90 * (idx + 1) / total_groups)
            await container.guide_store.update_guide_status(
                guide_id, progress=progress,
            )

        # 5. 완료
        await container.guide_store.update_guide_status(
            guide_id, status="done", progress=100,
        )
        elapsed = time.time() - t0
        logger.info(
            f"[guide {short_id}] ✓ 추출 완료: {total_rules_inserted} 규칙, "
            f"{total_groups} 그룹 처리, {elapsed:.1f}s 소요"
        )

    except Exception as e:
        logger.exception(f"[guide {guide_id}] 백그라운드 처리 실패")
        await container.guide_store.update_guide_status(
            guide_id, status="failed", error_msg=str(e)[:500],
        )
    finally:
        shutil.rmtree(cleanup_dir, ignore_errors=True)


def _group_chunks(chunks) -> list[list]:
    """청크들을 LLM 컨텍스트에 맞게 그룹핑."""
    groups: list[list] = []
    current: list = []
    current_chars = 0
    for c in chunks:
        clen = len(c.content)
        if current and (current_chars + clen > MAX_GROUP_CHARS or len(current) >= MAX_CHUNK_PER_GROUP):
            groups.append(current)
            current = []
            current_chars = 0
        current.append(c)
        current_chars += clen
    if current:
        groups.append(current)
    return groups


_VALID_CATEGORIES = {
    "보안", "품질", "네이밍", "테스트", "로깅",
    "트랜잭션", "API", "성능", "예외처리", "기타",
}

_VALID_SEVERITIES = {"must", "should", "may", "unknown"}


def _normalize_category(value) -> str:
    if not value or not isinstance(value, str):
        return "기타"
    v = value.strip()
    return v if v in _VALID_CATEGORIES else "기타"


def _normalize_severity(value) -> str:
    if not value or not isinstance(value, str):
        return "unknown"
    v = value.strip().lower()
    return v if v in _VALID_SEVERITIES else "unknown"


def _to_rule_item(r: RuleRecord) -> RuleItem:
    return RuleItem(
        rule_id=r.rule_id, guide_id=r.guide_id,
        section_label=r.section_label, title=r.title, body=r.body,
        category=r.category, severity=r.severity,
        code_bad=r.code_bad, code_good=r.code_good,
        source_pages=r.source_pages, order_index=r.order_index,
        reviewed=r.reviewed, user_edited=r.user_edited,
    )


# ─── Q&A 백그라운드 생성 ────────────────────────────────────

async def _generate_qa_background(
    container: AppContainer,
    guide_id: str,
    rules: list[RuleRecord],
    count_per_rule: int,
    overwrite: bool,
) -> None:
    """규칙들을 순회하며 LLM으로 Q&A 쌍을 생성, generated_qa 테이블에 저장."""
    import time
    short_gid = guide_id[:8]
    t0 = time.time()
    total_inserted = 0
    failed_rules = 0

    backend = container.llm_router.full_backend
    params = GenerateParams(
        temperature=0.5, max_tokens=3500,
        system_prompt=QA_GENERATION_SYSTEM,
    )

    logger.info(
        f"[qa-gen {short_gid}] 시작: {len(rules)} 규칙 × {count_per_rule}, "
        f"모델={backend.model_name}"
    )

    for idx, rule in enumerate(rules):
        # overwrite=True면 해당 규칙의 기존 Q&A 모두 삭제 (status 무관)
        if overwrite:
            removed = await container.guide_store.delete_qa_by_rule(rule.rule_id)
            if removed:
                logger.info(f"[qa-gen {short_gid}] 규칙 {rule.section_label}: 기존 {removed}개 삭제")

        rule_dict = {
            "section_label": rule.section_label,
            "title": rule.title,
            "body": rule.body,
            "category": rule.category,
            "severity": rule.severity,
            "code_bad": rule.code_bad,
            "code_good": rule.code_good,
        }
        prompt = build_qa_prompt(rule_dict, count=count_per_rule)

        tg = time.time()
        logger.info(
            f"[qa-gen {short_gid}] 규칙 {idx+1}/{len(rules)} 처리 중: "
            f"{rule.section_label} {rule.title[:50]}"
        )

        extracted: list[dict] = []
        last_err = None
        for attempt in range(2):
            try:
                response = await backend.generate(prompt, params)
                extracted = parse_qa_response(response)
                if extracted or attempt == 1:
                    break
                logger.warning(
                    f"[qa-gen {short_gid}] 규칙 {idx+1} 시도 {attempt+1}: JSON 파싱 실패, 재시도"
                )
            except Exception as e:
                last_err = str(e)
                logger.warning(
                    f"[qa-gen {short_gid}] 규칙 {idx+1} 시도 {attempt+1} 실패: {e}"
                )
                if attempt == 1:
                    break

        if not extracted:
            failed_rules += 1
            logger.warning(
                f"[qa-gen {short_gid}] 규칙 {idx+1} 결과 없음 ({time.time()-tg:.1f}s)"
                f"{' - 오류: ' + last_err if last_err else ''}"
            )
            continue

        inserted = 0
        for qa_data in extracted:
            if not isinstance(qa_data, dict):
                continue
            instruction = (qa_data.get("instruction") or "").strip()
            output = (qa_data.get("output") or "").strip()
            if not instruction or not output:
                continue
            qa_type = normalize_qa_type(qa_data.get("qa_type"))

            qa = GeneratedQARecord(
                qa_id=str(uuid.uuid4()),
                rule_id=rule.rule_id,
                guide_id=guide_id,
                qa_type=qa_type,
                instruction=instruction,
                output=output,
                status="pending",
            )
            try:
                await container.guide_store.insert_qa(qa)
                inserted += 1
                total_inserted += 1
            except Exception as e:
                logger.warning(f"[qa-gen {short_gid}] insert 실패: {e}")

        logger.info(
            f"[qa-gen {short_gid}] 규칙 {idx+1}/{len(rules)} 완료: "
            f"{inserted}/{len(extracted)} Q&A 저장 ({time.time()-tg:.1f}s)"
        )

    elapsed = time.time() - t0
    logger.info(
        f"[qa-gen {short_gid}] ✓ 생성 완료: 총 {total_inserted}개 Q&A, "
        f"실패 규칙 {failed_rules}, {elapsed:.1f}s 소요"
    )
