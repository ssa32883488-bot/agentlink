"""采购商 A/B + 供应商 A/B/C 种子数据：座椅加工场景（对齐《6agent的技术设计》）。"""
from __future__ import annotations

from commerce.db import connect, init_buyer_schema, init_supplier_schema
from commerce.seat_catalog import (
    BUYER_A_BOM,
    BUYER_A_INV,
    BUYER_A_MATERIALS,
    BUYER_B_BOM,
    BUYER_B_INV,
    BUYER_B_MATERIALS,
    SUPPLIER_A_CATALOG,
    SUPPLIER_B_CATALOG,
    SUPPLIER_C_CATALOG,
)


def seed_buyer(agent: str = "buyer-a", *, reset: bool = False) -> None:
    from commerce.db import db_path

    p = db_path(agent)
    if reset and p.exists():
        p.unlink()
    conn = connect(agent)
    init_buyer_schema(conn)
    exists = conn.execute("SELECT 1 FROM products LIMIT 1").fetchone()
    if exists and not reset:
        conn.close()
        return

    if agent == "buyer-b":
        materials, inv_map, bom = BUYER_B_MATERIALS, BUYER_B_INV, BUYER_B_BOM
        products = [
            ("CHAIR-ECO", "平价办公椅", 399.0, "承德产线·标准脚轮+普通海绵面料，家用/门店走量款"),
            ("CHAIR-HOME", "家用座椅", 459.0, "承德产线·舒适家用款"),
        ]
    else:
        materials, inv_map, bom = BUYER_A_MATERIALS, BUYER_A_INV, BUYER_A_BOM
        products = [
            ("CHAIR-PRO", "高档办公椅", 899.0, "保定产线·重型脚轮+记忆海绵+高档面料"),
            ("CHAIR-EXEC", "行政座椅", 1299.0, "保定产线·高定行政款"),
        ]

    conn.execute("DELETE FROM bom")
    conn.execute("DELETE FROM inventory")
    conn.execute("DELETE FROM materials")
    conn.execute("DELETE FROM products")
    for code, name, unit, pref, safety in materials:
        conn.execute(
            "INSERT OR REPLACE INTO materials(code,name,unit,preferred_supplier,safety_stock) VALUES(?,?,?,?,?)",
            (code, name, unit, pref, safety),
        )
        conn.execute(
            "INSERT OR REPLACE INTO inventory(material_code,on_hand,reserved) VALUES(?,?,0)",
            (code, inv_map.get(code, 0)),
        )
    for sku, name, price, desc in products:
        conn.execute(
            "INSERT OR REPLACE INTO products(sku,name,price,description,active) VALUES(?,?,?,?,1)",
            (sku, name, price, desc),
        )
        for code, qty in bom:
            conn.execute(
                "INSERT OR REPLACE INTO bom(finished_sku,material_code,qty_per) VALUES(?,?,?)",
                (sku, code, qty),
            )
    conn.commit()
    conn.close()


def seed_buyer_a(*, reset: bool = False) -> None:
    seed_buyer("buyer-a", reset=reset)


def seed_buyer_b(*, reset: bool = False) -> None:
    seed_buyer("buyer-b", reset=reset)


def _seed_supplier(agent: str, rows: list, *, reset: bool = False) -> None:
    from commerce.db import db_path

    p = db_path(agent)
    if reset and p.exists():
        p.unlink()
    conn = connect(agent)
    init_supplier_schema(conn)
    exists = conn.execute("SELECT 1 FROM catalog LIMIT 1").fetchone()
    if exists and not reset:
        conn.close()
        return
    conn.execute("DELETE FROM catalog")
    for row in rows:
        conn.execute(
            """INSERT OR REPLACE INTO catalog
            (code,name,unit,list_price,floor_price,on_hand,strategy_tag,moq,lead_time_days)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            row,
        )
    conn.commit()
    conn.close()


def seed_all(*, reset: bool = True) -> None:
    seed_buyer_a(reset=reset)
    seed_buyer_b(reset=reset)
    _seed_supplier("supplier-a", SUPPLIER_A_CATALOG, reset=reset)
    _seed_supplier("supplier-b", SUPPLIER_B_CATALOG, reset=reset)
    _seed_supplier("supplier-c", SUPPLIER_C_CATALOG, reset=reset)
    print("seed_ok buyer-a/b + supplier-a/b/c (seat catalog)")


if __name__ == "__main__":
    seed_all(reset=True)
