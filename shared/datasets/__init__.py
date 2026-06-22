"""Shared datasets. The fraud dataset loader lives here (not under modules/targets/)
because more than one pillar uses it: the fraud target trains on it, the differential
and held-out oracles read its splits, and the blue retrain appends to it. Per
constitution.md section 2, cross-pillar utilities belong in shared/."""
