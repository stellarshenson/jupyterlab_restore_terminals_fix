# Acceptance Criteria - jupyterlab_restore_terminals_fix

Terminals reopen in the folder they were last in after the Jupyter server restarts. The server saves each terminal's working folder while JupyterLab runs and re-creates the saved terminals at startup, before any browser connects, so the stock workspace restore attaches to them.

## Authors

- `@kj` Konrad Jelen

## Reopen after restart `REOPEN`

Terminals coming back after the Jupyter server restarts

- [x] `ACC-REOPEN-1` **Reopen in saved folder** - CRITICAL; after a server restart, a terminal whose tab was open reopens in the folder it was last in, not the server root
  - evidence: test_restart_recreates_saved_terminal and test_acc_reopen_1_terminal_reopens_in_saved_folder pass; logs/iso-e2e.log line 9 shows tabs 1,2 in saved folders
  - test: isolated server, cd a terminal into a subfolder, wait 15 s, restart the server, run pwd in the reopened tab
  - test-tags: UNIT, FUNCTIONAL
  - mechanism: 2026-10-17T10:23:04Z @kj server re-creates each saved terminal by name in its saved folder at startup, before any browser connects; the stock restore attaches to it
  - log: 2026-10-17T10:23:04Z @kj added
  - log: 2026-10-17T15:26:28Z @kj closed
- [x] `ACC-REOPEN-2` **No typed command** - MEDIUM; a reopened terminal shows no cd command typed into it
  - evidence: test_acc_reopen_2_no_cd_typed passes; logs/iso-e2e.log line 10 shows no cd line in either reopened buffer
  - test: after the restart in the saved-folder test, read the terminal output, assert no line starting with cd
  - test-tags: FUNCTIONAL
  - log: 2026-10-17T10:23:04Z @kj added
  - log: 2026-10-17T15:26:28Z @kj closed
- [x] `ACC-REOPEN-3` **Closed tab not reopened** - HIGH; a terminal whose tab was closed before the restart, and that no saved workspace layout holds, is not re-created
  - evidence: test_acc_reopen_3_closed_tab_not_recreated passes; logs/iso-e2e.log line 7 shows running 1,2 after restart
  - test: two terminals, close one tab, wait 15 s, restart, assert only the open one runs
  - test-tags: INTEGRATION, FUNCTIONAL
  - log: 2026-10-17T10:23:04Z @kj added
  - log: 2026-10-17T15:26:28Z @kj closed
- [x] `ACC-REOPEN-4` **Edge: last tab closed** - HIGH; after the last terminal tab is closed, a restart re-creates no terminal
  - evidence: test_acc_reopen_4_last_tab_closed_recreates_nothing and Jest empty-list test pass; logs/iso-e2e.log line 14 shows no terminal re-created
  - related: DEF-FRONT-3 - 0.9.26 brings this terminal back
  - test: one terminal, close its tab, wait 15 s, restart, assert no terminal runs
  - test-tags: UNIT, FUNCTIONAL
  - log: 2026-10-17T10:23:04Z @kj added
  - log: 2026-10-17T15:26:28Z @kj closed
- [x] `ACC-REOPEN-5` **Other workspace kept** - HIGH; a terminal in the layout of another saved workspace is re-created in its saved folder after a restart, though no open page shows it
  - evidence: test_acc_reopen_5_other_workspace_terminal_kept passes with the manager cleared; logs/iso-e2e.log line 20 shows the other-workspace terminal in its folder
  - related: DEF-SERVER-2 - 0.9.26 drops these terminals
  - test: workspace file holding terminal:N, POST /state without N, assert N keeps its saved folder
  - test-tags: INTEGRATION
  - log: 2026-10-17T10:23:04Z @kj added
  - log: 2026-10-17T15:26:28Z @kj closed
- [x] `ACC-REOPEN-6` **Edge: saved folder deleted** - MEDIUM; a terminal whose saved folder no longer exists is not re-created; startup continues
  - evidence: test_acc_reopen_6_deleted_folder_not_recreated passes
  - test: state with a missing folder, run prepopulate_terminals, assert no create call and no error
  - test-tags: UNIT
  - log: 2026-10-17T10:23:04Z @kj added
  - log: 2026-10-17T15:26:28Z @kj closed
- [x] `ACC-REOPEN-7` **Edge: name already running** - MEDIUM; startup never replaces a running terminal that has a saved name
  - evidence: test_acc_reopen_7_running_name_not_replaced passes
  - test: terminal_manager already holds the name, run prepopulate_terminals, assert no create call
  - test-tags: UNIT
  - log: 2026-10-17T10:23:04Z @kj added
  - log: 2026-10-17T15:26:28Z @kj closed
- [x] `ACC-REOPEN-8` **Separate state per root** - MEDIUM; servers with different root folders keep separate saved folders
  - evidence: test_acc_reopen_8_separate_state_per_root passes
  - test: two server roots, assert _state_file returns two different paths
  - test-tags: UNIT
  - log: 2026-10-17T10:23:04Z @kj added
  - log: 2026-10-17T15:26:28Z @kj closed
- [x] `ACC-REOPEN-9` **Fast startup** - HIGH; JupyterLab finishes loading without the warning "is taking too long to activate" for this plugin
  - evidence: Galata should load without a slow-activation warning (ACC-REOPEN-9) passes, 3/3
  - test: load the lab in Galata, assert no console message containing taking too long to activate
  - test-tags: E2E
  - log: 2026-10-17T10:23:04Z @kj added
  - log: 2026-10-17T15:26:28Z @kj closed

## Recording during use `RECORD`

How terminal folders are saved while JupyterLab runs

- [x] `ACC-RECORD-10` **Saved on open** - HIGH; a newly opened terminal's folder is saved within 5 s, without waiting for the periodic save
  - evidence: Jest posts a newly opened terminal within 5 s and Galata should save a newly opened terminal within 5 s pass
  - test: jest fake timers: add a terminal widget, advance 5 s, assert a POST /state naming it; Galata: open a terminal, see the POST within 5 s
  - test-tags: UNIT, E2E
  - log: 2026-10-17T10:23:04Z @kj added
  - log: 2026-10-17T15:26:28Z @kj closed
- [x] `ACC-RECORD-11` **Folder change saved** - HIGH; a cd in an open terminal is saved within 15 s
  - evidence: Jest posts again every 15 s and test_acc_record_11_cd_saved pass
  - test: jest fake timers: advance 15 s, assert a POST /state; pytest: process in a subfolder, POST /state, assert that folder saved
  - test-tags: UNIT, INTEGRATION
  - log: 2026-10-17T10:23:04Z @kj added
  - log: 2026-10-17T15:26:28Z @kj closed
- [x] `ACC-RECORD-12` **Closed tab dropped** - HIGH; a terminal with no open tab and in no saved workspace layout is dropped from the saved state at the next save
  - evidence: test_acc_record_12_closed_tab_dropped passes
  - test: POST /state without the name, no workspace file holds it, assert it is gone from the state
  - test-tags: INTEGRATION
  - log: 2026-10-17T10:23:05Z @kj added
  - log: 2026-10-17T15:26:28Z @kj closed
- [x] `ACC-RECORD-13` **Deepest process folder** - MEDIUM; the saved folder is that of the deepest process in the terminal's process tree, a shell preferred at equal depth
  - evidence: test_acc_record_13_deepest_process_folder, test_acc_record_13_shell_preferred_at_equal_depth and test_macos_fallback_uses_pgrep_and_lsof pass
  - test: helper tree with a child in a subfolder, assert _get_process_cwd returns the subfolder
  - test-tags: UNIT
  - log: 2026-10-17T10:23:05Z @kj added
  - log: 2026-10-17T15:26:28Z @kj closed
- [x] `ACC-RECORD-14` **Edge: child started by a thread** - MEDIUM; a program started by a non-main thread of a process in the terminal is found when the folder is looked up
  - evidence: test_direct_children_include_thread_forked_child passes
  - test: helper whose second thread starts sleep 60 and stays alive, assert _get_direct_children finds the sleep pid
  - test-tags: UNIT
  - log: 2026-10-17T10:23:05Z @kj added
  - log: 2026-10-17T15:26:28Z @kj closed
- [x] `ACC-RECORD-15` **Edge: process exits mid-read** - MEDIUM; a process that exits while folders are read is skipped and the save still succeeds
  - evidence: test_acc_record_15_exited_process_skipped passes; the cwd and environ guards are both exercised, deleting either fails the test
  - test: make one /proc read raise FileNotFoundError, POST /state, assert 200 and the other terminals saved
  - test-tags: UNIT
  - log: 2026-10-17T10:23:05Z @kj added
  - log: 2026-10-17T15:26:29Z @kj closed
- [x] `ACC-RECORD-16` **Typing never stalls** - CRITICAL; saving terminal folders never pauses the server event loop
  - evidence: test_state_post_keeps_event_loop_serving passes, largest event-loop gap under 0.2 s
  - related: DEF-SERVER-1 - the event-loop stall this rules out
  - test: slow the folder lookup to 0.5 s, POST /state, assert the largest event-loop gap stays under 0.2 s
  - test-tags: INTEGRATION
  - log: 2026-10-17T10:23:05Z @kj added
  - log: 2026-10-17T15:26:29Z @kj closed
- [x] `ACC-RECORD-17` **No subprocess on Linux** - HIGH; looking up terminal folders on Linux starts no subprocess
  - evidence: test_state_post_starts_no_subprocess passes; zero subprocess calls on Linux
  - related: DEF-SERVER-1 - pgrep per leaf process was its cause
  - test: record subprocess.run and Popen calls, POST /state with a terminal that has leaf processes, assert no calls
  - test-tags: INTEGRATION
  - log: 2026-10-17T10:23:05Z @kj added
  - log: 2026-10-17T15:26:29Z @kj closed
- [x] `ACC-RECORD-18` **Edge: no terminal service** - LOW; the state API answers 503 when the server has no terminal service
  - evidence: test_acc_record_18_no_terminal_service passes, 503
  - test: remove terminal_manager from the server settings, POST /state, assert 503
  - test-tags: INTEGRATION
  - log: 2026-10-17T10:23:05Z @kj added
  - log: 2026-10-17T15:26:29Z @kj closed

