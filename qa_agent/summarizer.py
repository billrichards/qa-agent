"""Post-run result summary via LLM.

After all testers complete, this module calls the LLM once with the full
findings list and produces a ``SummaryResult`` — a narrative analysis that
clusters related issues, identifies root causes, prioritises fixes, and flags
likely false positives.

The call is non-fatal: if the LLM is unavailable or returns unparseable output,
a warning is logged and ``None`` is returned so the rest of reporting continues.
"""

import json
import logging

from .llm_client import LLMError, LLMProvider, create_llm_client
from .models import RootCauseCluster, SummaryResult, TestSession

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a senior QA lead reviewing automated test results for a web application.

You will receive a JSON object describing a completed QA test session, including:
- Session metadata (pages tested, duration, URLs)
- Findings grouped by severity and category
- The full list of deduplicated findings with descriptions

Your job is to produce a concise, developer-facing summary of the results.

Return ONLY valid JSON matching this exact schema — no markdown, no commentary:

{
  "executive_summary": "<2-3 sentence narrative: overall health, most important themes, what the developer should read first>",
  "priority_recommendations": [
    "<ordered list of specific, actionable fixes — most critical first, plain English>",
    ...
  ],
  "root_cause_clusters": [
    {
      "label": "<short name for the cluster, e.g. 'Missing ARIA labels on icon buttons'>",
      "finding_titles": ["<exact title from input>", ...],
      "root_cause": "<why these are related — shared component, pattern, or missing practice>",
      "suggested_fix": "<concrete engineering action to address the cluster>"
    },
    ...
  ],
  "false_positive_candidates": [
    "<title of a finding that may be a test artifact rather than a real bug, with brief reason>",
    ...
  ]
}

Guidelines:
- executive_summary: be direct. If there are critical issues, lead with them.
- priority_recommendations: 3-6 items max. Focus on highest-impact fixes.
- root_cause_clusters: only create a cluster when 2+ findings genuinely share a root cause.
  Skip this field (empty array) if all findings are independent.
- false_positive_candidates: conservative — only flag something if there is a clear signal
  it is a test artifact (e.g. a navigation finding on a page that requires auth,
  a console error that is a known third-party script, etc.). Empty array is fine.
- Keep language terse and actionable. Avoid padding and hedging."""


def _serialize_session(session: TestSession) -> str:
    """Produce a compact JSON payload for the LLM from the completed session."""
    findings = session.get_deduplicated_findings()
    duration = None
    if session.end_time:
        duration = round((session.end_time - session.start_time).total_seconds(), 1)

    payload = {
        "pages_tested": len(session.pages_tested),
        "duration_seconds": duration,
        "urls": session.config_summary.get("urls", []),
        "mode": session.config_summary.get("mode"),
        "instructions": session.config_summary.get("instructions"),
        "total_findings": session.total_findings,
        "unique_findings": len(findings),
        "findings_by_severity": session.findings_by_severity,
        "findings_by_category": session.findings_by_category,
        "findings": [
            {
                "title": f.title,
                "severity": f.severity.value,
                "category": f.category.value,
                "description": f.description,
                "url": f.url,
                "affected_urls_count": len(f.affected_urls),
                "element_selector": f.element_selector,
                "expected_behavior": f.expected_behavior,
                "actual_behavior": f.actual_behavior,
            }
            for f in findings
        ],
    }
    return json.dumps(payload, default=str)


def _parse_summary(text: str) -> SummaryResult:
    """Parse LLM JSON response into a SummaryResult."""
    # Strip markdown fences if the model wrapped it despite instructions
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    data = json.loads(stripped)

    clusters = [
        RootCauseCluster(
            label=c.get("label", ""),
            finding_titles=c.get("finding_titles", []),
            root_cause=c.get("root_cause", ""),
            suggested_fix=c.get("suggested_fix", ""),
        )
        for c in data.get("root_cause_clusters", [])
    ]

    return SummaryResult(
        executive_summary=data.get("executive_summary", ""),
        priority_recommendations=data.get("priority_recommendations", []),
        root_cause_clusters=clusters,
        false_positive_candidates=data.get("false_positive_candidates", []),
    )


def generate_summary(
    session: TestSession,
    provider: LLMProvider = LLMProvider.ANTHROPIC,
    model: str | None = None,
    api_key: str | None = None,
    timeout: int = 60,
) -> SummaryResult | None:
    """Call the LLM to generate a summary of the completed session results.

    Returns ``None`` on any failure so callers can treat summary generation as optional.
    """
    if not session.pages_tested:
        return None

    findings = session.get_deduplicated_findings()
    if not findings:
        return None

    try:
        client = create_llm_client(provider=provider, model=model, api_key=api_key)
        user_message = (
            "Here is the completed QA test session data:\n\n"
            + _serialize_session(session)
            + "\n\nProvide your summary as JSON."
        )
        response = client.complete(
            system=_SYSTEM_PROMPT,
            user=user_message,
            max_tokens=2048,
            timeout=timeout,
        )
        return _parse_summary(response.text)
    except LLMError as e:
        logger.warning("Result summary LLM call failed (%s): %s", e.status_code, e)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("Failed to parse summary response: %s", e)
    except Exception as e:
        logger.warning("Unexpected error during result summary generation: %s", e)

    return None
