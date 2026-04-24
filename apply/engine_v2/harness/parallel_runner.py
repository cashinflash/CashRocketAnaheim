"""Shadow-mode runner — executes both engines, diffs outputs.

Dashboard shows v1 decision (primary) + v2 decision (shadow) for 2-4 weeks.
Cut over to v2 once:
    (a) all four known fixture cases match ground truth,
    (b) v2 beats v1 on Jorge/Michelle/Danitza/Sherrie flagged issues,
    (c) 2+ weeks of live shadow-mode shows no unexplained divergences.
"""

# TODO: wire to server.py's report generation path; emit a divergence log
# row whenever v1 and v2 disagree on tier or outcome.
