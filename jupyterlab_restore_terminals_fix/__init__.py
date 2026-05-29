try:
    from ._version import __version__
except ImportError:
    # Fallback when using the package in dev mode without installing
    # in editable mode with pip. It is highly recommended to install
    # the package from a stable release or in editable mode: https://pip.pypa.io/en/stable/topics/local-project-installs/#editable-installs
    import warnings
    warnings.warn("Importing 'jupyterlab_restore_terminals_fix' outside a proper installation.")
    __version__ = "dev"
from .routes import prepopulate_terminals, setup_route_handlers


def _jupyter_labextension_paths():
    return [{
        "src": "labextension",
        "dest": "jupyterlab_restore_terminals_fix"
    }]


def _jupyter_server_extension_points():
    return [{
        "module": "jupyterlab_restore_terminals_fix"
    }]


def _load_jupyter_server_extension(server_app):
    """Registers the API handler to receive HTTP requests from the frontend extension.

    Parameters
    ----------
    server_app: jupyterlab.labapp.LabApp
        JupyterLab application instance
    """
    setup_route_handlers(server_app.web_app)
    name = "jupyterlab_restore_terminals_fix"
    server_app.log.info(f"Registered {name} server extension")

    # Pre-create saved terminals once the IO loop is running, deferred so
    # the terminals server extension has installed its terminal_manager
    # into web_app.settings first (server-extension load order is not
    # guaranteed). This runs before any frontend connects, so the stock
    # workspace restore's `terminal:create-new {name}` connects to the
    # already-running session in its saved cwd instead of starting a fresh
    # shell at the root.
    def _prepopulate():
        try:
            prepopulate_terminals(server_app)
        except Exception as exc:  # noqa: BLE001
            server_app.log.warning(
                "restore_terminals_fix: prepopulate failed: %s", exc
            )

    try:
        import tornado.ioloop

        tornado.ioloop.IOLoop.current().call_later(1.0, _prepopulate)
    except Exception:  # noqa: BLE001
        _prepopulate()
