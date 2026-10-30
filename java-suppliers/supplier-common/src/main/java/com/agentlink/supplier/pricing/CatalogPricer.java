package com.agentlink.supplier.pricing;

import com.agentlink.supplier.policy.SupplierPolicy;

import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class CatalogPricer {
    private static final Pattern CODE = Pattern.compile("\\b(RM-[A-Z0-9-]+)\\b", Pattern.CASE_INSENSITIVE);

    private CatalogPricer() {}

    public static String normalizeSku(String text) {
        if (text == null || text.isBlank()) {
            return null;
        }
        String s = text.trim().toUpperCase(Locale.ROOT).replace(" ", "");
        if (s.startsWith("RM-")) {
            return s;
        }
        Matcher m = CODE.matcher(text);
        if (m.find()) {
            return m.group(1).toUpperCase(Locale.ROOT).replace(" ", "");
        }
        Map<String, String> aliases = new java.util.LinkedHashMap<>();
        aliases.put("重型脚轮", "RM-CASTER-300");
        aliases.put("标准脚轮", "RM-CASTER-200");
        aliases.put("脚轮", "RM-CASTER-300");
        aliases.put("扶手", "RM-ARMREST");
        aliases.put("五星脚", "RM-BASE-NYLON");
        aliases.put("气压棒", "RM-GASLIFT");
        aliases.put("椅架", "RM-TUBE-STEEL");
        aliases.put("记忆海绵坐垫", "RM-FOAM-MEM");
        aliases.put("记忆海绵", "RM-FOAM-MEM");
        aliases.put("普通海绵坐垫", "RM-FOAM-STD");
        aliases.put("普通海绵", "RM-FOAM-STD");
        aliases.put("海绵坐垫", "RM-FOAM-MEM");
        aliases.put("坐垫", "RM-FOAM-MEM");
        aliases.put("高档面料", "RM-FABRIC-PRO");
        aliases.put("普通面料", "RM-FABRIC-STD");
        aliases.put("面料", "RM-FABRIC-PRO");
        for (var e : aliases.entrySet()) {
            if (text.contains(e.getKey())) {
                return e.getValue();
            }
        }
        return null;
    }

    /** 解析请求物料码；未识别时返回 null（不再静默落到默认 SKU）。 */
    public static String requestedSku(String productName, String sku, Map<String, Object> specs) {
        String want = normalizeSku(sku);
        if (want == null && specs != null) {
            Object s = specs.getOrDefault("sku", specs.get("material_code"));
            want = normalizeSku(s == null ? null : String.valueOf(s));
        }
        if (want == null) {
            want = normalizeSku(productName);
        }
        return want;
    }

    public static SupplierPolicy.CatalogItem resolve(
            SupplierPolicy policy, String productName, String sku, Map<String, Object> specs
    ) {
        String want = requestedSku(productName, sku, specs);
        if (want == null || policy.catalog == null) {
            return null;
        }
        for (var row : policy.catalog) {
            if (row.sku != null && row.sku.equalsIgnoreCase(want)) {
                return row;
            }
        }
        // 明确请求的 SKU 不在本厂目录 → 拒报，禁止回落默认面料/首行
        return null;
    }

    public static Map<String, Object> quote(
            SupplierPolicy policy,
            int quantity,
            String productName,
            String sku,
            Map<String, Object> specs
    ) {
        String want = requestedSku(productName, sku, specs);
        var item = resolve(policy, productName, sku, specs);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("requested_sku", want);
        out.put("requested_product_name", productName);
        if (item == null) {
            out.put("catalog_hit", false);
            out.put("can_fulfill", false);
            out.put("pricing_mode", "list_plus_promo_only");
            out.put(
                    "reject_reason",
                    want == null
                            ? "无法识别请求物料，拒绝用默认商品冒充报价"
                            : ("本厂目录无此物料: " + want + (productName != null ? " (" + productName + ")" : ""))
            );
            return out;
        }

        double listUnit = item.unit_price;
        int avail = item.available_quantity;
        int baseLead = item.lead_time_days > 0
                ? item.lead_time_days
                : (policy.production_days != null
                ? policy.production_days
                : (policy.production_days_base != null ? policy.production_days_base : 5));
        int lead = baseLead + policy.buffer_days;
        int moq = item.moq != null ? item.moq : (policy.moq != null ? policy.moq : 1);
        String code = item.sku;
        String name = item.name != null ? item.name : item.sku;

        // 价目接口只回挂牌价；满量折扣不在此改单价（由议价 settle / PromoEngine 披露）
        Map<String, Object> lineMeta = PromoEngine.applyLineQty(policy, code, quantity, listUnit);

        // 无私下底价：unit_price 恒为挂牌价；真实让利只走 promotions（议价轮）
        out.put("sku", code);
        out.put("name", name);
        out.put("list_unit_price", listUnit);
        out.put("unit_price", listUnit);
        out.put("floor_price", round2(listUnit));
        out.put("currency", "CNY");
        out.put("tax_included", policy.default_tax_included);
        out.put("available_quantity", avail);
        out.put("lead_time_days", lead);
        out.put("moq", moq);
        out.put("strategy_tag", policy.strategy_tag != null ? policy.strategy_tag : "price-first");
        out.put("can_fulfill", avail >= quantity);
        // 不放入回执主字段；仅内部对照，避免初询泄优惠
        out.put("_line_qty_eligible", lineMeta);
        out.put("catalog_hit", true);
        out.put("pricing_mode", "list_price_only");
        Map<String, Object> physical = physicalSpecs(code, quantity);
        if (physical != null) {
            out.put("physical_specs", physical);
            out.put("pack_cm", physical.get("pack_cm"));
            out.put("volume_m3_unit", physical.get("volume_m3_unit"));
            out.put("volume_m3", physical.get("volume_m3"));
            out.put("kg_per_unit", physical.get("kg_per_unit"));
            out.put("weight_kg", physical.get("weight_kg"));
            out.put("charge_class", physical.get("charge_class"));
            out.put("unit", physical.get("unit"));
            out.put("note", physical.get("note"));
        }
        return out;
    }

    /** 与 commerce.seat_catalog 对齐的物理规格（初询必须带回，避免「未收到规格」）。 */
    public static Map<String, Object> physicalSpecs(String sku, int qty) {
        if (sku == null || sku.isBlank()) {
            return null;
        }
        String code = sku.toUpperCase(Locale.ROOT);
        double volUnit;
        double kgUnit;
        String pack;
        String unit;
        String charge;
        String note;
        switch (code) {
            case "RM-CASTER-300" -> {
                volUnit = 0.005; kgUnit = 0.4; pack = "25x20x10"; unit = "只";
                charge = "heavy"; note = "按单只计；BOM 每椅 5 只";
            }
            case "RM-CASTER-200" -> {
                volUnit = 0.005; kgUnit = 0.35; pack = "25x20x10"; unit = "只";
                charge = "heavy"; note = "按单只计；BOM 每椅 5 只";
            }
            case "RM-ARMREST" -> {
                volUnit = 0.018; kgUnit = 2.8; pack = "40x30x15"; unit = "对";
                charge = "heavy"; note = "一对装纸箱";
            }
            case "RM-BASE-NYLON" -> {
                volUnit = 0.0735; kgUnit = 4.5; pack = "70x70x15"; unit = "个";
                charge = "heavy"; note = "伞状拆解平放装";
            }
            case "RM-GASLIFT" -> {
                volUnit = 0.0045; kgUnit = 1.2; pack = "45x10x10"; unit = "根";
                charge = "heavy"; note = "纸筒或扁盒装";
            }
            case "RM-TUBE-STEEL" -> {
                volUnit = 0.048; kgUnit = 6.5; pack = "80x40x15"; unit = "套";
                charge = "heavy"; note = "防刮擦拆装打包";
            }
            case "RM-FOAM-MEM" -> {
                volUnit = 0.045; kgUnit = 1.8; pack = "55x55x15"; unit = "块";
                charge = "bulky"; note = "含木板，防尘袋装";
            }
            case "RM-FOAM-STD" -> {
                volUnit = 0.045; kgUnit = 1.5; pack = "55x55x15"; unit = "块";
                charge = "bulky"; note = "含木板，防尘袋装";
            }
            case "RM-FABRIC-PRO", "RM-FABRIC-STD" -> {
                volUnit = 0.012; kgUnit = 0.8; pack = "40x30x10"; unit = "套";
                charge = "light"; note = "卷装";
            }
            default -> {
                return null;
            }
        }
        int q = Math.max(qty, 1);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("sku", code);
        out.put("unit", unit);
        out.put("pack_cm", pack);
        out.put("volume_m3_unit", volUnit);
        out.put("volume_m3", round2(volUnit * q));
        out.put("kg_per_unit", kgUnit);
        out.put("weight_kg", round2(kgUnit * q));
        out.put("charge_class", charge);
        out.put("note", note);
        return out;
    }

    public static double round2(double v) {
        return Math.round(v * 100.0) / 100.0;
    }
}
