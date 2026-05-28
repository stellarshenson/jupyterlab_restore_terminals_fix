import plugin from '../index';

describe('jupyterlab_restore_terminals_fix', () => {
  it('should export a plugin with correct id', () => {
    expect(plugin.id).toBe('jupyterlab_restore_terminals_fix:plugin');
  });

  it('should require IStateDB', () => {
    expect(plugin.requires).toBeDefined();
    expect(plugin.requires!.length).toBeGreaterThanOrEqual(1);
  });

  it('should have autoStart enabled', () => {
    expect(plugin.autoStart).toBe(true);
  });
});
