"""API-side paper source integration boundary.

D-02 acquisition is implemented in ``services.paper_pipeline``.  A later B-06
application service may call that package and publish its validated content;
the HTTP client layer must not copy the adapter or publication rules here.
"""
