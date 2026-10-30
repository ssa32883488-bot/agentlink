"""座椅加工场景 · 全量物料 / BOM / 包装体积（对齐《6agent的技术设计》）。

编码约定：文档中的「RM-ARM REST」统一为 RM-ARMREST；
供应商 B 文档里的 RM-FABRIC-BLK / RM-FOAM-50 与采购侧高档/普通档对齐为：
  高档面料 RM-FABRIC-PRO、普通面料 RM-FABRIC-STD、
  记忆海绵 RM-FOAM-MEM、普通海绵 RM-FOAM-STD。
"""
from __future__ import annotations

from typing import Any

# 单椅组成：扶手1 + 五星脚1 + 脚轮5 + 气压棒1 + 椅架1 + 海绵1 + 面料1
SEAT_BOM_TEMPLATE = {
    "armrest": 1,
    "base": 1,
    "caster": 5,
    "gaslift": 1,
    "tube": 1,
    "foam": 1,
    "fabric": 1,
}

# 全量物料主数据：code, name, unit, pack_cm(LWH), volume_m3, kg_per_unit, charge_class
# kg_per_unit / volume_m3 供询运与报价回执全量规格；禁止只有体积没有重量。
MATERIALS_MASTER: list[dict[str, Any]] = [
    {
        "code": "RM-ARMREST",
        "name": "扶手组件",
        "unit": "对",
        "pack_cm": (40, 30, 15),
        "volume_m3": 0.018,
        "kg_per_unit": 2.8,
        "charge_class": "heavy",
        "note": "一对装纸箱",
    },
    {
        "code": "RM-BASE-NYLON",
        "name": "五星脚底座",
        "unit": "个",
        "pack_cm": (70, 70, 15),
        "volume_m3": 0.0735,
        "kg_per_unit": 4.5,
        "charge_class": "heavy",
        "note": "伞状拆解平放装",
    },
    {
        "code": "RM-GASLIFT",
        "name": "气压棒",
        "unit": "根",
        "pack_cm": (45, 10, 10),
        "volume_m3": 0.0045,
        "kg_per_unit": 1.2,
        "charge_class": "heavy",
        "note": "纸筒或扁盒装",
    },
    {
        "code": "RM-TUBE-STEEL",
        "name": "钢管制件椅架",
        "unit": "套",
        "pack_cm": (80, 40, 15),
        "volume_m3": 0.048,
        "kg_per_unit": 6.5,
        "charge_class": "heavy",
        "note": "防刮擦拆装打包",
    },
    {
        "code": "RM-CASTER-300",
        "name": "重型脚轮300kg",
        "unit": "只",
        "pack_cm": (25, 20, 10),
        "volume_m3": 0.005,
        "charge_class": "heavy",
        "note": "按单只计；BOM 每椅 5 只",
        "kg_per_unit": 0.4,
    },
    {
        "code": "RM-CASTER-200",
        "name": "标准脚轮200kg",
        "unit": "只",
        "pack_cm": (25, 20, 10),
        "volume_m3": 0.005,
        "charge_class": "heavy",
        "note": "按单只计；BOM 每椅 5 只",
        "kg_per_unit": 0.35,
    },
    {
        "code": "RM-FOAM-MEM",
        "name": "记忆海绵坐垫",
        "unit": "块",
        "pack_cm": (55, 55, 15),
        "volume_m3": 0.045,
        "kg_per_unit": 1.8,
        "charge_class": "bulky",
        "note": "含木板，防尘袋装",
    },
    {
        "code": "RM-FOAM-STD",
        "name": "普通海绵坐垫",
        "unit": "块",
        "pack_cm": (55, 55, 15),
        "volume_m3": 0.045,
        "kg_per_unit": 1.5,
        "charge_class": "bulky",
        "note": "含木板，防尘袋装",
    },
    {
        "code": "RM-FABRIC-PRO",
        "name": "高档座椅面料",
        "unit": "套",
        "pack_cm": (30, 25, 10),
        "volume_m3": 0.0075,
        "kg_per_unit": 0.9,
        "charge_class": "bulky",
        "note": "单椅用量，折叠压缩袋装",
    },
    {
        "code": "RM-FABRIC-STD",
        "name": "普通座椅面料",
        "unit": "套",
        "pack_cm": (30, 25, 10),
        "volume_m3": 0.0075,
        "kg_per_unit": 0.7,
        "charge_class": "bulky",
        "note": "单椅用量，折叠压缩袋装",
    },
]

# 采购商 A：高档座椅产线
BUYER_A_MATERIALS = [
    ("RM-ARMREST", "扶手组件", "对", "supplier-a", 40),
    ("RM-BASE-NYLON", "五星脚底座", "个", "supplier-a", 40),
    ("RM-GASLIFT", "气压棒", "根", "supplier-c", 60),
    ("RM-TUBE-STEEL", "钢管制件椅架", "套", "supplier-a", 40),
    ("RM-CASTER-300", "重型脚轮300kg", "只", "supplier-a", 150),
    ("RM-FOAM-MEM", "记忆海绵坐垫", "块", "supplier-b", 50),
    ("RM-FABRIC-PRO", "高档座椅面料", "套", "supplier-b", 80),
]
BUYER_A_INV = {
    "RM-ARMREST": 38,
    "RM-BASE-NYLON": 36,
    "RM-GASLIFT": 25,  # 低于安全线 → 易告警
    "RM-TUBE-STEEL": 35,
    "RM-CASTER-300": 120,
    "RM-FOAM-MEM": 42,
    "RM-FABRIC-PRO": 55,
}
BUYER_A_BOM = [  # 高档办公椅
    ("RM-ARMREST", 1),
    ("RM-BASE-NYLON", 1),
    ("RM-GASLIFT", 1),
    ("RM-TUBE-STEEL", 1),
    ("RM-CASTER-300", 5),
    ("RM-FOAM-MEM", 1),
    ("RM-FABRIC-PRO", 1),
]

# 采购商 B：平价办公/家用
BUYER_B_MATERIALS = [
    ("RM-ARMREST", "扶手组件", "对", "supplier-a", 40),
    ("RM-BASE-NYLON", "五星脚底座", "个", "supplier-c", 40),
    ("RM-GASLIFT", "气压棒", "根", "supplier-a", 50),
    ("RM-TUBE-STEEL", "钢管制件椅架", "套", "supplier-a", 35),
    ("RM-CASTER-200", "标准脚轮200kg", "只", "supplier-a", 120),
    ("RM-FOAM-STD", "普通海绵坐垫", "块", "supplier-b", 50),
    ("RM-FABRIC-STD", "普通座椅面料", "套", "supplier-b", 60),
]
BUYER_B_INV = {
    "RM-ARMREST": 55,
    "RM-BASE-NYLON": 48,
    "RM-GASLIFT": 70,
    "RM-TUBE-STEEL": 50,
    "RM-CASTER-200": 200,
    "RM-FOAM-STD": 60,
    "RM-FABRIC-STD": 28,  # 偏低 → 易告警
}
BUYER_B_BOM = [
    ("RM-ARMREST", 1),
    ("RM-BASE-NYLON", 1),
    ("RM-GASLIFT", 1),
    ("RM-TUBE-STEEL", 1),
    ("RM-CASTER-200", 5),
    ("RM-FOAM-STD", 1),
    ("RM-FABRIC-STD", 1),
]

# 供应商目录：code, name, unit, list_price, floor_price(=list，已取消私下底价), on_hand, strategy, moq, lead_days
# floor 列仅兼容旧库 schema，取值恒等于挂牌价；真实优惠只走 promotions。
SUPPLIER_A_CATALOG = [
    ("RM-ARMREST", "扶手组件", "对", 30.0, 30.0, 600, "price-first", 1, 5),
    ("RM-BASE-NYLON", "五星脚底座", "个", 40.0, 40.0, 500, "price-first", 1, 6),
    ("RM-GASLIFT", "气压棒", "根", 50.0, 50.0, 400, "price-first", 1, 5),
    ("RM-CASTER-300", "重型脚轮300kg", "只", 20.0, 20.0, 2000, "price-first", 1, 5),
    ("RM-CASTER-200", "标准脚轮200kg", "只", 15.0, 15.0, 2500, "price-first", 1, 5),
    ("RM-TUBE-STEEL", "钢管制件椅架", "套", 85.0, 85.0, 300, "price-first", 1, 7),
]

SUPPLIER_B_CATALOG = [
    ("RM-FABRIC-PRO", "高档座椅面料", "套", 35.0, 35.0, 1500, "custom-moq", 50, 10),
    ("RM-FABRIC-STD", "普通座椅面料", "套", 12.0, 12.0, 3000, "custom-moq", 50, 8),
    ("RM-FOAM-MEM", "记忆海绵坐垫", "块", 55.0, 55.0, 800, "custom-moq", 20, 10),
    ("RM-FOAM-STD", "普通海绵坐垫", "块", 20.0, 20.0, 1200, "custom-moq", 20, 8),
]

SUPPLIER_C_CATALOG = [
    ("RM-ARMREST", "扶手组件", "对", 35.0, 35.0, 200, "scarce-substitute", 1, 5),
    ("RM-BASE-NYLON", "五星脚底座", "个", 35.0, 35.0, 180, "scarce-substitute", 1, 6),
    ("RM-TUBE-STEEL", "钢管制件椅架", "套", 100.0, 100.0, 120, "scarce-substitute", 1, 8),
    ("RM-CASTER-200", "标准脚轮200kg", "只", 15.0, 15.0, 800, "scarce-substitute", 1, 5),
    ("RM-FOAM-MEM", "记忆海绵坐垫", "块", 50.0, 50.0, 150, "scarce-substitute", 1, 7),
    ("RM-FOAM-STD", "普通海绵坐垫", "块", 20.0, 20.0, 200, "scarce-substitute", 1, 6),
]

# 供应商优惠（结构化，供 pricing / promo 读取）
SUPPLIER_A_PROMOS = {
    "line_qty_discount": [
        {
            "skus": ["RM-CASTER-300", "RM-CASTER-200"],
            "threshold_qty": 500,
            "discount_pct": 0.10,
            "label": "脚轮单品满500件该单品总价九折",
        }
    ]
}

SUPPLIER_B_PROMOS = {
    "full_reduction": [
        {
            "label": "软装任意组合货价满1万减1000",
            "threshold_amount": 10000,
            "reduce_amount": 1000,
        }
    ]
}

SUPPLIER_C_PROMOS = {
    "line_qty_discount": [
        {
            "skus": ["RM-TUBE-STEEL"],
            "threshold_qty": 500,
            "discount_pct": 0.15,
            "label": "钢管制件椅架满500件打8.5折",
        }
    ],
    "cross_province_subsidy": {
        "enabled": True,
        "label": "跨省运费补贴一半",
        "origin_province": "山西",
        "min_qty": 1,
        "subsidy_pct_of_freight": 0.5,
        "uncertain": True,
        "note": "只要跨省运输可申请运费补贴一半；演示政策，审核存在不确定性",
    },
}

# 物流服务矩阵
LOGISTICS_SERVICES = {
    "express": {
        "label": "极速达",
        "eta_days": (1, 2),
        "base_fee": 350.0,
        "per_kg": 1.5,
        "per_m3": 300.0,
        "base_units": "首100kg或1方",
    },
    "standard": {
        "label": "标准快线",
        "eta_days": (3, 4),
        "base_fee": 180.0,
        "per_kg": 0.8,
        "per_m3": 150.0,
        "base_units": "首100kg或1方",
    },
    "economy": {
        "label": "经济拼车",
        "eta_days": (5, 7),
        "base_fee": 80.0,
        "per_kg": 0.4,
        "per_m3": 80.0,
        "base_units": "首100kg或1方",
    },
}

LOGISTICS_ROUTE_BANDS = [
    {"name": "同省同城", "max_km": 300, "factor": 1.0},
    {"name": "邻省华北", "max_km": 800, "factor": 1.2},
    {"name": "跨大区全国", "max_km": 10**9, "factor": 1.5},
]

BULKY_DIM_FACTOR = 200.0  # 1 m³ = 200 kg 计费重


def material_by_code(code: str) -> dict[str, Any] | None:
    for m in MATERIALS_MASTER:
        if m["code"] == code:
            return m
    return None


def estimate_weight_kg(code: str | None, qty: float = 1.0) -> float | None:
    """按单件重量 × 数量估算实际重量；无 kg_per_unit 则返回 None。"""
    mat = material_by_code(str(code or "").upper()) if code else None
    if not mat or mat.get("kg_per_unit") is None:
        return None
    try:
        return max(0.01, round(float(mat["kg_per_unit"]) * float(qty), 3))
    except (TypeError, ValueError):
        return None


def product_physical_specs(
    code: str | None,
    *,
    qty: float = 1.0,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """报价/询运用的全量物理规格：重量、体积、包装、计费类别。"""
    sku = str(code or "").strip().upper()
    mat = material_by_code(sku) if sku else None
    out: dict[str, Any] = dict(extra or {})
    if not mat:
        if sku:
            out.setdefault("sku", sku)
        return out
    pack = mat.get("pack_cm") or ()
    unit_vol = float(mat.get("volume_m3") or 0)
    unit_kg = mat.get("kg_per_unit")
    try:
        q = float(qty)
    except (TypeError, ValueError):
        q = 1.0
    out.update(
        {
            "sku": mat["code"],
            "name": mat.get("name") or mat["code"],
            "unit": mat.get("unit") or "件",
            "pack_cm": list(pack) if pack else None,
            "volume_m3_unit": unit_vol,
            "volume_m3": round(unit_vol * q, 4),
            "kg_per_unit": float(unit_kg) if unit_kg is not None else None,
            "weight_kg": estimate_weight_kg(mat["code"], q),
            "charge_class": mat.get("charge_class") or "heavy",
            "note": mat.get("note"),
            "quantity": q,
        }
    )
    return out


def chargeable_weight_kg(
    *,
    actual_kg: float,
    volume_m3: float,
    charge_class: str = "heavy",
) -> float:
    """实际重量与体积重量取大者；抛货按 1方=200kg。"""
    dim_kg = float(volume_m3) * BULKY_DIM_FACTOR if charge_class == "bulky" else float(volume_m3) * (1_000_000 / 6000) / 1000.0
    # 体积重量标准：cm³/6000 → kg；若已有 m³：m³ * 1e6 / 6000
    if charge_class != "bulky":
        dim_kg = float(volume_m3) * 1_000_000.0 / 6000.0
    else:
        dim_kg = float(volume_m3) * BULKY_DIM_FACTOR
    return max(float(actual_kg), dim_kg)


def route_factor(distance_km: float) -> tuple[str, float]:
    d = float(distance_km or 0)
    for band in LOGISTICS_ROUTE_BANDS:
        if d <= float(band["max_km"]):
            return str(band["name"]), float(band["factor"])
    return "跨大区全国", 1.5
