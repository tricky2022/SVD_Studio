# ADR-002: svdtools via adapter, not core

svdtools patch/derive is valuable but its internals change often.
We will call it (later) through `infrastructure/svdtools_adapter.py`
as an optional service, never import its internals into domain/.
