#!/usr/bin/env python3
"""
expand-tasks script.py — Deterministic operations for TaskMaster task expansion.
AI handles judgment (research questions, quality review); script handles mechanics.

Commands:
  read-tasks [--file PATH]           Read tasks.json and return task list
  gen-prompt --task-id ID [--file PATH] [--prd PATH]  Generate research prompt for a task
  write-research --task-id ID --research FILE [--file PATH]  Write research back to task
  status [--file PATH]               Show expansion status (which tasks have research)
"""

import argparse
import json
import sys
import os
from pathlib import Path


def find_tasks_file(explicit_path=None):
    """Find tasks.json in the current project."""
    if explicit_path:
        p = Path(explicit_path)
        if p.exists():
            return p
        print(json.dumps({"error": f"File not found: {explicit_path}"}))
        sys.exit(1)

    # Search common locations
    candidates = [
        Path(".taskmaster/tasks/tasks.json"),
        Path("tasks/tasks.json"),
    ]
    for c in candidates:
        if c.exists():
            return c

    print(json.dumps({"error": "No tasks.json found. Run from project root or use --file."}))
    sys.exit(1)


def load_tasks(tasks_file):
    """Load and normalize tasks from tasks.json."""
    with open(tasks_file) as f:
        data = json.load(f)

    # Handle nested structure: {master: {tasks: [...]}} or {tasks: [...]} or [...]
    if isinstance(data, list):
        return data, data
    if isinstance(data, dict):
        if "master" in data and isinstance(data["master"], dict):
            return data["master"].get("tasks", []), data
        if "tasks" in data:
            return data["tasks"], data
    return [], data


def save_tasks(tasks_file, full_data, tasks):
    """Save tasks back to tasks.json preserving structure."""
    if isinstance(full_data, list):
        full_data = tasks
    elif isinstance(full_data, dict):
        if "master" in full_data and isinstance(full_data["master"], dict):
            full_data["master"]["tasks"] = tasks
        elif "tasks" in full_data:
            full_data["tasks"] = tasks

    with open(tasks_file, "w") as f:
        json.dump(full_data, f, indent=2)


def cmd_read_tasks(args):
    """Read and list all tasks."""
    tasks_file = find_tasks_file(args.file)
    tasks, _ = load_tasks(tasks_file)

    result = []
    for t in tasks:
        has_research = bool(t.get("research_notes") or t.get("_research_expanded"))
        deps = t.get("dependencies", [])
        result.append({
            "id": t.get("id"),
            "title": t.get("title", ""),
            "status": t.get("status", "pending"),
            "dependencies": [str(d) for d in deps],
            "has_research": has_research,
            "description_length": len(t.get("description", "")),
            "subtask_count": len(t.get("subtasks", [])),
        })

    print(json.dumps({
        "tasks_file": str(tasks_file),
        "total": len(result),
        "expanded": sum(1 for r in result if r["has_research"]),
        "pending_expansion": sum(1 for r in result if not r["has_research"]),
        "tasks": result,
    }, indent=2))


def cmd_gen_prompt(args):
    """Generate a research prompt for a specific task."""
    tasks_file = find_tasks_file(args.file)
    tasks, _ = load_tasks(tasks_file)

    task = None
    for t in tasks:
        if str(t.get("id")) == str(args.task_id):
            task = t
            break

    if not task:
        print(json.dumps({"error": f"Task {args.task_id} not found"}))
        sys.exit(1)

    # Load PRD context if available
    prd_context = ""
    prd_path = args.prd or ".taskmaster/docs/prd.md"
    if os.path.exists(prd_path):
        with open(prd_path) as f:
            prd_text = f.read()
        # Extract relevant section (first 200 lines max)
        lines = prd_text.split("\n")[:200]
        prd_context = f"\n\nPRD CONTEXT (first 200 lines):\n{''.join(chr(10).join(lines))}"

    # Build dependency context
    dep_context = ""
    deps = task.get("dependencies", [])
    if deps:
        dep_tasks = [t2 for t2 in tasks if str(t2.get("id")) in [str(d) for d in deps]]
        if dep_tasks:
            dep_lines = [f"- Task {t2['id']}: {t2.get('title', '')}" for t2 in dep_tasks]
            dep_context = f"\n\nDEPENDENCY TASKS (must complete before this):\n" + "\n".join(dep_lines)

    title = task.get("title", "")
    description = task.get("description", "")
    details = task.get("details", "")
    subtasks = task.get("subtasks", [])

    subtask_text = ""
    if subtasks:
        sub_lines = [f"- {s.get('title', s.get('id', ''))}" for s in subtasks]
        subtask_text = f"\n\nSUBTASKS:\n" + "\n".join(sub_lines)

    # Generate 5 research questions based on task content
    research_questions = [
        f"What are the current best practices for implementing {title} in 2026?",
        f"What are common pitfalls and gotchas when building {title}?",
        f"What libraries, frameworks, or tools are recommended for {title}?",
        f"What architectural patterns work best for {title}?",
        f"Are there open-source examples or references for {title}?",
    ]

    prompt = f"""You are expanding a TaskMaster task with research. DO NOT write any code or create files. ONLY research and return a structured summary.

**Task {task.get('id')}: {title}**

DESCRIPTION:
{description}

{f"DETAILS:{chr(10)}{details}" if details else ""}
{subtask_text}
{dep_context}

Research these questions using Perplexity MCP tools (perplexity_batch preferred, perplexity_search as fallback):

{chr(10).join(f"{i+1}. {q}" for i, q in enumerate(research_questions))}

Return a structured summary with:
- Key findings per question (2-3 sentences each)
- Recommended implementation approach
- Specific libraries/tools with versions
- Code patterns to follow (max 15 lines each)
- Pitfalls and warnings
- Security considerations
- Any conflicting advice between sources

FORMAT your response as:
---
## Research: Task {task.get('id')} - {title}
**Date**: YYYY-MM-DD

### Key Findings
[Numbered findings matching the research questions]

### Recommended Approach
- **Pattern**: [name]
- **Libraries**: [with versions]
- **Why**: [trade-off reasoning]

### Key Code Pattern
```[language]
[Most relevant snippet, max 15 lines]
```

### Pitfalls
- [Critical items to avoid]

### Security Notes
- [Any security considerations]

### Implementation Guidance
[2-4 sentences of specific implementation advice for this task]
---"""

    print(json.dumps({
        "task_id": task.get("id"),
        "title": title,
        "prompt": prompt,
        "research_questions": research_questions,
    }, indent=2))


def cmd_write_research(args):
    """Write research results back into the task."""
    tasks_file = find_tasks_file(args.file)
    tasks, full_data = load_tasks(tasks_file)

    # Read research content
    if args.research == "-":
        research_content = sys.stdin.read()
    else:
        with open(args.research) as f:
            research_content = f.read()

    # Find and update the task
    updated = False
    for t in tasks:
        if str(t.get("id")) == str(args.task_id):
            # Store research in the task
            t["research_notes"] = research_content
            t["_research_expanded"] = True

            # Append research to details if it exists
            existing_details = t.get("details", "")
            if existing_details:
                t["details"] = existing_details + "\n\n---\n\n" + research_content
            else:
                t["details"] = research_content

            updated = True
            break

    if not updated:
        print(json.dumps({"error": f"Task {args.task_id} not found"}))
        sys.exit(1)

    save_tasks(tasks_file, full_data, tasks)
    print(json.dumps({
        "success": True,
        "task_id": args.task_id,
        "research_length": len(research_content),
        "tasks_file": str(tasks_file),
    }))


def cmd_status(args):
    """Show expansion status."""
    tasks_file = find_tasks_file(args.file)
    tasks, _ = load_tasks(tasks_file)

    expanded = []
    pending = []
    for t in tasks:
        info = {"id": t.get("id"), "title": t.get("title", "")}
        if t.get("research_notes") or t.get("_research_expanded"):
            expanded.append(info)
        else:
            pending.append(info)

    print(json.dumps({
        "total": len(tasks),
        "expanded": len(expanded),
        "pending": len(pending),
        "expanded_tasks": expanded,
        "pending_tasks": pending,
        "all_expanded": len(pending) == 0,
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description="TaskMaster task expansion with research")
    subparsers = parser.add_subparsers(dest="command")

    # read-tasks
    p_read = subparsers.add_parser("read-tasks")
    p_read.add_argument("--file", help="Path to tasks.json")

    # gen-prompt
    p_gen = subparsers.add_parser("gen-prompt")
    p_gen.add_argument("--task-id", required=True, help="Task ID to generate prompt for")
    p_gen.add_argument("--file", help="Path to tasks.json")
    p_gen.add_argument("--prd", help="Path to PRD file")

    # write-research
    p_write = subparsers.add_parser("write-research")
    p_write.add_argument("--task-id", required=True, help="Task ID to write research to")
    p_write.add_argument("--research", required=True, help="Path to research file (or - for stdin)")
    p_write.add_argument("--file", help="Path to tasks.json")

    # status
    p_status = subparsers.add_parser("status")
    p_status.add_argument("--file", help="Path to tasks.json")

    args = parser.parse_args()

    if args.command == "read-tasks":
        cmd_read_tasks(args)
    elif args.command == "gen-prompt":
        cmd_gen_prompt(args)
    elif args.command == "write-research":
        cmd_write_research(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
