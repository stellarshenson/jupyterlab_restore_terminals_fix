import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { IStateDB } from '@jupyterlab/statedb';
import { ITerminalTracker } from '@jupyterlab/terminal';
import { requestAPI } from './request';

const TERMINAL_NS = 'terminal';
const POLL_INTERVAL_MS = 15000;

interface ITerminalCwdResponse {
  terminal_name: string;
  cwd: string;
  relative_cwd?: string;
  error?: string;
}

interface IAllTerminalCwdsResponse {
  terminals: ITerminalCwdResponse[];
}

interface IRelCwdMap {
  [terminalName: string]: string;
}

interface ITerminalWidgetData {
  data: { name: string; cwd?: string };
}

async function fetchAllCwds(serverSettings: any): Promise<IRelCwdMap> {
  try {
    const data = await requestAPI<IAllTerminalCwdsResponse>(
      'cwds',
      serverSettings
    );
    const map: IRelCwdMap = {};
    for (const entry of data.terminals) {
      if (entry.relative_cwd) {
        map[entry.terminal_name] = entry.relative_cwd;
      }
    }
    return map;
  } catch {
    return {};
  }
}

async function fetchTerminalRelCwd(
  terminalName: string,
  serverSettings: any
): Promise<string | null> {
  try {
    const data = await requestAPI<ITerminalCwdResponse>(
      `cwd/${terminalName}`,
      serverSettings
    );
    return data.relative_cwd || null;
  } catch {
    return null;
  }
}

/**
 * Patch the workspace entry for a terminal with its server-root-relative
 * cwd. The built-in terminal:create-new command reads this on the next
 * workspace restore and reopens the terminal in that directory.
 *
 * Patch-only: if the `terminal:<name>` entry does not already exist
 * (terminal not part of the current workspace layout) we skip it. That
 * keeps us from creating ghost entries in the Running Terminals sidebar
 * and naturally isolates per-workspace state (IStateDB is per-workspace).
 */
async function patchTerminalCwd(
  stateDB: IStateDB,
  name: string,
  relativeCwd: string
): Promise<void> {
  const key = `${TERMINAL_NS}:${name}`;
  try {
    const existing = await stateDB.fetch(key);
    if (!existing) {
      return;
    }
    const widgetData = existing as unknown as ITerminalWidgetData;
    if (widgetData.data.cwd === relativeCwd) {
      return;
    }
    widgetData.data.cwd = relativeCwd;
    await stateDB.save(key, widgetData as any);
  } catch {
    // ignore stateDB errors
  }
}

const plugin: JupyterFrontEndPlugin<void> = {
  id: 'jupyterlab_restore_terminals_fix:plugin',
  description:
    'Restores terminal working directories after workspace restoration.',
  autoStart: true,
  requires: [IStateDB],
  optional: [ITerminalTracker],
  activate: (
    app: JupyterFrontEnd,
    stateDB: IStateDB,
    terminalTracker: ITerminalTracker | null
  ): void => {
    if (!terminalTracker) {
      return;
    }

    const serverSettings = app.serviceManager.serverSettings;

    // Restore is handled by the built-in terminal plugin: it reads the
    // cwd we keep patched into each terminal:<name> workspace entry and
    // reopens the terminal there. No restore-phase code needed here.

    // -- Save phase: capture cwd shortly after a terminal opens --
    // Retries because the pty child shell may not have spawned yet at
    // widget-creation time, so /proc cwd is not ready immediately.
    terminalTracker.widgetAdded.connect((_sender, widget) => {
      const delays = [2000, 4000, 8000];
      for (const delay of delays) {
        setTimeout(() => {
          if (widget.isDisposed) {
            return;
          }
          const name = widget.content.session?.model?.name;
          if (!name) {
            return;
          }
          fetchTerminalRelCwd(name, serverSettings)
            .then(rel => {
              if (rel) {
                return patchTerminalCwd(stateDB, name, rel);
              }
            })
            .catch(() => {});
        }, delay);
      }
    });

    // -- Save phase: periodic poll to track cd between opens --
    setInterval(async () => {
      try {
        const cwds = await fetchAllCwds(serverSettings);
        for (const [name, rel] of Object.entries(cwds)) {
          await patchTerminalCwd(stateDB, name, rel);
        }
      } catch {
        // ignore polling errors
      }
    }, POLL_INTERVAL_MS);
  }
};

export default plugin;
