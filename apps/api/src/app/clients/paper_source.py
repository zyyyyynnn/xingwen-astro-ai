"""API-side paper source integration boundary.

``services.paper_pipeline`` owns paper acquisition. API application services
call that package and publish its validated content;
the HTTP client layer must not copy the adapter or publication rules here.
"""
