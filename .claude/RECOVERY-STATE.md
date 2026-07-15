# Recovery State

Cold-restart board for `jupyterlab_restore_terminals_fix`. A fresh session with zero
context resumes from this file alone.

---

## BRACE 2026-07-15 Wed 14:31

### HORIZON: SESSION-ONLY

Opus 4.8 usage limit hit (98%, resets ~5am). Only this CLI session dies - the JupyterHub
server and all its terminal sessions stay alive. Nothing to reattach: no detached compute,
no background jobs, no subagents were running when braced. On resume, just pick up the
diagnosis below.

### What survives on its own

- The live JupyterHub server (`https://jupyterhub.lab.stellars-tech.eu/user/konrad.jelen/`)
  and its running terminal sessions - untouched by this brace
- Published extension **v0.9.26** on npm + PyPI (the server-side pre-creation restore fix,
  journal entry 7) - installed and working for the restart-restore case
- Git tree was CLEAN before this brace (only this recovery file is new)

### Current state of the work

The **restore-at-root bug is SOLVED and shipped** (v0.9.26): cwds are persisted server-side
to `jupyter_data_dir/restore_terminals_fix/state-<sha1>.json`; `prepopulate_terminals()`
re-creates each saved terminal via `terminal_manager.create(name, cwd)` on startup before
any browser connects, so stock restore's `terminal:create-new {name}` connects to the
running session in its saved cwd. Validated on isolated server + confirmed live.

Then a **regression report** came in: after the user did a server reset and returned, all
terminal tabs were closed. Investigation followed.

### DIAGNOSIS (confirmed, user-agreed) - it is NOT the terminals, it is the WORKSPACE

- **Terminals are fine.** They are re-created and running; they appear in the Running
  Terminals list. The user confirmed: *"terminals are not culled; they are ok; it is the
  workspace problem; workspace is never restored."*
- **Culler is EXONERATED.** Live query of the culler
  (`.../jupyterlab-kernel-terminal-workspace-culler-extension/cull-result`) returned
  `{"kernels_culled": [], "terminals_culled": [], "workspaces_culled": []}`. Settings:
  `terminalCullIdleTimeout: 60` (min), `terminalCullDisconnectedOnly: true`,
  `workspaceCullEnabled: true`, `workspaceCullIdleTimeout: 10080` (7 days),
  `cullCheckInterval: 5` (min). At the 60-min default the disconnected-terminal cull rarely
  fires; it is not touching anything right now.
- **Real culprit = workspace auto-clone.** Workspace file inventory showed:
  - `default` - terms=0 (empty layout)
  - `auto-u` - terms=0
  - `auto-A` - terms=0 (the `?reset=1` one)
  - `auto-r` - **terms=5** (the real layout: `terminal:3,5,6,9,4`)
  The user keeps landing in an EMPTY workspace (`default`/`auto-A`/`auto-u`) whose layout
  has zero terminal references, while the actual 5-terminal layout lives in `auto-r`. Every
  workspace switch/reset spawns a fresh empty `auto-X`. "Switch to default" or "create
  default" doesn't reach the good layout - a new empty workspace is created instead.

### FIRST ACTION (next session)

Diagnose the **workspace auto-clone bug** - do NOT touch code until root cause is confirmed
and the user has chosen a direction (prior premature fixes repeatedly failed).

Investigate why JupyterLab 4.6.1 under JupyterHub keeps landing the user in a fresh empty
`auto-X` instead of the `auto-r` workspace holding their layout, and why "switch to default"
doesn't work. Specifically:
- How `/lab` with no explicit workspace resolves/clones a workspace; role of `?reset=1`
  (it forces the target workspace empty AND persists that emptiness)
- Whether the empty `default` workspace is being persisted OVER the good `auto-r` layout
- Whether the fix belongs in restore-terminals-fix, the culler, or is a JupyterHub/JupyterLab
  config issue (workspace resolution, not a terminal-cwd issue at all)
- Workspace API path is `/lab/api/workspaces/<name>` (NOT `/api/workspaces/<name>` - 404s)

### Pending artifacts

- Culler bug-report drafted at:
  `<scratchpad>/culler-conflict-report.md`
  (scratchpad dir this session:
  `/tmp/claude-1000/-home-lab-workspace-private-jupyterlab-jupyterlab-restore-terminals-fix/fd35560b-f1b9-4aa4-92f7-4f4c4abc137b/scratchpad/`)
  NOTE: this report is about a *real but separate* culler flaw (culls server-pre-created
  terminals that no frontend has claimed). It is NOT the current live symptom. Its final
  section already notes the workspace auto-clone issue is tracked separately. Scratchpad is
  under /tmp and may not survive a host reboot - but horizon is SESSION-ONLY so it should
  still be there on resume. If gone, it can be regenerated from journal entry 7 + the culler
  internals notes.

### Hard rules still in force (do not violate on resume)

- No git commit/push/tag without explicit user approval EVERY time
- No version bump / publish / `make publish` without explicit request (Makefile `publish`
  auto-increments version - it over-incremented twice already this campaign)
- Use Makefile targets, not manual installs
- Journal only via the `journal` plugin (`/journal:update`), never direct Edit
- Never mass-delete terminals (killed the user's active terminal once doing this)
- To kill a test server by port, resolve one PID and `kill` it - never
  `pkill -f "port=NNNN"` (that killed my own shell)
