import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { URLExt } from '@jupyterlab/coreutils';
import { ServerConnection } from '@jupyterlab/services';
import { IStateDB } from '@jupyterlab/statedb';
import { ITerminalTracker } from '@jupyterlab/terminal';
import { requestAPI } from './request';

const TAG = '[restore-terminals-fix]';
const PLUGIN_KEY = 'jupyterlab_restore_terminals_fix:terminal-cwds';
const TERMINAL_NS = 'terminal';
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

async function precreateTerminals(
  cwds: ICwdMap,
  serverSettings: ServerConnection.ISettings
): Promise<void> {
  const url = URLExt.join(serverSettings.baseUrl, 'api', 'terminals');
  const requests = Object.entries(cwds).map(([name, cwd]) =>
    ServerConnection.makeRequest(
      url,
      { method: 'POST', body: JSON.stringify({ name, cwd }) },
      serverSettings
    )
      .then(resp => {
        console.log(
          `${TAG} pre-created terminal ${name} cwd=${cwd} status=${resp.status}`
        );
      })
      .catch(() => {
        console.log(`${TAG} pre-create failed for ${name} (may exist)`);
      })
  );
  await Promise.all(requests);
}

async function getLayoutTerminalNames(
  stateDB: IStateDB
): Promise<Set<string>> {
  const names = new Set<string>();
  const layout = (await stateDB.fetch(
    'layout-restorer:data'
  )) as any;
  if (!layout) {
    return names;
  }
  const collect = (node: any) => {
    if (!node) {
      return;
    }
    const widgets: string[] = node.widgets || [];
    for (const w of widgets) {
      if (w.startsWith(`${TERMINAL_NS}:`)) {
        names.add(w.replace(`${TERMINAL_NS}:`, ''));
      }
    }
    if (node.children) {
      for (const child of node.children) {
        collect(child);
      }
    }
  };
  collect(layout.main?.dock);
  collect(layout.down);
  return names;
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
    console.log(`${TAG} activate called`);
    if (!terminalTracker) {
      return;
    }

    const serverSettings = app.serviceManager.serverSettings;

    // -- Restore phase --
    // Pre-create terminals with saved cwds after all plugins activate
    // but BEFORE layout restorer replays commands. app.started resolves
    // after all plugin activate() calls complete. The layout restorer
    // waits for app.started + its own promise chain, so pre-creation
    // runs first.
    app.started.then(async () => {
      console.log(`${TAG} app.started - beginning pre-creation`);
      const layoutNames = await getLayoutTerminalNames(stateDB);
      console.log(
        `${TAG} layout terminals: ${[...layoutNames].join(', ')}`
      );

      const data = await stateDB.fetch(PLUGIN_KEY);
      if (!data) {
        console.log(`${TAG} no saved cwds`);
        return;
      }
      const allCwds = data as unknown as ICwdMap;

      // Only pre-create terminals that are in the layout
      const toRestore: ICwdMap = {};
      for (const name of layoutNames) {
        if (allCwds[name]) {
          toRestore[name] = allCwds[name];
        }
      }

      // Clean stale entries
      const cleaned: ICwdMap = {};
      for (const name of layoutNames) {
        if (allCwds[name]) {
          cleaned[name] = allCwds[name];
        }
      }
      await stateDB.save(PLUGIN_KEY, cleaned as any);
      console.log(
        `${TAG} cleaned cwds to layout-only: ${JSON.stringify(cleaned)}`
      );

      if (Object.keys(toRestore).length > 0) {
        await precreateTerminals(toRestore, serverSettings);
      }
    }).catch(err => {
      console.warn(`${TAG} restore error:`, err);
    });

    // -- Save phase: capture cwd on terminal open --
    terminalTracker.widgetAdded.connect((_sender, widget) => {
      console.log(`${TAG} widgetAdded fired, id=${widget.id}`);
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
          fetchTerminalCwd(name, serverSettings)
            .then(async cwd => {
              console.log(`${TAG} [${delay}ms] ${name} cwd=${cwd}`);
              if (cwd) {
                const existing =
                  ((await stateDB.fetch(
                    PLUGIN_KEY
                  )) as unknown as ICwdMap) || {};
                existing[name] = cwd;
                await stateDB.save(PLUGIN_KEY, existing as any);
              }
            })
            .catch(() => {});
        }, delay);
      }
    });

    // -- Save phase: periodic poll --
    setInterval(async () => {
      try {
        const cwds = await fetchAllCwds(serverSettings);
        if (Object.keys(cwds).length > 0) {
          const layoutNames = await getLayoutTerminalNames(stateDB);
          const existing =
            ((await stateDB.fetch(PLUGIN_KEY)) as unknown as ICwdMap) ||
            {};
          // Only keep terminals that are in the layout
          const merged: ICwdMap = {};
          for (const name of layoutNames) {
            merged[name] = cwds[name] || existing[name] || '';
          }
          await stateDB.save(PLUGIN_KEY, merged as any);
        }
      } catch {
        // ignore polling errors
      }
    }, POLL_INTERVAL_MS);
  }
};

export default plugin;
