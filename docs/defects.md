# Defects - jupyterlab_restore_terminals_fix

Defects in the server extension that records and restores terminal working directories, and in its frontend reporter.

## Authors

- `@kj` Konrad Jelen

## Server handlers `SERVER`

Python handlers for terminal cwd lookup and terminal state persistence

- [x] `DEF-SERVER-1` **keystrokes stall every 15 s** - CRITICAL; keystrokes in every terminal stall 128-198 ms exactly every 15.0 s; cause: POST /state resolves cwds on the event loop and `_get_direct_children` runs `pgrep -P` per leaf process; fix: /proc thread-union children, walk via run_in_executor; `jupyterlab_restore_terminals_fix/routes.py`
  - evidence: test_state_post_keeps_event_loop_serving and test_state_post_starts_no_subprocess pass; pytest 26/26
  - repro: type in any terminal while the frontend posts /jupyterlab-restore-terminals-fix/state; echo stalls every 15.0 s
  - test-tags: UNIT, INTEGRATION
  - root-cause: 2026-10-17T10:10:34Z @kj TerminalStateHandler.post runs `_get_process_cwd` on the event loop; `_get_direct_children` reads only the main-thread children file and falls back to `pgrep -P` for each leaf: 22 leaves x ~8 ms = ~180 ms per poll
  - log: 2026-10-17T10:10:34Z @kj added
  - log: 2026-10-17T10:10:34Z @kj reported by the workspace session 2026-10-17: 1,400 echo probes p50 1.2 ms, stalls at 11:10:09.53 and 11:10:24.53; py-spy of pid 526 in the stall windows shows post -> _get_direct_children -> subprocess.run(pgrep)
  - log: 2026-10-17T15:26:29Z @kj closed
- [x] `DEF-SERVER-2` **other workspace terminals reopen at root** - MAJOR; after a restart, terminals in the layout of a workspace not open at the time reopen at the server root; likely cause: POST /state replaces the whole saved state with the open page terminal names; `jupyterlab_restore_terminals_fix/routes.py`
  - evidence: test_acc_reopen_5_other_workspace_terminal_kept and test_workspace_terminal_names_reads_workspace_files_only pass; iso-e2e line 20
  - root-cause: 2026-10-17T14:57:30Z @kj POST /state replaced the saved state with the open page's terminal names; terminals held only by another workspace file dropped off
  - repro: workspace A with a terminal in a subfolder, switch to workspace B, wait 15 s, restart, open A, run pwd
  - test-tags: INTEGRATION
  - log: 2026-10-17T10:23:05Z @kj added
  - log: 2026-10-17T15:26:29Z @kj closed

## Frontend reporter `FRONT`

The JupyterLab plugin that reports open terminal tabs to the server

- [x] `DEF-FRONT-3` **closed last tab comes back after restart** - MEDIUM; after the last terminal tab is closed, a restart re-creates that terminal with no tab, shown only under Running Terminals; likely cause: the frontend skips the save when no terminal tab is open; `src/index.ts`
  - evidence: Jest empty-list test and test_acc_reopen_4_last_tab_closed_recreates_nothing pass; iso-e2e line 11
  - root-cause: 2026-10-17T14:57:30Z @kj the frontend returned before posting when no terminal tab was open; the last closed tab's entry was never cleared
  - repro: open one terminal, close its tab, wait 15 s, restart the server, open Running Terminals
  - test-tags: UNIT, FUNCTIONAL
  - log: 2026-10-17T10:23:05Z @kj added
  - log: 2026-10-17T15:26:29Z @kj closed

