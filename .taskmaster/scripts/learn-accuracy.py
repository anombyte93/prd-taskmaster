#!/usr/bin/env python3
"""
Estimation accuracy learning system.
Analyzes actual vs estimated times and improves future estimates.
"""

import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from track_time import get_all_task_times, calculate_accuracy

class AccuracyLearner:
    def __init__(self):
        self.reports_dir = Path(".taskmaster/reports")
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.accuracy_file = self.reports_dir / "estimation-accuracy.json"
        self.load_accuracy_data()

    def load_accuracy_data(self):
        """Load historical accuracy data."""
        if self.accuracy_file.exists():
            with open(self.accuracy_file, 'r') as f:
                self.data = json.load(f)
        else:
            self.data = {
                "tasks_analyzed": 0,
                "average_accuracy": 100.0,
                "adjustment_factor": 1.0,
                "history": []
            }

    def save_accuracy_data(self):
        """Save accuracy data."""
        with open(self.accuracy_file, 'w') as f:
            json.dump(self.data, f, indent=2)

    def analyze_task(self, task_id, estimated_minutes, actual_minutes):
        """Analyze a single task's accuracy."""
        accuracy = calculate_accuracy(estimated_minutes, actual_minutes)

        entry = {
            "task_id": task_id,
            "estimated_minutes": estimated_minutes,
            "actual_minutes": actual_minutes,
            "accuracy_percent": accuracy,
            "variance_percent": accuracy - 100
        }

        self.data["history"].append(entry)
        self.data["tasks_analyzed"] += 1

        # Recalculate average
        total_accuracy = sum(h["accuracy_percent"] for h in self.data["history"])
        self.data["average_accuracy"] = round(total_accuracy / len(self.data["history"]), 1)

        # Update adjustment factor
        self.data["adjustment_factor"] = round(self.data["average_accuracy"] / 100, 2)

        self.save_accuracy_data()

        return entry

    def get_adjusted_estimate(self, base_estimate_minutes):
        """Apply learned adjustment to new estimate."""
        adjusted = base_estimate_minutes * self.data["adjustment_factor"]
        return round(adjusted, 0)

    def generate_report(self):
        """Generate human-readable accuracy report."""
        if self.data["tasks_analyzed"] < 3:
            return "❌ Need at least 3 completed tasks for accuracy analysis."

        history = self.data["history"]
        avg_accuracy = self.data["average_accuracy"]
        adjustment = self.data["adjustment_factor"]

        # Find outliers
        outliers = [h for h in history if abs(h["variance_percent"]) > 50]

        report = f"""
📊 Estimation Accuracy Report

Tasks Analyzed: {self.data["tasks_analyzed"]}
Average Accuracy: {avg_accuracy}%
Adjustment Factor: {adjustment}x

Recent Tasks:
"""

        for h in history[-10:]:  # Last 10 tasks
            status = "✅" if 90 <= h["accuracy_percent"] <= 110 else "⚠️"
            report += f"  Task {h['task_id']}: {h['actual_minutes']}min (est: {h['estimated_minutes']}min) - {h['accuracy_percent']}% {status}\n"

        if avg_accuracy < 90:
            report += f"\n⚠️  You're completing tasks {100 - avg_accuracy:.0f}% faster than estimated.\n"
            report += f"🎯 Recommendation: Reduce future estimates by {(1 - adjustment) * 100:.0f}%\n"
        elif avg_accuracy > 110:
            report += f"\n⚠️  You're taking {avg_accuracy - 100:.0f}% longer than estimated.\n"
            report += f"🎯 Recommendation: Increase future estimates by {(adjustment - 1) * 100:.0f}%\n"
        else:
            report += f"\n✅ Your estimates are accurate! Keep it up.\n"

        if outliers:
            report += f"\n⚠️  {len(outliers)} outlier tasks found (>50% variance):\n"
            for o in outliers:
                report += f"  Task {o['task_id']}: {o['variance_percent']:+.0f}% variance\n"

        return report

if __name__ == "__main__":
    learner = AccuracyLearner()
    print(learner.generate_report())
