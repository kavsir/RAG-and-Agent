"""
Round P1.2.2 Final Evaluation Certification Runner.
Executes the certification suite across all 5 evaluation layers:
1. Canonical Agent Core Suite (182 cases, official document truth)
2. P1.2.2 Adversarial Truth Suite (65 cases: real unmocked ProgressTracker + ActionExecutor duplicate detection, bounded no-progress)
3. Live Production Evidence Traceability Audit (100% complete provenance, total_audited > 0)
4. Real Event Instrumentation & 13 Acceptance Hard Gates
5. Fresh Subprocess Legacy Regressions (Zero-fallback strict threshold validation)
"""
import sys
import io
from pathlib import Path

# Configure stdout for UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

repo_root = Path(__file__).resolve().parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from eval.agent_core.run_p1_2_1_eval import run_all_evaluations  # noqa: E402


if __name__ == "__main__":
    print("=" * 80)
    print("ROUND P1.2.2 — FINAL EVALUATION CERTIFICATION RUNNER")
    print("=" * 80)
    report = run_all_evaluations()
    if report.get("verdict") == "AGENT_CORE_V1_FULLY_ACCEPTED":
        sys.exit(0)
    else:
        sys.exit(1)
