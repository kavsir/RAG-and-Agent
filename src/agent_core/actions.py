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
from typing import Optional

from src.agent_core.schemas import (
    ActionPlan,
    ActionObservation,
    ActionType,
    AgentGoalState,
    AgentStatus,
    StopReason,
    EvidenceStatus,
    QuestionType,
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

    def execute(self, plan: ActionPlan, state: AgentGoalState) -> ActionObservation:
        """Thực thi một kế hoạch hành động đã được lập."""
        a_type = plan.action_type

        if a_type == ActionType.CATALOG_LOOKUP:
            return self._execute_catalog_lookup(plan, state)
        elif a_type == ActionType.RETRIEVE_EXACT:
            return self._execute_exact_retrieval(plan, state)
        elif a_type == ActionType.RETRIEVE_EXPANDED:
            return self._execute_expanded_retrieval(plan, state)
        elif a_type == ActionType.COMPARE_EVIDENCE:
            return self._execute_compare_evidence(plan, state)
        elif a_type == ActionType.ASK_USER:
            return self._execute_ask_user(plan, state)
        elif a_type == ActionType.PARTIAL_ANSWER:
            return self._execute_partial_answer(plan, state)
        elif a_type == ActionType.ABSTAIN:
            return self._execute_abstain(plan, state)
        elif a_type == ActionType.FINISH:
            return self._execute_finish(plan, state)
        else:
            return ActionObservation(
                action_id=plan.action_id,
                action_type=plan.action_type,
                success=False,
                message=f"Hành động chưa được hỗ trợ: {a_type}",
            )

    def _execute_catalog_lookup(self, plan: ActionPlan, state: AgentGoalState) -> ActionObservation:
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

        status, item = self.verifier.verify_requirement(target_req, [])
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

    def _execute_exact_retrieval(self, plan: ActionPlan, state: AgentGoalState) -> ActionObservation:
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
                    res = retriever.collection.get(where=where_filter, limit=10)
                    if res and res.get("documents"):
                        for cid, meta, text in zip(res["ids"], res["metadatas"], res["documents"]):
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
                elif not where_filter and col_name == "regulation" and retriever.collection:
                    res = retriever.collection.get(limit=10)
                    if res and res.get("documents"):
                        for cid, meta, text in zip(res["ids"], res["metadatas"], res["documents"]):
                            matching_docs.append({
                                "id": cid,
                                "chunk_id": cid,
                                "text": text,
                                "content": text,
                                "metadata": meta or {},
                                "document_type": "regulation",
                                "source_file": (meta or {}).get("source_file", ""),
                                "section": (meta or {}).get("section", ""),
                            })

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

        status, item = self.verifier.verify_requirement(target_req, matching_docs)
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
                message=f"Đã thu thập bằng chứng cho {target_req.requirement_key}: {item.content}",
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

    def _execute_expanded_retrieval(self, plan: ActionPlan, state: AgentGoalState) -> ActionObservation:
        """Truy xuất mở rộng qua RAG (tên môn, alias) khi exact retrieval không tìm thấy, bảo vệ không chéo thực thể."""
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

        for col_name in collections_to_search:
            try:
                retriever = get_collection_retriever(col_name)
                # BM25 search mở rộng
                docs = retriever.bm25_search(query_str, top_k=5)
                for d in docs:
                    d_code = d.get("metadata", {}).get("course_code")
                    if d_code and target_req.entity and d_code != target_req.entity:
                        continue
                    d["content"] = d.get("text", "")
                    matching_docs.append(d)
            except Exception:
                pass

        status, item = self.verifier.verify_requirement(target_req, matching_docs)
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

    def _execute_compare_evidence(self, plan: ActionPlan, state: AgentGoalState) -> ActionObservation:
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

    def _execute_ask_user(self, plan: ActionPlan, state: AgentGoalState) -> ActionObservation:
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

    def _execute_partial_answer(self, plan: ActionPlan, state: AgentGoalState) -> ActionObservation:
        """Sinh câu trả lời từng phần: nêu rõ phần đã xác minh và phần dữ liệu chưa có."""
        valid_statuses = (EvidenceStatus.SATISFIED, EvidenceStatus.VERIFIED_VALUE, EvidenceStatus.VERIFIED_NONE)
        sat_reqs = [r for r in state.requirements if r.status in valid_statuses]
        unsat_reqs = [r for r in state.requirements if r.status not in valid_statuses]

        lines = ["Thông tin đã xác thực từ tài liệu chính quy:"]
        for r in sat_reqs:
            f_vn = FIELD_NAMES_VN.get(r.field, r.field)
            lines.append(f"- **{r.entity} ({f_vn})**: {r.extracted_value}")

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

    def _execute_abstain(self, plan: ActionPlan, state: AgentGoalState) -> ActionObservation:
        """Từ chối trả lời an toàn khi gặp mã môn không tồn tại hoặc dữ liệu ngoài phạm vi."""
        reason = plan.reason_code
        state.status = AgentStatus.ABSTAINED

        if reason == "UNKNOWN_ENTITY":
            state.stop_reason = StopReason.UNKNOWN_ENTITY
            state.final_answer = (
                f"Mã học phần {', '.join(state.entities)} không có trong danh mục chương trình đào tạo "
                f"hoặc tài liệu chính thức của nhà trường. Vui lòng kiểm tra lại mã môn học."
            )
        elif reason == "DATA_NOT_AVAILABLE":
            state.stop_reason = StopReason.DATA_NOT_AVAILABLE
            state.final_answer = (
                "Yêu cầu không thể thực hiện do dữ liệu không được công bố trong các văn bản đào tạo chính thức."
            )
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

    def _execute_finish(self, plan: ActionPlan, state: AgentGoalState) -> ActionObservation:
        """Hoàn tất mục tiêu và kết xuất câu trả lời đầy đủ kèm nguồn thẩm định."""
        valid_statuses = (EvidenceStatus.SATISFIED, EvidenceStatus.VERIFIED_VALUE, EvidenceStatus.VERIFIED_NONE)
        lines = []
        for r in state.requirements:
            if r.status in valid_statuses:
                f_vn = FIELD_NAMES_VN.get(r.field, r.field)
                lines.append(f"- **{r.entity} ({f_vn})**: {r.extracted_value}")

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
