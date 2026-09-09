"""
Action Executor (ACT Phase) for Goal-Driven Agent Core V1.1.
Executes atomic, verifiable, and idempotent actions:
- CATALOG_LOOKUP
- RETRIEVE_EXACT (RAG exact metadata filtering on ChromaDB + BM25)
- RETRIEVE_EXPANDED (RAG search with catalog expansion, strictly entity-scoped)
- COMPARE_EVIDENCE
- ASK_USER
- PARTIAL_ANSWER
- ABSTAIN
- FINISH
Reuses existing RAG infrastructure with 0 second-retrieval architectures and 0 external LLM calls.
"""
import re
import json
from typing import Optional, Any

from src.agent_core.schemas import (
    ActionPlan,
    ActionObservation,
    ActionType,
    AgentGoalState,
    AgentStatus,
    StopReason,
    EvidenceStatus,
    QuestionType,
    EvidenceRequirement,
    EvidenceItem,
)
from src.agent_core.entity_catalog import get_entity_catalog, EntityCatalog
from src.agent_core.environment_catalog import get_knowledge_environment_catalog, KnowledgeEnvironmentCatalog
from src.agent_core.verifier import get_evidence_verifier, EvidenceVerifier
from src.rag.hybrid_retriever import get_collection_retriever

FIELD_NAMES_VN = {
    "credits": "số tín chỉ",
    "lecturer": "giảng viên",
    "lecturer_email": "email giảng viên",
    "assessment": "hình thức đánh giá",
    "clo": "chuẩn đầu ra (CLO)",
    "objectives": "mục tiêu môn học",
    "hours": "số giờ học",
    "department": "khoa phụ trách",
    "english_name": "tên tiếng Anh",
    "prerequisites": "môn tiên quyết",
    "course_plan": "kế hoạch giảng dạy",
    "graduation_requirements": "điều kiện tốt nghiệp",
    "academic_warning": "cảnh báo học vụ",
    "training_rules": "quy chế đào tạo",
}


def format_requirement_answer(r: EvidenceRequirement, catalog: Optional[EntityCatalog] = None) -> str:
    """Định dạng kết quả trả lời học vụ tự nhiên, hội thoại, có cấu trúc thẩm mỹ cho người dùng."""
    from src.agent_core import presentation
    from src.agent_core.schemas import EntityType

    if r.data_capability == "STRUCTURED_CURRICULUM" or r.subject_type in (EntityType.CURRICULUM, EntityType.COHORT, EntityType.MAJOR, EntityType.SEMESTER):
        cohort = r.filters.get("cohort", "K19") if r.filters else "K19"
        major = r.filters.get("major", "Khoa học máy tính") if r.filters else "Khoa học máy tính"
        if r.field in ("GET_TOTAL_CREDITS", "total_credits"):
            return presentation.format_total_credits(r.extracted_value)
        elif r.field in ("GET_SEMESTER_COURSES", "courses"):
            sem = r.filters.get("semester", 1) if r.filters else 1
            return presentation.format_semester_courses(sem, r.extracted_value, cohort, major)
        elif r.field in ("FIND_COURSE_SEMESTER", "semester"):
            return presentation.format_course_placement(r.extracted_value, cohort, major)
        elif r.field in ("LIST_COURSES", "curriculum"):
            return presentation.format_curriculum_overview(r.extracted_value, cohort, major)

    f_vn = FIELD_NAMES_VN.get(r.field, r.field)
    c_info = catalog.get_course_info(r.entity) if catalog and r.entity and r.entity not in ("DNTU", "general") else None
    c_name = c_info.get("canonical_name", "") if c_info else ""

    if r.field == "credits":
        return presentation.format_credits(r.entity, c_name, r.extracted_value)
    elif r.field == "lecturer":
        return presentation.format_lecturer(r.entity, c_name, r.extracted_value)
    elif r.field == "lecturer_email":
        return presentation.format_lecturer_email(r.entity, c_name, r.extracted_value)
    elif r.field == "clo":
        return presentation.format_clo(r.entity, c_name, r.extracted_value)
    elif r.field == "assessment":
        return presentation.format_assessment(r.entity, c_name, r.extracted_value)
    elif r.field == "prerequisites":
        return presentation.format_prerequisites(r.entity, c_name, r.extracted_value)
    elif r.field == "graduation_requirements":
        return presentation.format_graduation(r.entity, r.extracted_value)
    elif r.field == "academic_warning":
        return presentation.format_academic_warning(r.entity, r.extracted_value)
    else:
        return presentation.format_generic(f_vn, r.entity, c_name, r.extracted_value)



class ActionExecutor:
    """Bộ thực thi hành động học vụ an toàn, tái sử dụng hạ tầng RAG chính quy."""

    def __init__(
        self,
        entity_catalog: Optional[EntityCatalog] = None,
        env_catalog: Optional[KnowledgeEnvironmentCatalog] = None,
        verifier: Optional[EvidenceVerifier] = None,
    ):
        self.entity_catalog = entity_catalog or get_entity_catalog()
        self.env_catalog = env_catalog or get_knowledge_environment_catalog()
        self.verifier = verifier or get_evidence_verifier()

    def execute(self, plan: ActionPlan, state: AgentGoalState, event_sink: Optional[Any] = None) -> ActionObservation:
        """Thực thi một kế hoạch hành động đã được lập."""
        a_type = plan.action_type

        if a_type == ActionType.EXECUTE_STRUCTURED_QUERY:
            return self._execute_structured_query(plan, state, event_sink=event_sink)
        elif a_type == ActionType.CATALOG_LOOKUP:
            return self._execute_catalog_lookup(plan, state, event_sink=event_sink)
        elif a_type == ActionType.RETRIEVE_EXACT:
            return self._execute_exact_retrieval(plan, state, event_sink=event_sink)
        elif a_type == ActionType.RETRIEVE_EXPANDED:
            return self._execute_expanded_retrieval(plan, state, event_sink=event_sink)
        elif a_type == ActionType.COMPARE_EVIDENCE:
            return self._execute_compare_evidence(plan, state, event_sink=event_sink)
        elif a_type == ActionType.ASK_USER:
            return self._execute_ask_user(plan, state, event_sink=event_sink)
        elif a_type == ActionType.PARTIAL_ANSWER:
            return self._execute_partial_answer(plan, state, event_sink=event_sink)
        elif a_type == ActionType.ABSTAIN:
            return self._execute_abstain(plan, state, event_sink=event_sink)
        elif a_type == ActionType.FINISH:
            return self._execute_finish(plan, state, event_sink=event_sink)
        else:
            return ActionObservation(
                action_id=plan.action_id,
                action_type=plan.action_type,
                success=False,
                message=f"Hành động chưa được hỗ trợ: {a_type}",
            )

    def _execute_structured_query(self, plan: ActionPlan, state: AgentGoalState, event_sink: Optional[Any] = None) -> ActionObservation:
        """Thực thi truy vấn tri thức học vụ có cấu trúc (SQLite Structured Academic Store) với đầy đủ provenance."""
        from src.agent_core.academic_store import get_academic_store
        store = get_academic_store()

        target_req = next(
            (r for r in state.requirements if r.requirement_key == plan.target_requirement_key or (r.entity == plan.entity and r.field == plan.requested_field)),
            None
        )
        if not target_req and state.requirements:
            target_req = state.requirements[0]

        if event_sink:
            event_sink.emit_phase("VERIFY", "Đang truy vấn kho dữ liệu CTĐT có cấu trúc...")

        # Lấy hoặc dựng AcademicQueryPlan
        query_plan = state.query_plan
        if not query_plan:
            from src.agent_core.schemas import AcademicQueryPlan, EntityType
            filters = target_req.filters if target_req else {}
            query_plan = AcademicQueryPlan(
                plan_id=f"plan_{plan.action_id}",
                subject_type=target_req.subject_type if target_req else EntityType.CURRICULUM,
                operation=target_req.field if target_req else "LIST_COURSES",
                filters=filters,
                data_capability="STRUCTURED_CURRICULUM",
                accepted_sources=["curriculum"],
            )

        res = store.execute_query(query_plan)
        if target_req:
            target_req.attempt_count += 1

        if res.get("status") == "success" and res.get("data") is not None:
            prov = res.get("source_provenance", {})
            raw_content = json.dumps(res["data"], ensure_ascii=False) if isinstance(res["data"], (dict, list)) else str(res["data"])

            item = EvidenceItem(
                entity=target_req.entity if target_req else (plan.entity or "curriculum"),
                field=target_req.field if target_req else (plan.requested_field or "curriculum"),
                document_type="curriculum",
                content=raw_content,
                source=prov.get("source_file") or "academic_store.sqlite3",
                source_file=prov.get("source_file"),
                section=prov.get("source_section"),
                chunk_id=prov.get("source_chunk_id"),
                metadata={"data": res["data"], "operation": res["operation"], "provenance": prov, "source_hash": prov.get("source_hash")},
                is_authoritative=True,
                status=EvidenceStatus.VERIFIED_VALUE,
                relevance_score=1.0,
            )
            if target_req:
                target_req.status = EvidenceStatus.VERIFIED_VALUE
                target_req.extracted_value = res["data"]
                target_req.source_doc_id = prov.get("source_file")
            state.evidence.append(item)

            return ActionObservation(
                action_id=plan.action_id,
                action_type=plan.action_type,
                success=True,
                new_evidence_count=1,
                requirements_satisfied=[target_req.requirement_key] if target_req else [],
                evidence_items=[item],
                message=f"Đã truy vấn thành công kho CTĐT ({res.get('record_count', 1)} bản ghi)",
            )

        if target_req:
            target_req.status = EvidenceStatus.NOT_AVAILABLE
        return ActionObservation(
            action_id=plan.action_id,
            action_type=plan.action_type,
            success=False,
            message="Không tìm thấy dữ liệu phù hợp trong kho CTĐT.",
        )

    def _execute_catalog_lookup(self, plan: ActionPlan, state: AgentGoalState, event_sink: Optional[Any] = None) -> ActionObservation:
        """Tra cứu nhanh danh mục chính thống từ metadata/manifests có nguồn gốc provenance."""
        target_req = next(
            (r for r in state.requirements if r.entity == plan.entity and r.field == plan.requested_field),
            None
        )
        if not target_req and state.requirements:
            target_req = state.requirements[0]

        if not target_req:
            return ActionObservation(
                action_id=plan.action_id,
                action_type=plan.action_type,
                success=False,
                message="Không tìm thấy requirement mục tiêu.",
            )

        if event_sink:
            event_sink.emit_phase("VERIFY", "Đang xác minh bằng chứng...")

        status, item = self.verifier.verify_requirement(target_req, [], retrieval_strategy="catalog")
        target_req.status = status
        target_req.attempt_count += 1

        if status in (EvidenceStatus.SATISFIED, EvidenceStatus.VERIFIED_VALUE, EvidenceStatus.VERIFIED_NONE) and item:
            target_req.extracted_value = item.content
            target_req.source_doc_id = item.source
            state.evidence.append(item)
            return ActionObservation(
                action_id=plan.action_id,
                action_type=plan.action_type,
                success=True,
                new_evidence_count=1,
                requirements_satisfied=[target_req.requirement_key],
                evidence_items=[item],
                message=f"Đã tra cứu thành công {target_req.requirement_key}: {item.content}",
            )

        return ActionObservation(
            action_id=plan.action_id,
            action_type=plan.action_type,
            success=False,
            message=f"Catalog lookup không thỏa mãn {target_req.requirement_key}",
        )

    def _execute_exact_retrieval(self, plan: ActionPlan, state: AgentGoalState, event_sink: Optional[Any] = None) -> ActionObservation:
        """Truy xuất chính xác qua RAG sử dụng metadata filtering theo course_code và document_type."""
        target_req = next(
            (r for r in state.requirements if r.entity == plan.entity and r.field == plan.requested_field),
            None
        )
        if not target_req and state.requirements:
            target_req = state.requirements[0]

        if not target_req:
            return ActionObservation(
                action_id=plan.action_id,
                action_type=plan.action_type,
                success=False,
                message="Không tìm thấy requirement mục tiêu.",
            )

        collections_to_search = []
        for doc_type in target_req.accepted_document_types:
            if doc_type in ("course_detail", "course_outline"):
                collections_to_search.append("course_detail")
            elif doc_type == "curriculum":
                collections_to_search.append("curriculum")
            elif doc_type == "regulation":
                collections_to_search.append("regulation")

        if not collections_to_search:
            collections_to_search = ["course_detail", "curriculum"]

        where_filter = {"course_code": target_req.entity} if target_req.entity and target_req.entity not in ("DNTU", "general") else None
        matching_docs = []

        for col_name in collections_to_search:
            try:
                retriever = get_collection_retriever(col_name)
                # 1. Exact metadata query trực tiếp trên Chroma Persistent Collection
                if where_filter and retriever.collection:
                    res = retriever.collection.get(where=where_filter, limit=100)
                    if res and res.get("documents"):
                        paired = sorted(
                            zip(res["ids"], res["metadatas"], res["documents"]),
                            key=lambda x: int(re.search(r"chunk(\d+)", str(x[0])).group(1)) if re.search(r"chunk(\d+)", str(x[0])) else 999
                        )
                        for cid, meta, text in paired:
                            matching_docs.append({
                                "id": cid,
                                "chunk_id": cid,
                                "text": text,
                                "content": text,
                                "metadata": meta or {},
                                "document_type": (meta or {}).get("document_type", col_name),
                                "source_file": (meta or {}).get("source_file", ""),
                                "section": (meta or {}).get("section", ""),
                            })
                elif not where_filter and col_name == "regulation" and retriever.bm25_index:
                    f_vn = FIELD_NAMES_VN.get(target_req.field, "")
                    query_str = f"{target_req.field} {f_vn}"
                    b_docs = retriever.bm25_search(query_str, top_k=5)
                    for d in b_docs:
                        d["content"] = d.get("text", "")
                        matching_docs.append(d)

                # 2. Nếu chưa có docs, truy xuất qua BM25
                if not matching_docs and retriever.bm25_index:
                    f_vn = FIELD_NAMES_VN.get(target_req.field, "")
                    query_str = f"{target_req.field} {f_vn}" if target_req.entity in ("DNTU", "general") else f"{target_req.entity} {target_req.field}"
                    b_docs = retriever.bm25_search(query_str, top_k=5)
                    for d in b_docs:
                        d["content"] = d.get("text", "")
                        matching_docs.append(d)
            except Exception:
                pass

        if event_sink:
            event_sink.emit_phase("VERIFY", "Đang xác minh bằng chứng...")

        status, item = self.verifier.verify_requirement(target_req, matching_docs, retrieval_strategy="exact")
        target_req.status = status
        target_req.attempt_count += 1

        sat_keys = []
        new_ev_items = []
        if status in (EvidenceStatus.SATISFIED, EvidenceStatus.VERIFIED_VALUE, EvidenceStatus.VERIFIED_NONE) and item:
            target_req.extracted_value = item.content
            target_req.source_doc_id = item.source
            state.evidence.append(item)
            sat_keys.append(target_req.requirement_key)
            new_ev_items.append(item)

        # Batch verify: Thẩm định các requirement khác cùng thực thể từ matching_docs đã tải
        if matching_docs:
            for other_req in state.requirements:
                if (
                    other_req.requirement_key != target_req.requirement_key
                    and other_req.entity == target_req.entity
                    and other_req.status == EvidenceStatus.PENDING
                ):
                    o_status, o_item = self.verifier.verify_requirement(other_req, matching_docs, retrieval_strategy="exact")
                    other_req.attempt_count += 1
                    if o_status in (EvidenceStatus.SATISFIED, EvidenceStatus.VERIFIED_VALUE, EvidenceStatus.VERIFIED_NONE) and o_item:
                        other_req.status = o_status
                        other_req.extracted_value = o_item.content
                        other_req.source_doc_id = o_item.source
                        state.evidence.append(o_item)
                        sat_keys.append(other_req.requirement_key)
                        new_ev_items.append(o_item)

        if sat_keys:
            return ActionObservation(
                action_id=plan.action_id,
                action_type=plan.action_type,
                success=True,
                documents_found=len(matching_docs),
                new_evidence_count=len(new_ev_items),
                requirements_satisfied=sat_keys,
                evidence_items=new_ev_items,
                message=f"Đã thu thập bằng chứng cho {', '.join(sat_keys)}",
            )
        else:
            return ActionObservation(
                action_id=plan.action_id,
                action_type=plan.action_type,
                success=False,
                documents_found=len(matching_docs),
                new_evidence_count=0,
                requirements_satisfied=[],
                message=f"Exact retrieval không tìm thấy thông tin hợp lệ cho {target_req.requirement_key}",
            )

    def _execute_expanded_retrieval(self, plan: ActionPlan, state: AgentGoalState, event_sink: Optional[Any] = None) -> ActionObservation:
        """Truy xuất mở rộng qua Hybrid Search (dense + BM25 + RRF) khi exact retrieval không tìm thấy, bảo vệ nghiêm ngặt không chéo thực thể."""
        target_req = next(
            (r for r in state.requirements if r.entity == plan.entity and r.field == plan.requested_field),
            None
        )
        if not target_req and state.requirements:
            target_req = state.requirements[0]

        if not target_req:
            return ActionObservation(
                action_id=plan.action_id,
                action_type=plan.action_type,
                success=False,
                message="Không tìm thấy requirement mục tiêu.",
            )

        c_info = self.entity_catalog.get_course_info(target_req.entity)
        c_name = c_info.get("canonical_name", "") if c_info else ""
        aliases = c_info.get("aliases", []) if c_info else []
        alias_str = " ".join(aliases[:2])

        query_str = f"{target_req.entity} {c_name} {alias_str} {target_req.field}".strip()

        collections_to_search = ["course_detail", "curriculum", "regulation"]
        matching_docs = []

        where_filter = {"course_code": target_req.entity} if target_req.entity and target_req.entity not in ("DNTU", "general") else None

        for col_name in collections_to_search:
            try:
                retriever = get_collection_retriever(col_name)
                # Hybrid search: dense + BM25 + RRF
                docs = retriever.hybrid_search(query_str, top_k=5, where_filter=where_filter)
                for d in docs:
                    d_code = d.get("metadata", {}).get("course_code")
                    if d_code and target_req.entity and d_code != target_req.entity:
                        continue
                    d["content"] = d.get("text", "")
                    matching_docs.append(d)
            except Exception:
                pass

        if event_sink:
            event_sink.emit_phase("VERIFY", "Đang xác minh bằng chứng...")

        status, item = self.verifier.verify_requirement(target_req, matching_docs, retrieval_strategy="expanded")
        target_req.status = status
        target_req.attempt_count += 1

        if status in (EvidenceStatus.SATISFIED, EvidenceStatus.VERIFIED_VALUE, EvidenceStatus.VERIFIED_NONE) and item:
            target_req.extracted_value = item.content
            target_req.source_doc_id = item.source
            state.evidence.append(item)
            return ActionObservation(
                action_id=plan.action_id,
                action_type=plan.action_type,
                success=True,
                documents_found=len(matching_docs),
                new_evidence_count=1,
                requirements_satisfied=[target_req.requirement_key],
                evidence_items=[item],
                message=f"Đã thu thập bằng chứng mở rộng cho {target_req.requirement_key}: {item.content}",
            )
        else:
            return ActionObservation(
                action_id=plan.action_id,
                action_type=plan.action_type,
                success=False,
                documents_found=len(matching_docs),
                new_evidence_count=0,
                requirements_satisfied=[],
                message=f"Expanded retrieval không tìm thấy thông tin hợp lệ cho {target_req.requirement_key}",
            )

    def _execute_compare_evidence(self, plan: ActionPlan, state: AgentGoalState, event_sink: Optional[Any] = None) -> ActionObservation:
        """Tổng hợp so sánh đa thực thể dựa trên các bằng chứng đã thẩm định."""
        valid_statuses = (EvidenceStatus.SATISFIED, EvidenceStatus.VERIFIED_VALUE, EvidenceStatus.VERIFIED_NONE)
        fields = list(set(r.field for r in state.requirements if r.status in valid_statuses))
        comparison_lines = [f"### So sánh các học phần: {', '.join(state.entities)}"]

        for f in fields:
            f_title = FIELD_NAMES_VN.get(f, f.replace("_", " ").title())
            comparison_lines.append(f"\n- **{f_title.title()}**:")
            for ent in state.entities:
                val = next((r.extracted_value for r in state.requirements if r.entity == ent and r.field == f and r.status in valid_statuses), "Chưa có thông tin")
                comparison_lines.append(f"  + **{ent}**: {val}")

        state.final_answer = "\n".join(comparison_lines)
        state.status = AgentStatus.COMPLETED
        state.stop_reason = StopReason.GOAL_COMPLETED

        return ActionObservation(
            action_id=plan.action_id,
            action_type=plan.action_type,
            success=True,
            raw_output=state.final_answer,
            message="Đã tổng hợp bảng so sánh đa thực thể thành công.",
        )

    def _execute_ask_user(self, plan: ActionPlan, state: AgentGoalState, event_sink: Optional[Any] = None) -> ActionObservation:
        """Đưa Agent vào trạng thái tương tác để thu thập thêm thông tin từ người dùng."""
        payload = plan.ask_user_payload or {}
        state.status = AgentStatus.NEEDS_USER_INPUT
        state.stop_reason = StopReason.USER_INPUT_REQUIRED
        state.clarification_required = True
        state.clarification_question = payload.get("clarification_question", "Bạn có thể làm rõ thêm yêu cầu không?")
        state.clarification_options = payload.get("options", [])
        q_type = payload.get("question_type")
        if q_type:
            try:
                state.clarification_type = QuestionType(q_type)
            except Exception:
                state.clarification_type = QuestionType.MISSING_DATA_ALTERNATIVE if "alternative" in str(q_type).lower() else QuestionType.MISSING_INTENT
        if plan.reason_code == "PROPOSE_ALTERNATIVE":
            state.alternative_proposed = True
        state.final_answer = state.clarification_question

        return ActionObservation(
            action_id=plan.action_id,
            action_type=plan.action_type,
            success=True,
            message=f"Đã gửi yêu cầu làm rõ đến người dùng: {state.clarification_question}",
        )

    def _execute_partial_answer(self, plan: ActionPlan, state: AgentGoalState, event_sink: Optional[Any] = None) -> ActionObservation:
        """Sinh câu trả lời từng phần: nêu rõ phần đã xác minh và phần dữ liệu chưa có."""
        from src.agent_core.schemas import GoalIntent, GoalScope
        from src.agent_core import presentation

        if (
            (state.intent in (GoalIntent.COURSE_OVERVIEW, GoalIntent.COURSE_FULL_DETAILS)
             or state.scope in (GoalScope.SUMMARY, GoalScope.ALL_AVAILABLE))
            and state.entities
            and len(state.requirements) > 1
        ):
            state.final_answer = presentation.format_course_card(
                entity=state.entities[0],
                course_name="",
                requirements=state.requirements,
                catalog=self.entity_catalog,
            )
        else:
            valid_statuses = (EvidenceStatus.SATISFIED, EvidenceStatus.VERIFIED_VALUE, EvidenceStatus.VERIFIED_NONE)
            sat_reqs = [r for r in state.requirements if r.status in valid_statuses]
            unsat_reqs = [r for r in state.requirements if r.status not in valid_statuses]

            lines = ["Thông tin đã xác thực từ tài liệu chính quy:"]
            for r in sat_reqs:
                lines.append(f"- {format_requirement_answer(r, self.entity_catalog)}")

            if unsat_reqs:
                lines.append("\nCác thông tin chưa được công bố trong tài liệu chính thức:")
                for r in unsat_reqs:
                    f_vn = FIELD_NAMES_VN.get(r.field, r.field)
                    lines.append(f"- {r.entity} - {f_vn}: Không có dữ liệu công bố chính thức.")

            state.final_answer = "\n".join(lines)

        state.status = AgentStatus.PARTIAL
        state.stop_reason = StopReason.PARTIAL_EVIDENCE

        return ActionObservation(
            action_id=plan.action_id,
            action_type=plan.action_type,
            success=True,
            raw_output=state.final_answer,
            message="Đã sinh câu trả lời từng phần (Partial Answer).",
        )

    def _execute_abstain(self, plan: ActionPlan, state: AgentGoalState, event_sink: Optional[Any] = None) -> ActionObservation:
        """Từ chối trả lời an toàn khi gặp mã môn không tồn tại hoặc dữ liệu ngoài phạm vi."""
        reason = plan.reason_code
        state.status = AgentStatus.ABSTAINED

        if reason == "UNKNOWN_ENTITY":
            state.stop_reason = StopReason.UNKNOWN_ENTITY
            state.final_answer = (
                f"Mã học phần {', '.join(state.entities)} không có trong danh mục chương trình đào tạo "
                f"hoặc tài liệu chính thức của nhà trường. Vui lòng kiểm tra lại mã môn học."
            )
        elif reason in ("DATA_NOT_AVAILABLE", "REQUIREMENT_EXHAUSTED_ABSTAIN"):
            state.stop_reason = StopReason.DATA_NOT_AVAILABLE
            state.final_answer = (
                "Yêu cầu không thể thực hiện do dữ liệu không được công bố trong các văn bản đào tạo chính thức."
            )
        elif reason == "NO_PROGRESS_ABSTAIN":
            state.stop_reason = StopReason.NO_PROGRESS
            state.final_answer = "Hệ thống dừng tra cứu do không thể tìm thêm bằng chứng hợp lệ."
        else:
            state.stop_reason = StopReason.UNSUPPORTED_CAPABILITY
            state.final_answer = "Hệ thống dừng tra cứu theo chính sách an toàn học vụ."

        return ActionObservation(
            action_id=plan.action_id,
            action_type=plan.action_type,
            success=True,
            raw_output=state.final_answer,
            message=f"Đã từ chối an toàn: {state.final_answer}",
        )

    def _execute_finish(self, plan: ActionPlan, state: AgentGoalState, event_sink: Optional[Any] = None) -> ActionObservation:
        """Hoàn tất mục tiêu và kết xuất câu trả lời đầy đủ kèm nguồn thẩm định."""
        from src.agent_core.schemas import GoalIntent, GoalScope
        from src.agent_core import presentation

        if (
            (state.intent in (GoalIntent.COURSE_OVERVIEW, GoalIntent.COURSE_FULL_DETAILS)
             or state.scope in (GoalScope.SUMMARY, GoalScope.ALL_AVAILABLE))
            and state.entities
            and len(state.requirements) > 1
        ):
            state.final_answer = presentation.format_course_card(
                entity=state.entities[0],
                course_name="",
                requirements=state.requirements,
                catalog=self.entity_catalog,
            )
        else:
            valid_statuses = (EvidenceStatus.SATISFIED, EvidenceStatus.VERIFIED_VALUE, EvidenceStatus.VERIFIED_NONE)
            lines = []
            for r in state.requirements:
                if r.status in valid_statuses:
                    lines.append(format_requirement_answer(r, self.entity_catalog))

            if not lines:
                lines.append("Đã hoàn tất quy trình tra cứu dữ liệu học vụ.")

            state.final_answer = "\n".join(lines)

        state.status = AgentStatus.COMPLETED
        state.stop_reason = StopReason.GOAL_COMPLETED

        return ActionObservation(
            action_id=plan.action_id,
            action_type=plan.action_type,
            success=True,
            raw_output=state.final_answer,
            message="Đã hoàn tất mục tiêu thành công.",
        )


# Global Singleton
_action_executor_instance: Optional[ActionExecutor] = None


def get_action_executor() -> ActionExecutor:
    global _action_executor_instance
    if _action_executor_instance is None:
        _action_executor_instance = ActionExecutor()
    return _action_executor_instance
