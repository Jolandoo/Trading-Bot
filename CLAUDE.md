# Trading Bot — Claude Code Instructions

## Verification Before Push
- Always run the full test suite and build before committing
- Never push to remote until the user explicitly confirms - commit locally first and wait for review
- Flag any remaining warnings, type errors, or test failures before suggesting commit/push

## UI/Styling Workflow
- For alignment, z-index, and layout issues, inspect the full component tree and parent containers before making changes - don't iterate blindly
- When working with React Native + Expo, always check Expo SDK compatibility before installing native packages (e.g., react-native-svg)
- For timezone-sensitive UI (charts, time markers), explicitly handle local vs UTC conversion and add a comment noting the assumption

## Cross-Platform Scripts
- When writing or running Python/Node scripts, assume Windows compatibility: use UTF-8 encoding explicitly for file I/O and avoid emoji/non-ASCII in print statements unless encoding is set
