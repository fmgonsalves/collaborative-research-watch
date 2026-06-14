---
name: alignment-grill
description: Proactively interview the user about a plan, design, new implementation stage, architecture change, security-sensitive change, or workflow evolution until reaching shared understanding. Use before implementation when alignment is needed, especially when the user asks to start or implement a new implementation stage.
---

# Alignment Grill

Interview the user relentlessly about every aspect of the plan until reaching shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one by one.

## Instructions

- Ask questions one at a time.
- For each question, provide the recommended answer and why it is the default.
- If a question can be answered by exploring the codebase, explore the codebase instead of asking.
- Treat requests to start, begin, implement, or plan a new implementation stage as alignment checkpoints before implementation.
- Keep questions anchored to the current requested decision, implementation stage, or implementation boundary. Do not branch into adjacent roadmap, product, or architecture topics unless they directly affect the next implementation decision.
- Stop grilling once the remaining decisions are low-risk implementation details or the user has explicitly chosen a direction.
- Do not duplicate project-specific rules here; let project skills decide when this interview behavior is required.
