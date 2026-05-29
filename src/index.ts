import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { ITerminalTracker } from '@jupyterlab/terminal';
import { requestAPI } from './request';

const POLL_INTERVAL_MS = 15000;

/**
 * Report the names of all terminals currently in the layout to the server.
 *
 * The server resolves each one's cwd and persists it, then re-creates
 * those terminals on its next startup so the built-in workspace restore
 * connects to them already in the right directory. We send only the
 * tracker's terminals (i.e. those with a live widget / open tab) so
 * closed-tab sessions are not restored and do not become ghost entries.
 */
async function reportLayoutTerminals(
  terminalTracker: ITerminalTracker,
  serverSettings: any
): Promise<void> {
  const names: string[] = [];
  terminalTracker.forEach(widget => {
    const name = widget.content.session?.model?.name;
    if (name) {
      names.push(name);
    }
  });
  if (names.length === 0) {
    return;
  }
  try {
    await requestAPI('state', serverSettings, {
      method: 'POST',
      body: JSON.stringify({ names })
    });
  } catch {
    // ignore reporting errors
  }
}

const plugin: JupyterFrontEndPlugin<void> = {
  id: 'jupyterlab_restore_terminals_fix:plugin',
  description:
    'Restores terminal working directories after workspace restoration.',
  autoStart: true,
  requires: [ITerminalTracker],
  activate: (app: JupyterFrontEnd, terminalTracker: ITerminalTracker): void => {
    const serverSettings = app.serviceManager.serverSettings;

    // Restore is handled entirely server-side: the server pre-creates the
    // saved terminals at startup, before any frontend connects, so the
    // stock terminal plugin's restore connects to them in the right cwd.
    // The frontend only reports which terminals are in-layout and lets
    // the server snapshot their cwds.

    // Report shortly after a terminal opens (retry for pty spawn lag).
    terminalTracker.widgetAdded.connect(() => {
      const delays = [2000, 5000];
      for (const delay of delays) {
        setTimeout(() => {
          reportLayoutTerminals(terminalTracker, serverSettings);
        }, delay);
      }
    });

    // Periodic snapshot to capture `cd` between opens.
    setInterval(() => {
      reportLayoutTerminals(terminalTracker, serverSettings);
    }, POLL_INTERVAL_MS);
  }
};

export default plugin;
