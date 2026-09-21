---
name: llm-architectural-prompt-enforcement
description: Enforce architectural and structural requirements via LLM prompt modifications instead of post-hoc validation. Use when LLM-generated output must always contain specific structural elements (state machines, required components, naming contracts, non-functional constraints) and validation/retry loops alone are too costly.
---

# LLM Architectural Prompt Enforcement

Techniques for modifying LLM agent prompts in multi-agent pipelines to enforce architectural requirements and constraints.

## When to Use

Use this skill when you need to ensure LLM-generated output adheres to specific architectural, structural, or non-functional requirements that cannot be reliably enforced through post-generation validation alone. This is particularly valuable in agentic systems where:
- Certain structural elements must always be present (e.g., specific state machines, required components)
- Non-functional requirements must be met (e.g., performance constraints, security properties)
- Interface contracts must be preserved (e.g., specific variable naming, API usage patterns)
- Regulatory or compliance requirements must be satisfied (e.g., accessibility, data handling)

## Why This Matters

In LLM-powered agentic systems, relying solely on post-generation validation or retry loops can be inefficient and frustrating. By encoding architectural requirements directly into agent prompts, you:
- Reduce wasted generation attempts that violate core constraints
- Provide clearer guidance to the LLM about what is truly required
- Enable more predictable and reliable system behavior
- Shift left defect prevention rather than relying on detection and repair

## How to Apply

### 1. Identify the Responsible Agent

Determine which agent/node in your pipeline is responsible for generating the output that needs to satisfy the architectural requirement.

*Example*: In a game generation pipeline with research → design → spec → codegen → validate stages, if you need to enforce a specific game state machine structure, the `spec` node is typically responsible since it produces the implementation spec that guides code generation.

### 2. Formulate Clear, Actionable Requirements

Convert your architectural requirement into precise, unambiguous language that an LLM can understand and follow.

**Do**: Use positive, prescriptive language with concrete examples
**Don't**: Use negative language or vague descriptions

*Weak*: "Don't forget to include the Tutorial state"
*Strong*: "The state_machine MUST include 'Tutorial' as the third element after 'Preload' and before 'Play'"

### 3. Embed Requirements in the Prompt

Add your requirement to the agent's prompt using these patterns:

#### Requirement Statement Pattern

```
[REQUIREMENT]: [Clear statement of what must be true]
[Rationale]: [Brief explanation of why this matters]
[Consequence]: [What happens if this is not followed]
```

*Example*:
```
[REQUIREMENT]: The state_machine array must contain exactly these six elements in order: ['Boot', 'Preload', 'Tutorial', 'Play', 'GameOver', 'Win']
[Rationale]: This ensures all games have proper initialization, loading, onboarding, core gameplay, and termination sequences for optimal player retention
[Consequence]: Games missing any of these states will fail validation and require rework
```

#### Concrete Example Pattern

Provide a specific example of what correct output looks like:
```
Correct example: ["Boot", "Preload", "Tutorial", "Play", "GameOver", "Win"]
Incorrect example: ["Boot", "Preload", "Play"]  # Missing Tutorial, GameOver, Win
```

#### Constraint Pattern

For formal constraints, use mathematical or logical notation:
```
Constraint: len(state_machine) == 6
Constraint: state_machine[0] == 'Boot' && state_machine[1] == 'Preload' && state_machine[2] == 'Tutorial'
```

### 4. Validate the Change

After modifying prompts, verify that:
- The LLM understands and follows the requirement
- The change doesn't inadvertently constrain beneficial variability
- Validation checks still work correctly with the new expectation

**Validation Techniques**:
- Unit test the prompt modification in isolation
- Run a small batch of generations and manually inspect output
- Check that existing validation logic still passes with compliant output
- Verify that non-compliant output is correctly rejected

### 5. Monitor and Iterate

Track how often the requirement triggers retries or failures, and adjust your prompt wording as needed based on observed LLM behavior.

## Best Practices

### Do:
- Make requirements *positive* statements about what should be present
- Provide concrete examples of correct and incorrect output
- Tie requirements to tangible outcomes (e.g., "This ensures proper player onboarding")
- Keep requirement statements concise but complete
- Review and refine results based on actual generation results
- For long prompts, consider moving them to external files (e.g., .txt) and loading them at runtime. This avoids issues with curly braces being interpreted as format placeholders by libraries like LangChain, and makes prompts easier to edit and version control. *Example*: In gd-gpt, the spec node prompt was moved to `pipeline/nodes/spec_prompt.txt` and loaded via `with open(...) as f: PROMPT = f.read()`.

### Don't:
- Use double negatives or complex logical constructions
- Rely on the LLM to infer implicit requirements
- Make requirements so strict that they eliminate valuable variability
- Forget to update associated validation logic when requirements change
- Assume one attempt at requirement wording will be perfect

## Pitfalls and How to Avoid Them

### Pitfall: Over-constraining

*Problem*: Making requirements so specific that they prevent the LLM from adapting to legitimate variations in the input.
*Solution*: Focus on invariant structural elements rather than specific values. For example, require that a Tutorial state exists rather than specifying exactly what it should contain.

### Pitfall: Ambiguous Language

*Problem*: Using terms that the LLM might interpret differently than intended.
*Solution*: Replace vague terms with concrete specifications. Instead of "meaningful tutorial", specify what makes a tutorial meaningful (e.g., "must contain interactive elements that teach core mechanics").

### Pitfall: Forgetting Context

*Problem*: Requirements that make sense in isolation conflict with other system requirements.
*Solution*: Always consider how your requirement interacts with other constraints in the system. Test combinations of requirements together.

### Pitfall: Neglecting Validation Updates

*Problem*: Changing prompt requirements without updating corresponding validation checks.
*Solution*: Treat prompt requirements and validation checks as a coupled pair - when one changes, the other likely needs to change too.

### Pitfall: Ignoring Failure Modes

*Problem*: Not tracking how the LLM fails to meet the requirement, missing opportunities to improve the prompt.
*Solution*: Log and analyze instances where the requirement is not met to identify patterns in LLM misunderstandings.

### Pitfall: Ignoring Infrastructure and Process Factors

*Problem*: Focusing solely on LLM prompt modifications while neglecting infrastructure setup, dependency management, and process workflows that are critical for successful architectural enforcement.
*Solution*: Remember that prompt modifications are just one part of a larger system. Ensure that virtual environments are properly configured, dependencies are available, and teams follow established processes for running and validating pipeline changes. Document infrastructure requirements and setup procedures alongside prompt modifications.

## Related Techniques

- **Structured Output Templates**: Combine with JSON schema or Pydantic models to enforce both structural and data type constraints
- **Chain-of-Thought Prompting**: Have the LLM explain how its output satisfies each requirement before providing the final answer
- **Few-Shot Examples**: Provide multiple correct examples showing variations that still meet the architectural requirements
- **Self-Check Prompts**: Add a prompt instruction for the LLM to verify its own output against the requirements before submitting

## When Not to Use

Avoid this technique when:
- The requirement is better enforced through post-generation parsing and validation
- The requirement is truly exploratory and benefits from LLM creativity
- Validating the requirement is extremely cheap and fast compared to generation cost
- The requirement changes frequently, making prompt updates impractical
- You lack the ability to test prompt changes effectively

In these cases, invest in improving your validation logic or retry mechanisms instead.

### Pitfall: Unterminated f-string due to missing quote after expression

*Problem*: When constructing f-strings that contain expressions followed immediately by brackets or parentheses (e.g., `f\"...{expr}]\"`), forgetting to close the f-string with a quote before the bracket results in a syntax error: unterminated f-string literal.

*Solution*: Always ensure the f-string is terminated with a closing quote before any following brackets, parentheses, or other punctuation that is not part of the f-string. For example, use `f\"...{expr}\"]` rather than `f\"...{expr}]\"`.

### Pitfall: Incorrect escaping of special characters in prompt strings

*Problem*: When including special characters like curly braces `{}` or backslashes `\` in prompt strings that are interpreted as format placeholders or escape sequences by the LLM or intermediate processing, the LLM may receive malformed instructions, leading to parsing errors or unexpected behavior. For example, a JSON example like `{\"gravity\": \"1200\", \"jump_velocity\": \"-400\"}` must be escaped as `{{\"gravity\": \"1200\", \"jump_velocity\": \"-400\"}}` to prevent curly brace interpretation. Similarly, backslashes in strings like `\\n` must be correctly escaped to avoid being treated as single escape characters.

*Solution*: Always escape special characters according to the context in which the prompt string is used. In Python strings, double the backslashes (`\\\\n` becomes `\\n` after string literal processing) and double curly braces (`{{` and `}}`) to represent literal braces. Validate by printing the final prompt string to ensure it appears as intended before sending to the LLM.

## References

- `references/gd-gpt-tutorial-enforcement-example.md` — Example of enforcing mandatory tutorial phase in state machine spec
- `references/gd-gpt-codegen-anti-patterns.md` — Anti-pattern documentation in codegen prompt to prevent recurring review failures
- `references/rate-limit-backoff.md` — Category-aware exponential backoff for LLM API rate limits (TRANSIENT errors get 30s base vs 2s for others)
- `references/llm-provider-token-limits.md` — LLM provider token limits and silent fallback detection (max_tokens exceeding model limit triggers silent fallback to free tier)