#!/usr/bin/env python3
"""
Task execution state manager for crash recovery.
"""

import json
from pathlib import Path
from datetime import datetime, timezone

class ExecutionState:
    def __init__(self):
        self.state_file = Path(".taskmaster/state/execution-state.json")
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.load_state()

    def load_state(self):
        """Load current execution state."""
        if self.state_file.exists():
            with open(self.state_file, 'r') as f:
                self.state = json.load(f)
        else:
            self.state = {
                "mode": None,
                "current_task": None,
                "current_subtask": None,
                "tasks_completed": [],
                "last_update": None
            }

    def save_state(self):
        """Persist current state to disk."""
        self.state["last_update"] = datetime.now(timezone.utc).isoformat()
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)

    def set_mode(self, mode):
        """Set execution mode (sequential, parallel, etc.)."""
        self.state["mode"] = mode
        self.save_state()

    def start_task(self, task_id):
        """Mark task as started."""
        self.state["current_task"] = task_id
        self.state["current_subtask"] = None
        self.save_state()

    def start_subtask(self, task_id, subtask_id):
        """Mark subtask as started."""
        self.state["current_task"] = task_id
        self.state["current_subtask"] = subtask_id
        self.save_state()

    def complete_task(self, task_id):
        """Mark task as completed."""
        if task_id not in self.state["tasks_completed"]:
            self.state["tasks_completed"].append(task_id)
        self.state["current_task"] = None
        self.state["current_subtask"] = None
        self.save_state()

    def has_incomplete_work(self):
        """Check if there's incomplete work from previous session."""
        return self.state["current_task"] is not None

    def get_resume_point(self):
        """Get information about where to resume."""
        if not self.has_incomplete_work():
            return None

        return {
            "mode": self.state["mode"],
            "task": self.state["current_task"],
            "subtask": self.state["current_subtask"],
            "last_update": self.state["last_update"],
            "completed_tasks": self.state["tasks_completed"]
        }

if __name__ == "__main__":
    state = ExecutionState()
    if state.has_incomplete_work():
        resume = state.get_resume_point()
        print(f"Incomplete work detected:")
        print(f"  Task: {resume['task']}")
        print(f"  Subtask: {resume['subtask']}")
        print(f"  Last update: {resume['last_update']}")
    else:
        print("No incomplete work found.")
