import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { URLExt } from '@jupyterlab/coreutils';
import { ServerConnection } from '@jupyterlab/services';
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
  serverSettings: ServerConnection.ISettings
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
  serverSettings: ServerConnection.ISettings
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

async function precreateTerminals(
  savedCwds: ICwdMap,
  serverSettings: ServerConnection.ISettings
): Promise<void> {
  const url = URLExt.join(serverSettings.baseUrl, 'api', 'terminals');
  const requests = Object.entries(savedCwds).map(([name, cwd]) =>
    ServerConnection.makeRequest(
      url,
      {
        method: 'POST',
        body: JSON.stringify({ name, cwd })
      },
      serverSettings
    ).catch(() => {
      // terminal may already exist (browser refresh) - that's fine
    })
  );
  await Promise.all(requests);
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

    // -- Restore phase: fire-and-forget pre-creation --
    // Don't await - activation must return immediately to avoid
    // blocking JupyterLab startup. Pre-creation races workspace
    // restore; if it wins, terminals open in saved cwds.
    loadCwds(stateDB).then(savedCwds => {
      if (Object.keys(savedCwds).length > 0) {
        precreateTerminals(savedCwds, serverSettings);
      }
    });

    // -- Save phase: capture cwd on terminal open --
    terminalTracker.widgetAdded.connect((_sender, widget) => {
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

export default plugin;
