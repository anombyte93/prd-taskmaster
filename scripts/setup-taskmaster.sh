#!/bin/bash
# Setup taskmaster directory structure
# This script creates the necessary .taskmaster/ directories and files
# for taskmaster AI integration

set -e  # Exit on error

echo "🔧 Setting up taskmaster directory structure..."

# Create main .taskmaster directory
if [ ! -d ".taskmaster" ]; then
  mkdir -p .taskmaster
  echo "✅ Created .taskmaster/ directory"
else
  echo "ℹ️  .taskmaster/ directory already exists"
fi

# Create subdirectories
mkdir -p .taskmaster/docs
mkdir -p .taskmaster/tasks
mkdir -p .taskmaster/reports

echo "✅ Created subdirectories: docs/, tasks/, reports/"

# Update .gitignore to exclude taskmaster state files
GITIGNORE_FILE=".gitignore"

if [ -f "$GITIGNORE_FILE" ]; then
  if ! grep -q ".taskmaster/state.json" "$GITIGNORE_FILE" 2>/dev/null; then
    echo "" >> "$GITIGNORE_FILE"
    echo "# Taskmaster AI state files" >> "$GITIGNORE_FILE"
    echo ".taskmaster/state.json" >> "$GITIGNORE_FILE"
    echo ".taskmaster/tasks/" >> "$GITIGNORE_FILE"
    echo ".taskmaster/reports/" >> "$GITIGNORE_FILE"
    echo "✅ Updated .gitignore with taskmaster exclusions"
  else
    echo "ℹ️  .gitignore already configured for taskmaster"
  fi
else
  # Create .gitignore if it doesn't exist
  echo "# Taskmaster AI state files" > "$GITIGNORE_FILE"
  echo ".taskmaster/state.json" >> "$GITIGNORE_FILE"
  echo ".taskmaster/tasks/" >> "$GITIGNORE_FILE"
  echo ".taskmaster/reports/" >> "$GITIGNORE_FILE"
  echo "✅ Created .gitignore with taskmaster exclusions"
fi

# Create placeholder README in docs/
if [ ! -f ".taskmaster/docs/README.md" ]; then
  cat > .taskmaster/docs/README.md <<'EOF'
# Taskmaster Documentation

This directory contains project documentation for taskmaster AI.

## Files

- `prd.md` - Product Requirements Document (auto-generated)
- `task-hints.md` - Task breakdown suggestions (optional)

## Usage

1. Ensure `prd.md` exists with comprehensive requirements
2. Run `taskmaster init` to initialize project
3. Run `taskmaster generate` to generate tasks from PRD
4. Run `taskmaster start` to begin implementation

See https://www.task-master.dev/ for full documentation.
EOF
  echo "✅ Created .taskmaster/docs/README.md"
fi

# Create placeholder config if taskmaster CLI not initialized
if [ ! -f ".taskmaster/config.json" ]; then
  cat > .taskmaster/config.json <<'EOF'
{
  "version": "2.0",
  "project": {
    "name": "Project Name",
    "description": "Project description"
  },
  "ai": {
    "provider": "anthropic",
    "model": "claude-sonnet-4"
  },
  "workflow": {
    "autoGenerate": false,
    "taskFormat": "json"
  }
}
EOF
  echo "✅ Created placeholder .taskmaster/config.json"
  echo "ℹ️  Note: Run 'taskmaster init' to configure with your API keys"
fi

echo ""
echo "🎉 Taskmaster directory structure ready!"
echo ""
echo "Directory structure:"
echo ".taskmaster/"
echo "├── config.json        (placeholder - run 'taskmaster init' to configure)"
echo "├── docs/"
echo "│   ├── README.md"
echo "│   └── prd.md         (will be created by PRD skill)"
echo "├── tasks/             (taskmaster generates tasks here)"
echo "└── reports/           (taskmaster creates reports here)"
echo ""
echo "Next steps:"
echo "1. PRD will be created at .taskmaster/docs/prd.md"
echo "2. Install taskmaster CLI: npm install -g task-master-ai"
echo "3. Initialize taskmaster: taskmaster init"
echo "4. Generate tasks: taskmaster generate"
echo ""
