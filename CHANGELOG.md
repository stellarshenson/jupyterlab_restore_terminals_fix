# Changelog

<!-- <START NEW CHANGELOG ENTRY> -->

## [0.9.30] - 2026-10-17

### Added

- Functional restart test that starts two real Jupyter servers and verifies the saved terminal is re-created in its folder
- macOS process-tree coverage for the pgrep and lsof fallback

### Changed

- The state save keeps the last saved folder of a terminal held by another saved workspace while that terminal is not running

### Fixed

- Keystrokes no longer stall every 15 s: the process-tree walk runs off the event loop and starts no subprocess on Linux
- A terminal in another saved workspace keeps its folder across a restart instead of reopening at the root
- Closing the last terminal tab clears its saved entry, so the terminal is not re-created after a restart

<!-- <END NEW CHANGELOG ENTRY> -->
