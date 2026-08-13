"""Thin async data-access modules, one per aggregate.

Every function takes an :class:`~sqlalchemy.ext.asyncio.AsyncSession` as its
first argument and never commits — the transaction boundary is the request
(see ``app.infrastructure.db.session.get_session``).
"""
