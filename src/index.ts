import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { requestAPI } from './request';

/**
 * Initialization data for the jupyterlab_restore_terminals_fix extension.
 */
const plugin: JupyterFrontEndPlugin<void> = {
  id: 'jupyterlab_restore_terminals_fix:plugin',
  description: 'Jupyterlab fix in a form of extension for a common problem of restoring workspace after server restart etc... such that terminal windows are there, but they all were opened in the same location (notebook root). We\'d like to have them opened in the locations where they were opened originally.',
  autoStart: true,
  activate: (app: JupyterFrontEnd) => {
    console.log('JupyterLab extension jupyterlab_restore_terminals_fix is activated!');

    requestAPI<any>('hello', app.serviceManager.serverSettings)
      .then(data => {
        console.log(data);
      })
      .catch(reason => {
        console.error(
          `The jupyterlab_restore_terminals_fix server extension appears to be missing.\n${reason}`
        );
      });
  }
};

export default plugin;
