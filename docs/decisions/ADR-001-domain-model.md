# ADR-001: own domain model, not cmsis-svd objects

cmsis-svd maps XML to Python objects but loses ordering/comments and
couples app to a third-party API. We keep our own dataclasses in
`domain/model.py` and use cmsis-svd only as reference + optional
cross-check. Parser lives in infrastructure/ over lxml.
