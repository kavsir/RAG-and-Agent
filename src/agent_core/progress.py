"""
Progress Tracker & Anti-Loop Detection for Goal-Driven Agent Core V1.
Implements the 3 independent anti-loop mechanisms:
1. MAX ITERATIONS (max 2 attempts per requirement)
2. NO-PROGRESS DETECTION (ProgressSnapshot comparison)
3. DUPLICATE ACTION PREVENTION (ActionFingerprint registry)
"""
from typing import Tuple
from src.agent_core.schemas import (
    AgentGoalState,
    ProgressSnapshot,
    EvidenceStatus,
)


class ProgressTracker:
    """Bộ theo dõi tiến trình và phòng vệ chống lặp vô hạn."""

    MAX_ATTEMPTS_PER_REQUIREMENT = 2

    def create_snapshot(self, state: AgentGoalState, last_fingerprint: str = None) -> ProgressSnapshot:
        """Tạo ảnh chụp trạng thái tiến độ hiện tại."""
        satisfied = [
            r.requirement_key for r in state.requirements
            if r.status in (EvidenceStatus.SATISFIED, EvidenceStatus.VERIFIED_VALUE, EvidenceStatus.VERIFIED_NONE)
        ]
        missing = [
            r.requirement_key for r in state.requirements
            if r.status in (EvidenceStatus.PENDING, EvidenceStatus.MISSING, EvidenceStatus.INSUFFICIENT)
        ]
        conflicting = [r.requirement_key for r in state.requirements if r.status == EvidenceStatus.CONFLICTING]

        return ProgressSnapshot(
            iteration=state.iteration,
            satisfied_requirements=satisfied,
            missing_requirements=missing,
            evidence_count=len(state.evidence),
            conflicting_requirements=conflicting,
            last_action_fingerprint=last_fingerprint,
        )

    def evaluate_progress(self, state: AgentGoalState, current_snapshot: ProgressSnapshot) -> Tuple[bool, str]:
        """
        So sánh tiến độ trước và sau một hành động.
        Trả về (has_progress, reason).
        """
        if not state.progress_history:
            state.progress_history.append(current_snapshot)
            return True, "INITIAL_PROGRESS"

        prev = state.progress_history[-1]

        # Kiểm tra các điều kiện tiến triển:
        new_evidence = current_snapshot.evidence_count > prev.evidence_count
        new_satisfied = len(current_snapshot.satisfied_requirements) > len(prev.satisfied_requirements)
        resolved_conflict = len(current_snapshot.conflicting_requirements) < len(prev.conflicting_requirements)
        fewer_missing = len(current_snapshot.missing_requirements) < len(prev.missing_requirements)

        has_progress = new_evidence or new_satisfied or resolved_conflict or fewer_missing

        if not has_progress:
            state.no_progress_count += 1
            reason = (
                f"NO_PROGRESS: evidence_count={current_snapshot.evidence_count} (was {prev.evidence_count}), "
                f"satisfied={len(current_snapshot.satisfied_requirements)} (was {len(prev.satisfied_requirements)})"
            )
        else:
            state.no_progress_count = 0
            reason = "PROGRESS_DETECTED"

        state.progress_history.append(current_snapshot)
        return has_progress, reason

    def is_duplicate_action(self, state: AgentGoalState, fingerprint: str) -> bool:
        """Kiểm tra xem hành động với fingerprint này đã từng chạy trước đó chưa."""
        return fingerprint in state.attempted_actions

    def is_requirement_exhausted(self, state: AgentGoalState, req_key: str) -> bool:
        """Kiểm tra xem yêu cầu bằng chứng này đã vượt quá số lần thử tối đa (2 lần) chưa."""
        for r in state.requirements:
            if r.requirement_key == req_key:
                return r.attempt_count >= self.MAX_ATTEMPTS_PER_REQUIREMENT
        return False


# Singleton Instance
_progress_tracker_instance: ProgressTracker = None


def get_progress_tracker() -> ProgressTracker:
    global _progress_tracker_instance
    if _progress_tracker_instance is None:
        _progress_tracker_instance = ProgressTracker()
    return _progress_tracker_instance
