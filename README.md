# jupyterlab_restore_terminals_fix

[![GitHub Actions](https://github.com/stellarshenson/jupyterlab_restore_terminals_fix/actions/workflows/build.yml/badge.svg)](https://github.com/stellarshenson/jupyterlab_restore_terminals_fix/actions/workflows/build.yml)
[![npm version](https://img.shields.io/npm/v/jupyterlab_restore_terminals_fix.svg)](https://www.npmjs.com/package/jupyterlab_restore_terminals_fix)
[![PyPI version](https://img.shields.io/pypi/v/jupyterlab-restore-terminals-fix.svg)](https://pypi.org/project/jupyterlab-restore-terminals-fix/)
[![Total PyPI downloads](https://static.pepy.tech/badge/jupyterlab-restore-terminals-fix)](https://pepy.tech/project/jupyterlab-restore-terminals-fix)
[![JupyterLab 4](https://img.shields.io/badge/JupyterLab-4-orange.svg)](https://jupyterlab.readthedocs.io/en/stable/)
[![Brought To You By KOLOMOLO](https://img.shields.io/badge/Brought%20To%20You%20By-KOLOMOLO-00ffff?style=flat)](https://kolomolo.com)
[![Donate PayPal](https://img.shields.io/badge/Donate-PayPal-blue?style=flat)](https://www.paypal.com/donate/?hosted_button_id=B4KPBJDLLXTSA)

> [!TIP]
> This extension is part of the [stellars_jupyterlab_fixes](https://github.com/stellarshenson/stellars_jupyterlab_fixes) metapackage. Install all Stellars extensions at once: `pip install stellars_jupyterlab_fixes`

Fix for the common JupyterLab problem where terminal windows lose their working directories after workspace restoration. When JupyterLab restores a saved workspace (after server restart, browser refresh, etc.), all terminals reopen pointing to the notebook root instead of their original locations. This extension remembers and restores each terminal's working directory.

## Features

- **Automatic cwd restoration** - terminals reopen in their original working directories after workspace restore
- **Server-side cwd detection** - accurately determines each terminal's current directory via process inspection
- **Cross-platform support** - works on Linux (via /proc) and macOS (via lsof)
- **Transparent operation** - works automatically with no user interaction required

## Requirements

- JupyterLab >= 4.0.0

## Install

```bash
pip install jupyterlab_restore_terminals_fix
```

## Uninstall

To remove the extension, execute:

```bash
pip uninstall jupyterlab_restore_terminals_fix
```
