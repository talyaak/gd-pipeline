---
name: validating-playable-ad-timing
description: Validate playable-ad/game timing metrics (time-to-first-interaction, engagement duration, completion rate) against implementation-spec targets. Use when wiring or reviewing the playtest/vision validation gates of a game-generation pipeline.
---
# Validating Playable Ad Timing Requirements

## When to use
When validating generated HTML5 playable ads against timing requirements such as time-to-first-interaction, engagement duration, and completion rate as specified in the game's implementation spec.

## Why this matters
Playable ad networks and UA teams have strict benchmarks for timing metrics that directly impact ad performance and user retention. Validating these metrics ensures generated ads meet commercial quality standards.

## How to implement

### 1. Extract timing targets from spec
Retrieve timing targets from the implementation spec artifact with sensible defaults:
- `target_session_seconds`: Total session length (tutorial + core loop), default 30s, valid range 15-40s
- `time_to_first_interaction_target_seconds`: Time to first meaningful interaction, default 4s, must be ≤4s for retention
- Calculate millisecond equivalents for validation

### 2. Define validation thresholds
Set configurable thresholds for validation:
- Time-to-first-interaction tolerance: +1000ms over target (allows 1s buffer)
- Minimum completion rate: 0.5 (50% of target session must be completed)
- Minimum engagement fraction: 0.3 (30% of target session in active play state)

### 3. Implement timing validation function
Create a function that validates execution report metrics against spec targets:

```python
def _check_timing_metrics(report, spec_artifact: dict) -> list[str]:
    """Validate execution timing metrics against spec targets.
    
    Returns list of violation messages (empty = all metrics pass).
    """
    violations = []
    
    # Extract timing targets from spec (with defaults)
    target_session_seconds = spec_artifact.get("target_session_seconds", 30)
    time_to_first_interaction_target_seconds = spec_artifact.get("time_to_first_interaction_target_seconds", 4)
    
    target_session_ms = target_session_seconds * 1000
    tti_target_ms = time_to_first_interaction_target_seconds * 1000
    
    # 1. Time-to-first-interaction check
    if report.time_to_first_interaction_ms is not None:
        tti_ms = report.time_to_first_interaction_ms
        max_allowed_tti = tti_target_ms + TTFI_TOLERANCE_MS
        if tti_ms > max_allowed_tti:
            violations.append(
                f"Time-to-first-interaction ({tti_ms}ms) exceeds target "
                f"({tti_target_ms}ms) + tolerance ({TTFI_TOLERANCE_MS}ms) = {max_allowed_tti}ms"
            )
    else:
        violations.append("Time-to-first-interaction not measured")
    
    # 2. Completion rate check
    if report.completion_rate is not None:
        if report.completion_rate < MIN_COMPLETION_RATE:
            violations.append(
                f"Completion rate ({report.completion_rate:.2f}) below minimum ({MIN_COMPLETION_RATE})"
            )
    else:
        violations.append("Completion rate not measured")
    
    # 3. Engagement duration check
    if report.engagement_duration_ms is not None:
        min_engagement_ms = target_session_ms * MIN_ENGAGEMENT_FRACTION
        if report.engagement_duration_ms < min_engagement_ms:
            violations.append(
                f"Engagement duration ({report.engagement_duration_ms}ms) below minimum "
                f"({MIN_ENGAGEMENT_FRACTION * 100:.0f}% of target session = {min_engagement_ms}ms)"
            )
    else:
        violations.append("Engagement duration not measured")
    
    return violations
```

### 4. Integrate into validation pipeline
In the main validation function:
- Only run timing validation if basic runtime checks pass (loaded, no console errors, canvas rendered, input response detected)
- Collect timing violations and add them to the overall error list
- Fail validation if any timing violations exist

### 5. Handle missing spec data gracefully
Use `.get()` with default values when accessing spec artifact fields to prevent crashes when spec data is incomplete or malformed.

## Key implementation details
- Time-to-first-interaction is measured from page load to first meaningful user interaction (pointerdown/keyup)
- Engagement duration tracks time spent in active play states (detected via game state inspection)
- Completion rate calculates fraction of target session completed based on engagement time or win state detection
- All validations use spec-defined targets with fallback defaults for robustness
- Validation only runs when basic runtime checks pass to avoid cascading failures

## Verification approach
1. Unit test the timing validation function with various report/spec combinations
2. Verify syntax of modified validation code
3. Confirm integration with existing validation pipeline doesn't break basic checks
4. Test edge cases: missing metrics, boundary values, invalid spec data

## Common pitfalls to avoid
- Don't validate timing metrics when basic runtime checks fail (leads to misleading errors)
- Don't assume spec fields always exist - use proper default handling
- Don't set thresholds too strictly - account for measurement variability
- Don't forget to convert seconds to milliseconds consistently
- Don't validate engagement/completion if metrics weren't measured (None values)

## References
- gd-pipeline: playtest/vision nodes in `pipeline/graph.py`, static checks in `pipeline/validate.py`
- Telemetry/report schema: `pipeline/schemas.py`
- Original gd-gpt implementation notes: `references/gd-gpt-timing-validation-implementation.md`