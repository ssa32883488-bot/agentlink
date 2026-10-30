package com.agentlink.supplier.pricing;

import com.agentlink.supplier.policy.SupplierPolicy;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class PromoEngine {
    private PromoEngine() {}

    public static Map<String, Object> applyLineQty(SupplierPolicy policy, String sku, int qty, double listUnit) {
        if (policy.promotions == null || policy.promotions.line_qty_discount == null) {
            return null;
        }
        String code = sku == null ? "" : sku.toUpperCase(Locale.ROOT);
        Map<String, Object> best = null;
        double bestUnit = listUnit;
        for (var tier : policy.promotions.line_qty_discount) {
            boolean hit = false;
            for (String s : tier.skus) {
                if (code.equalsIgnoreCase(s)) {
                    hit = true;
                    break;
                }
            }
            if (!hit || qty < tier.threshold_qty) {
                continue;
            }
            double cand = CatalogPricer.round2(listUnit * (1.0 - tier.discount_pct));
            if (cand < bestUnit) {
                bestUnit = cand;
                best = new LinkedHashMap<>();
                best.put("label", tier.label);
                best.put("threshold_qty", tier.threshold_qty);
                best.put("discount_pct", tier.discount_pct);
                best.put("applied", true);
                best.put("list_unit", listUnit);
                best.put("unit_after", cand);
                best.put("save_per_unit", CatalogPricer.round2(listUnit - cand));
            }
        }
        return best;
    }

    public static Map<String, Object> settle(
            SupplierPolicy policy,
            int qty,
            double unitPrice,
            Double freight,
            String destProvince,
            String sku
    ) {
        String code = CatalogPricer.normalizeSku(sku);
        if (code == null) {
            code = policy.default_sku;
        }
        double listUnit = unitPrice;
        var item = CatalogPricer.resolve(policy, null, code, null);
        if (item != null) {
            listUnit = item.unit_price;
        }
        var line = applyLineQty(policy, code, qty, listUnit);
        double unit = line != null ? ((Number) line.get("unit_after")).doubleValue() : unitPrice;
        double goods = CatalogPricer.round2(unit * qty);
        double lineSave = line != null ? CatalogPricer.round2(listUnit * qty - goods) : 0;

        double fullSave = 0;
        Map<String, Object> fullTier = null;
        if (policy.promotions != null) {
            for (var t : policy.promotions.full_reduction) {
                boolean ok = true;
                if (t.threshold_amount != null) {
                    ok = goods >= t.threshold_amount;
                }
                if (t.threshold_qty != null) {
                    ok = ok && qty >= t.threshold_qty;
                }
                if (!ok) {
                    continue;
                }
                double save = t.reduce_amount != null
                        ? t.reduce_amount
                        : (t.reduce_pct != null ? CatalogPricer.round2(goods * t.reduce_pct) : 0);
                if (save >= fullSave) {
                    fullSave = save;
                    fullTier = new LinkedHashMap<>();
                    fullTier.put("label", t.label);
                    fullTier.put("reduce_amount", t.reduce_amount);
                }
            }
        }
        double goodsAfter = CatalogPricer.round2(Math.max(0, goods - fullSave));

        Map<String, Object> sub = applyCrossProvince(policy, qty, freight, destProvince);
        Double freightAfter = freight;
        if (sub.get("freight_after") instanceof Number n) {
            freightAfter = n.doubleValue();
        }
        double tco = goodsAfter + (freightAfter != null ? freightAfter : 0);

        List<String> hints = new ArrayList<>();
        if (policy.promotions != null) {
            for (var t : policy.promotions.line_qty_discount) {
                hints.add(t.label + " / 满" + t.threshold_qty + "件 / 减" + Math.round(t.discount_pct * 100) + "%");
            }
            for (var t : policy.promotions.full_reduction) {
                StringBuilder b = new StringBuilder(t.label != null ? t.label : "满减");
                if (t.threshold_amount != null) {
                    b.append(" / 满货价").append(t.threshold_amount.intValue());
                }
                if (t.reduce_amount != null) {
                    b.append(" / 减").append(t.reduce_amount.intValue());
                }
                hints.add(b.toString());
            }
            if (policy.promotions.cross_province_subsidy != null && policy.promotions.cross_province_subsidy.enabled) {
                var cfg = policy.promotions.cross_province_subsidy;
                hints.add((cfg.label != null ? cfg.label : "跨省运费补贴") + (cfg.uncertain ? "（审核不确定）" : ""));
            }
        }

        Map<String, Object> nextTier = nextLineQtyGap(policy, code, qty, listUnit);

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("quantity", qty);
        out.put("sku", code);
        out.put("unit_price", unit);
        out.put("list_unit_price", listUnit);
        out.put("goods_total", goods);
        out.put("line_qty_discount", line);
        out.put("line_qty_save", lineSave);
        out.put("full_reduction", fullTier);
        out.put("full_reduction_save", fullSave);
        out.put("goods_after_promo", goodsAfter);
        out.put("freight", freight);
        out.put("cross_province_subsidy", sub);
        out.put("freight_after_subsidy", freightAfter);
        out.put("tco", CatalogPricer.round2(tco));
        out.put("next_tier", nextTier);
        out.put("policy_hints", hints);
        out.put("dest_province", destProvince);
        return out;
    }

    /** 下一档单品满量折扣（未达门槛时）。 */
    public static Map<String, Object> nextLineQtyGap(
            SupplierPolicy policy, String sku, int qty, double listUnit
    ) {
        if (policy.promotions == null || policy.promotions.line_qty_discount == null) {
            return null;
        }
        String code = sku == null ? "" : sku.toUpperCase(Locale.ROOT);
        Map<String, Object> best = null;
        int bestGap = Integer.MAX_VALUE;
        for (var tier : policy.promotions.line_qty_discount) {
            boolean hit = code.isEmpty();
            for (String s : tier.skus) {
                if (code.equalsIgnoreCase(s)) {
                    hit = true;
                    break;
                }
            }
            if (!hit) {
                continue;
            }
            int need = tier.threshold_qty;
            if (qty >= need) {
                continue;
            }
            int gap = need - qty;
            double discUnit = CatalogPricer.round2(listUnit * (1.0 - tier.discount_pct));
            double goodsNow = CatalogPricer.round2(listUnit * qty);
            double goodsAt = CatalogPricer.round2(discUnit * need);
            double saveVsList = CatalogPricer.round2(listUnit * need - goodsAt);
            double net = CatalogPricer.round2(goodsAt - goodsNow);
            if (gap < bestGap) {
                bestGap = gap;
                Map<String, Object> tierMap = new LinkedHashMap<>();
                tierMap.put("kind", "line_qty_discount");
                tierMap.put("label", tier.label);
                tierMap.put("threshold_qty", tier.threshold_qty);
                tierMap.put("discount_pct", tier.discount_pct);
                best = new LinkedHashMap<>();
                best.put("tier", tierMap);
                best.put("target_qty", need);
                best.put("qty_gap", gap);
                best.put("extra_goods_spend", CatalogPricer.round2(listUnit * gap));
                best.put("promo_save", saveVsList);
                best.put("net_extra_spend", net);
                best.put(
                        "hint",
                        "加购 " + gap + " 件可达「" + tier.label + "」，折后单价约 "
                                + discUnit + "（目录价 " + listUnit + "）"
                );
            }
        }
        return best;
    }

    static Map<String, Object> applyCrossProvince(
            SupplierPolicy policy, int qty, Double freight, String destProvince
    ) {
        Map<String, Object> base = new LinkedHashMap<>();
        base.put("eligible", false);
        base.put("applied", false);
        base.put("uncertain", false);
        base.put("subsidy_amount", 0.0);
        base.put("freight_after", freight);
        base.put("note", null);
        if (policy.promotions == null || policy.promotions.cross_province_subsidy == null
                || !policy.promotions.cross_province_subsidy.enabled || freight == null) {
            return base;
        }
        var cfg = policy.promotions.cross_province_subsidy;
        String origin = cfg.origin_province;
        if (origin == null && policy.merchant != null) {
            Object p = policy.merchant.get("province");
            origin = p == null ? null : String.valueOf(p);
        }
        String dest = destProvince == null ? "" : destProvince.trim();
        if (origin == null || dest.isEmpty() || origin.equals(dest)) {
            base.put("note", "收货省与发货省相同，不适用跨省补贴");
            return base;
        }
        if (qty < cfg.min_qty) {
            base.put("eligible", true);
            base.put("uncertain", cfg.uncertain);
            base.put("note", "跨省补贴需满 " + cfg.min_qty + " 件（当前 " + qty + "）");
            return base;
        }
        double subsidy = CatalogPricer.round2(Math.min(freight, freight * cfg.subsidy_pct_of_freight));
        base.put("eligible", true);
        base.put("applied", subsidy > 0);
        base.put("uncertain", cfg.uncertain);
        base.put("subsidy_amount", subsidy);
        base.put("freight_after", CatalogPricer.round2(freight - subsidy));
        base.put("note", cfg.note != null ? cfg.note : origin + "→" + dest + " 跨省运费补贴");
        base.put("origin_province", origin);
        base.put("dest_province", dest);
        return base;
    }

    /** 已取消私下底价/让价：单价不因议价轮次下调；优惠只走 promotions。 */
    public static double goodwillUnit(SupplierPolicy policy, double previous, int qty) {
        return CatalogPricer.round2(previous);
    }

    /** 采购议价可挖空间：已触发优惠 + 下一档可达节省 + 跨省补贴（若有）。 */
    @SuppressWarnings("unchecked")
    public static double promoLeverage(Map<String, Object> economics) {
        double room = num(economics.get("line_qty_save")) + num(economics.get("full_reduction_save"));
        Object gap = economics.get("next_tier");
        if (gap instanceof Map<?, ?> g) {
            room += num(g.get("promo_save"));
        }
        Object sub = economics.get("cross_province_subsidy");
        if (sub instanceof Map<?, ?> s) {
            room += num(s.get("subsidy_amount"));
        }
        return CatalogPricer.round2(Math.max(0.0, room));
    }

    private static double num(Object v) {
        if (v instanceof Number n) {
            return n.doubleValue();
        }
        return 0.0;
    }
}
