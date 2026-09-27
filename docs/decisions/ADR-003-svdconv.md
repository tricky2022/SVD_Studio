# ADR-003: SVDConv as external subprocess

SVDConv is the authoritative checker. Invoke via subprocess when
`SVDCONV` env/path configured; never link as library; never let
GUI depend on it. Missing binary => validation degrades gracefully.
