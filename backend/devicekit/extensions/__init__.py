"""Namespace package for installed-extension backends (plan 03).

Each installed extension's ``backend/`` half is extracted to
``devicekit/extensions/<slug>/`` and imported as ``devicekit.extensions.<slug>.<module>``.
This directory holds only extracted extensions at runtime — nothing here is tracked except
this file. Extensions are hot-loaded by :class:`devicekit.mixins.extensions.ExtensionsMixin`.
"""
