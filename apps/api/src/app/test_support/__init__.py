"""Test-only support helpers.

This package is only wired into the application when ``APP_ENV`` is ``test``
or ``integration`` (see ``app.main.create_app``). It is never mounted in
``development`` or ``production`` and must never contain production logic.
"""
