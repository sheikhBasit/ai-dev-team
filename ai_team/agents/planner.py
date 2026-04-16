"""Planner agent — breaks the task into structured WorkItems for the coder."""

from __future__ import annotations

import json
import logging
import re

from ai_team.config import get_llm_for_agent
from ai_team.state import State, WorkItem

logger = logging.getLogger("ai_team.agents.planner")

SYSTEM_PROMPT = """You are a senior engineering planner. Your job is to break a development task into a structured list of concrete work items for a coder agent.

Each work item must be:
- Specific enough that a developer knows exactly what to do
- Scoped to 1-3 files maximum
- Ordered by dependency (items a coder should do first come first)

Respond with ONLY a JSON array of work items. No prose, no explanation, just the JSON.

Format:
[
  {
    "title": "Short imperative title",
    "description": "What to implement and why",
    "files_hint": ["path/to/file.py"],
    "priority": 1
  }
]

Priority: 1=must do first, 2=do after priority 1, 3=optional/polish"""


def planner_agent(state: State) -> dict:
    task = state.get("task", "")
    context = state.get("project_context", "")
    index = state.get("codebase_index", "")
    architecture = state.get("architecture", "")

    user_msg = f"""Task: {task}

Project context (truncated):
{context[:2000] if context else "No context available"}

Codebase index (truncated):
{index[:1500] if index else "No index available"}

Architecture plan:
{architecture[:1000] if architecture else "No architecture plan"}

Break this task into work items. Return JSON only."""

    llm = get_llm_for_agent("planner")
    from langchain_core.messages import HumanMessage, SystemMessage
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_msg)]

    try:
        response = llm.invoke(messages)
        raw = response.content if hasattr(response, "content") else str(response)

        # Extract JSON from response (may have markdown fences)
        json_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if json_match:
            items_raw = json.loads(json_match.group())
            work_items: list[WorkItem] = [
                WorkItem(
                    title=item.get("title", "Untitled"),
                    description=item.get("description", ""),
                    files_hint=item.get("files_hint", []),
                    priority=int(item.get("priority", 2)),
                )
                for item in items_raw
                if isinstance(item, dict)
            ]
        else:
            logger.warning("Planner returned no JSON, using single work item")
            work_items = [WorkItem(title=task, description=task, files_hint=[], priority=1)]
    except Exception as e:
        logger.warning("Planner failed (%s), falling back to single work item", e)
        work_items = [WorkItem(title=task, description=task, files_hint=[], priority=1)]

    logger.info("Planner produced %d work items", len(work_items))
    summary = "\n".join(f"  {i+1}. [{wi['priority']}] {wi['title']}" for i, wi in enumerate(work_items))
    return {
        "work_items": work_items,
        "messages": [f"[Planner] Broke task into {len(work_items)} work items:\n{summary}"],
    }
