import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { IStateDB } from '@jupyterlab/statedb';
import { ITerminalTracker } from '@jupyterlab/terminal';
import { requestAPI } from './request';

const STATEDB_KEY = 'jupyterlab_restore_terminals_fix:terminal-cwds';
const POLL_INTERVAL_MS = 15000;

interface ITerminalCwdResponse {
  terminal_name: string;
  cwd: string;
  error?: string;
}

interface IAllTerminalCwdsResponse {
  terminals: ITerminalCwdResponse[];
}

interface ICwdMap {
  [terminalName: string]: string;
}

async function fetchAllCwds(
  serverSettings: any
): Promise<ICwdMap> {
  try {
    const data = await requestAPI<IAllTerminalCwdsResponse>(
      'cwds',
      serverSettings
    );
    const map: ICwdMap = {};
    for (const entry of data.terminals) {
      map[entry.terminal_name] = entry.cwd;
    }
    return map;
  } catch {
    return {};
  }
}

async function fetchTerminalCwd(
  terminalName: string,
  serverSettings: any
): Promise<string | null> {
  try {
    const data = await requestAPI<ITerminalCwdResponse>(
      `cwd/${terminalName}`,
      serverSettings
    );
    return data.cwd || null;
  } catch {
    return null;
  }
}

async function saveCwds(stateDB: IStateDB, cwds: ICwdMap): Promise<void> {
  await stateDB.save(STATEDB_KEY, cwds as any);
}

async function loadCwds(stateDB: IStateDB): Promise<ICwdMap> {
  const data = await stateDB.fetch(STATEDB_KEY);
  if (data) {
    return data as unknown as ICwdMap;
  }
  return {};
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
  ) => {
    if (!terminalTracker) {
      console.warn(
        'jupyterlab_restore_terminals_fix: ITerminalTracker not available'
      );
      return;
    }

    const serverSettings = app.serviceManager.serverSettings;

    // -- Restore phase: run once after workspace restore --
    app.restored.then(async () => {
      const savedCwds = await loadCwds(stateDB);
      if (Object.keys(savedCwds).length === 0) {
        return;
      }

      // Brief delay to let terminal sessions initialise
      await new Promise(resolve => setTimeout(resolve, 1500));

      terminalTracker.forEach(widget => {
        try {
          const session = widget.content.session;
          const name = session?.model?.name;
          if (!name || !savedCwds[name]) {
            return;
          }
          const targetCwd = savedCwds[name];
          session.send({
            type: 'stdin',
            content: [`cd ${shellQuote(targetCwd)}\n`]
          });
        } catch {
          // terminal may have been disposed
        }
      });
    });

    // -- Save phase: capture cwd on terminal open --
    terminalTracker.widgetAdded.connect((_sender, widget) => {
      // Wait for terminal to initialise before querying cwd
      setTimeout(async () => {
        try {
          const name = widget.content.session?.model?.name;
          if (!name) {
            return;
          }
          const cwd = await fetchTerminalCwd(name, serverSettings);
          if (cwd) {
            const cwds = await loadCwds(stateDB);
            cwds[name] = cwd;
            await saveCwds(stateDB, cwds);
          }
        } catch {
          // ignore
        }
      }, 1000);
    });

    // -- Save phase: periodic poll every 15s --
    setInterval(async () => {
      try {
        const cwds = await fetchAllCwds(serverSettings);
        if (Object.keys(cwds).length > 0) {
          const existing = await loadCwds(stateDB);
          const merged = { ...existing, ...cwds };
          await saveCwds(stateDB, merged);
        }
      } catch {
        // ignore polling errors
      }
    }, POLL_INTERVAL_MS);
  }
};

function shellQuote(s: string): string {
  return "'" + s.replace(/'/g, "'\\''") + "'";
}

export default plugin;
