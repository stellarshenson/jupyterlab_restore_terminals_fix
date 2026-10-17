import { expect, test } from '@jupyterlab/galata';

/**
 * Don't load JupyterLab webpage before running the tests.
 * This is required to ensure we capture all log messages.
 */
test.use({ autoGoto: false });

test('should emit an activation console message', async ({ page }) => {
  const logs: string[] = [];

  page.on('console', message => {
    logs.push(message.text());
  });

  await page.goto();

  expect(
    logs.filter(
      s =>
        s ===
        'JupyterLab extension jupyterlab_restore_terminals_fix is activated!'
    )
  ).toHaveLength(1);
});

test('should load without a slow-activation warning (ACC-REOPEN-9)', async ({
  page
}) => {
  const logs: string[] = [];

  page.on('console', message => {
    logs.push(message.text());
  });

  await page.goto();

  expect(logs.filter(s => s.includes('taking too long to activate'))).toEqual(
    []
  );
});

test('should save a newly opened terminal within 5 s (ACC-RECORD-10)', async ({
  page
}) => {
  await page.goto();

  const name = await page.evaluate(async () => {
    const widget = await window.jupyterapp.commands.execute(
      'terminal:create-new'
    );
    return widget.content.session.name as string;
  });

  const request = await page.waitForRequest(
    req =>
      req.method() === 'POST' &&
      req.url().includes('jupyterlab-restore-terminals-fix/state') &&
      (req.postDataJSON()?.names ?? []).includes(name),
    { timeout: 5000 }
  );

  expect(request.postDataJSON().names).toContain(name);
});
