import { ITerminalTracker } from '@jupyterlab/terminal';
import { Signal } from '@lumino/signaling';
import plugin from '../index';
import { requestAPI } from '../request';

jest.mock('../request');

const mockedRequestAPI = requestAPI as jest.MockedFunction<typeof requestAPI>;

function fakeTracker(names: string[]) {
  const widgets = names.map(name => ({
    content: { session: { model: { name } } }
  }));
  return {
    widgets,
    widgetAdded: new Signal<object, any>({}),
    forEach: (fn: (widget: any) => void) => widgets.forEach(fn)
  };
}

function activate(tracker: ReturnType<typeof fakeTracker>): void {
  const app = { serviceManager: { serverSettings: {} } };
  plugin.activate(app as any, tracker as any);
}

function postedNames(callIndex: number): string[] {
  const [endPoint, , init] = mockedRequestAPI.mock.calls[callIndex];
  expect(endPoint).toBe('state');
  expect(init!.method).toBe('POST');
  return JSON.parse(init!.body as string).names;
}

describe('jupyterlab_restore_terminals_fix', () => {
  it('should export a plugin with correct id', () => {
    expect(plugin.id).toBe('jupyterlab_restore_terminals_fix:plugin');
  });

  it('should require ITerminalTracker', () => {
    expect(plugin.requires).toContain(ITerminalTracker);
  });

  it('should have autoStart enabled', () => {
    expect(plugin.autoStart).toBe(true);
  });
});

describe('terminal state reporting', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    mockedRequestAPI.mockClear();
  });

  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
  });

  it('posts a newly opened terminal within 5 s (ACC-RECORD-10)', () => {
    const tracker = fakeTracker(['7']);
    activate(tracker);

    tracker.widgetAdded.emit(tracker.widgets[0]);
    jest.advanceTimersByTime(5000);

    expect(mockedRequestAPI).toHaveBeenCalled();
    expect(postedNames(0)).toContain('7');
  });

  it('posts again every 15 s (ACC-RECORD-11)', () => {
    const tracker = fakeTracker(['7']);
    activate(tracker);

    jest.advanceTimersByTime(14999);
    expect(mockedRequestAPI).not.toHaveBeenCalled();

    jest.advanceTimersByTime(1);
    expect(mockedRequestAPI).toHaveBeenCalledTimes(1);
    expect(postedNames(0)).toEqual(['7']);

    jest.advanceTimersByTime(15000);
    expect(mockedRequestAPI).toHaveBeenCalledTimes(2);
    expect(postedNames(1)).toEqual(['7']);
  });

  it('posts an empty list when no terminal tab is open (ACC-REOPEN-4, DEF-FRONT-3)', () => {
    activate(fakeTracker([]));

    jest.advanceTimersByTime(15000);

    expect(mockedRequestAPI).toHaveBeenCalledTimes(1);
    expect(postedNames(0)).toEqual([]);
  });
});
