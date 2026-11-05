"""
Jurnal va qoldiq izchilligini tekshirish:

    1) har bir mahsulot uchun SUM(ledger.qty_delta) = stock_balance.qty
    2) har bir mahsulotning oxirgi jurnal qatoridagi qty_after = stock_balance.qty

    docker compose run --rm api python -m scripts.check_ledger

Farq topilsa, chiqish kodi 1 (cron yoki monitoringga ulash uchun).
"""

import sys

from sqlalchemy import text

from database.config import SessionLocal

QUERY = text(
    """
    WITH sums AS (
        SELECT product_id, SUM(qty_delta) AS total FROM ledger_entries GROUP BY product_id
    ), last AS (
        SELECT DISTINCT ON (product_id) product_id, qty_after
          FROM ledger_entries ORDER BY product_id, id DESC
    )
    SELECT p.code, s.qty AS balance, COALESCE(sums.total, 0) AS ledger_sum, last.qty_after
      FROM stock_balance s
      JOIN products p ON p.id = s.product_id
      LEFT JOIN sums ON sums.product_id = s.product_id
      LEFT JOIN last ON last.product_id = s.product_id
     WHERE s.qty <> COALESCE(sums.total, 0)
        OR s.qty <> COALESCE(last.qty_after, 0)
     ORDER BY p.code
    """
)


def main() -> int:
    with SessionLocal() as db:
        rows = db.execute(QUERY).all()
    if not rows:
        print("OK: jurnal va qoldiqlar mos.")
        return 0
    print("FARQ TOPILDI:")
    for code, balance, ledger_sum, qty_after in rows:
        print(f"  {code}: stock_balance={balance}, SUM(ledger)={ledger_sum}, oxirgi qty_after={qty_after}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
