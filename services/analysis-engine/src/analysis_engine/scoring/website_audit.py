"""Website AI-friendliness scoring — wraps geo_optimizer.audit()."""

from __future__ import annotations

from geo_optimizer import audit as run_geo_audit

from analysis_engine.models import ScoreBreakdown


def score_website_audit(url: str) -> ScoreBreakdown:
    audit_result = run_geo_audit(url)

    if audit_result.error:
        return ScoreBreakdown(
            dimension="website_audit",
            score=None,
            data_complete=False,
            detail={"reason": audit_result.error},
        )

    return ScoreBreakdown(
        dimension="website_audit",
        score=float(audit_result.score),
        data_complete=True,
        detail={
            "band": audit_result.band,
            "score_breakdown": dict(audit_result.score_breakdown),
            "recommendations": list(audit_result.recommendations),
        },
    )
