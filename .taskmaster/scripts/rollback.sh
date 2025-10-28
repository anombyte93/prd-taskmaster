#!/bin/bash
# .taskmaster/scripts/rollback.sh
# Rollback to any task checkpoint

TASK_ID=$1

if [ -z "$TASK_ID" ]; then
  echo "❌ Error: Task ID required"
  echo "Usage: rollback.sh <task_id>"
  exit 1
fi

TAG="checkpoint-task-${TASK_ID}"

# Check if tag exists
if ! git tag -l | grep -q "^${TAG}$"; then
  echo "❌ Error: Checkpoint tag '${TAG}' not found"
  echo "Available checkpoints:"
  git tag -l "checkpoint-task-*" | sort -V
  exit 1
fi

echo "🔄 Rolling back to ${TAG}..."

# Safety check
echo "⚠️  This will:"
echo "  - Discard all changes after Task ${TASK_ID}"
echo "  - Reset to checkpoint-task-${TASK_ID}"
echo "  - Preserve current work in rollback-backup branch"
echo ""
echo "Continue? (yes/no)"
read -r CONFIRM

if [ "$CONFIRM" != "yes" ]; then
  echo "❌ Rollback cancelled"
  exit 0
fi

# Create backup branch of current state
BACKUP_BRANCH="rollback-backup-$(date +%Y%m%d-%H%M%S)"
git checkout -b "$BACKUP_BRANCH"
git checkout main

echo "💾 Backed up current state to: ${BACKUP_BRANCH}"

# Reset to checkpoint
git reset --hard "${TAG}"

echo "✅ Rolled back to Task ${TASK_ID} completion state"
echo "📝 Updating progress.md..."

# Log rollback
cat >> .taskmaster/docs/progress.md <<EOF

---
## ROLLBACK PERFORMED
**Timestamp**: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
**Rolled back to**: Task ${TASK_ID} (${TAG})
**Backup branch**: ${BACKUP_BRANCH}
**Reason**: User-initiated rollback

Tasks after ${TASK_ID} discarded. Ready to resume from Task ${TASK_ID}.
---

EOF

echo ""
echo "🎯 Next steps:"
echo "  1. Resume from Task $((TASK_ID + 1))"
echo "  2. Redo Task ${TASK_ID} differently"
echo "  3. Review backup: git checkout ${BACKUP_BRANCH}"
