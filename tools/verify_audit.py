"""Recompute the audit-log hash chain and report the first break (docs/10 §6)."""
from __future__ import annotations

import sys

from _common import ROOT  # noqa: F401  (adds backend to sys.path)


def main() -> int:
    from healthvision.config.settings import load_config
    from healthvision.services.audit_service import AuditService
    from healthvision.storage.db import Database

    cfg = load_config()
    db = Database(cfg.resolve(cfg.settings.paths.data_dir) / "healthvision.db")
    with db.session() as s:
        res = AuditService.verify_chain(s)
    print(res)
    return 0 if res["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
