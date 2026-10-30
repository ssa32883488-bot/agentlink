package com.agentlink.supplier.pipeline;

import com.agentlink.supplier.aip.BusinessEnvelope;
import com.agentlink.supplier.ai.BargainNarrator;
import com.agentlink.supplier.policy.SupplierPolicy;
import com.agentlink.supplier.pricing.CatalogPricer;
import com.agentlink.supplier.pricing.PromoEngine;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public class QuotePipeline {
    private final SupplierPolicy policy;
    private final String agentId;
    private final BargainNarrator narrator;
    private final ObjectMapper mapper = new ObjectMapper();

    public QuotePipeline(SupplierPolicy policy, String agentId, BargainNarrator narrator) {
        this.policy = policy;
        this.agentId = agentId;
        this.narrator = narrator;
    }

    public PipelineOutcome handle(JsonNode envelope) {
        String schema = text(envelope, "schema_type");
        String businessId = text(envelope, "business_id");
        JsonNode payload = envelope.get("payload");
        if (payload == null || payload.isNull()) {
            return PipelineOutcome.awaitingInput("missing payload");
        }

        if ("agentlink.bargain_round".equals(schema)) {
            return bargain(businessId, payload);
        }
        if ("agentlink.blind_bid".equals(schema)) {
            return blindBid(businessId, payload);
        }
        if ("agentlink.contract_ack".equals(schema)) {
            return contractAck(businessId, payload);
        }
        if (!"agentlink.quote_request".equals(schema)) {
            return PipelineOutcome.rejected("unexpected schema_type=" + schema);
        }
        return initialQuote(businessId, payload);
    }

    private PipelineOutcome initialQuote(String businessId, JsonNode payload) {
        for (String k : List.of("purchase_request_id", "quantity", "product_name", "specifications")) {
            if (!payload.has(k) || payload.get(k).isNull()) {
                return PipelineOutcome.awaitingInput("missing fields: " + k);
            }
        }
        int qty = payload.get("quantity").asInt();
        String productName = payload.get("product_name").asText();
        Map<String, Object> specs = mapper.convertValue(payload.get("specifications"), Map.class);
        String sku = payload.has("sku") ? payload.get("sku").asText(null) : null;

        // 先校验目录命中：无此物料一律拒报，禁止再用默认 SKU 冒充
        Map<String, Object> priced = CatalogPricer.quote(policy, qty, productName, sku, specs);
        if (!Boolean.TRUE.equals(priced.get("catalog_hit"))) {
            Object reason = priced.get("reject_reason");
            return PipelineOutcome.rejected(
                    reason != null ? String.valueOf(reason) : ("本厂目录无此物料，无法报价: " + productName));
        }

        if (policy.min_custom_fields != null && !policy.min_custom_fields.isEmpty()) {
            List<String> miss = new ArrayList<>();
            for (String f : policy.min_custom_fields) {
                Object v = specs.get(f);
                if (v == null || String.valueOf(v).isBlank()) {
                    miss.add(f);
                }
            }
            if (!miss.isEmpty()) {
                return PipelineOutcome.awaitingInput("custom spec incomplete, need: " + String.join(", ", miss));
            }
        }

        int moq = ((Number) priced.get("moq")).intValue();
        if (qty < moq) {
            return PipelineOutcome.rejected("below MOQ: need>=" + moq + ", got " + qty);
        }

        boolean can = Boolean.TRUE.equals(priced.get("can_fulfill"));
        List<Map<String, Object>> alternatives = new ArrayList<>();
        List<Map<String, Object>> split = null;
        if (!can && "scarce-substitute".equals(policy.strategy_tag)) {
            for (var alt : policy.substitutes) {
                int aAvail = ((Number) alt.getOrDefault("available_quantity", 0)).intValue();
                if (aAvail >= qty) {
                    alternatives.add(alt);
                }
            }
            int avail = ((Number) priced.get("available_quantity")).intValue();
            if (avail > 0) {
                List<Integer> days = policy.split_batch_days;
                split = List.of(
                        Map.of("quantity", avail, "eta_days", days.get(0)),
                        Map.of("quantity", qty - avail, "eta_days", days.size() > 1 ? days.get(1) : days.get(0) + 7)
                );
            }
            if (alternatives.isEmpty() && split == null) {
                return PipelineOutcome.rejected(
                        "insufficient inventory and no substitute: need " + qty + ", have " + avail);
            }
        } else if (!can) {
            return PipelineOutcome.rejected(
                    "insufficient inventory: need " + qty + ", have " + priced.get("available_quantity"));
        }

        // 初询不结算/不披露 promotions：只回挂牌价 + 产品规格
        Map<String, Object> quote = new LinkedHashMap<>();
        quote.put("quote_id", "quote-java-" + UUID.randomUUID().toString().substring(0, 8));
        quote.put("purchase_request_id", payload.get("purchase_request_id").asText());
        quote.put("supplier_agent_id", agentId);
        quote.put("version", 1);
        quote.put("status", "initial_quote");
        Map<String, Object> product = new LinkedHashMap<>();
        product.put("name", priced.get("name"));
        product.put("sku", priced.get("sku"));
        product.put("specification", specs);
        product.put("quantity", qty);
        // 物理规格（若价目侧带回）
        if (priced.get("pack_cm") != null) product.put("pack_cm", priced.get("pack_cm"));
        if (priced.get("volume_m3") != null) product.put("volume_m3", priced.get("volume_m3"));
        if (priced.get("weight_kg") != null) product.put("weight_kg", priced.get("weight_kg"));
        if (priced.get("kg_per_unit") != null) product.put("kg_per_unit", priced.get("kg_per_unit"));
        if (priced.get("physical_specs") != null) product.put("specs", priced.get("physical_specs"));
        quote.put("product", product);
        quote.put("sku", priced.get("sku"));
        quote.put("product_name", priced.get("name"));
        quote.put("unit_price", priced.get("unit_price"));
        quote.put("currency", "CNY");
        quote.put("tax_included", priced.get("tax_included"));
        quote.put("available_quantity", priced.get("available_quantity"));
        quote.put("lead_time_days", priced.get("lead_time_days"));
        quote.put("shipping_cost", null);
        quote.put("valid_until", Instant.now().plus(24, ChronoUnit.HOURS).toString());
        quote.put("conditions", List.of());
        quote.put("strategy_tag", priced.get("strategy_tag"));
        quote.put("bargain_room", null);
        quote.put("policy", null);
        quote.put("promotions_disclosed", false);
        quote.put("negotiation_style", "list_price_first");
        quote.put("pricing_mode", "list_price_only");
        quote.put("note", "初询仅挂牌价与产品规格；优惠政策请议价时再询");
        quote.put("runtime", "java-langchain4j");
        if (priced.get("volume_m3") != null) quote.put("volume_m3", priced.get("volume_m3"));
        if (priced.get("weight_kg") != null) quote.put("weight_kg", priced.get("weight_kg"));
        if (!alternatives.isEmpty()) {
            quote.put("alternatives", alternatives);
        }
        if (split != null) {
            quote.put("split_fulfillment_plan", split);
            quote.put("can_fulfill_full", false);
        }

        return PipelineOutcome.ok(
                "initial_quote",
                BusinessEnvelope.wrap("agentlink.initial_quote", businessId, quote)
        );
    }

    private PipelineOutcome bargain(String businessId, JsonNode payload) {
        int reqQty = payload.path("quantity").asInt(1);
        String productName = payload.path("product_name").asText(null);
        String skuHint = payload.hasNonNull("sku") ? payload.get("sku").asText(null) : null;
        Map<String, Object> specs = payload.has("specifications")
                ? mapper.convertValue(payload.get("specifications"), Map.class)
                : Map.of();
        Map<String, Object> priced = CatalogPricer.quote(policy, reqQty, productName, skuHint, specs);
        if (!Boolean.TRUE.equals(priced.get("catalog_hit"))) {
            Object reason = priced.get("reject_reason");
            return PipelineOutcome.rejected(
                    reason != null ? String.valueOf(reason) : ("本厂目录无此物料，无法议价: " + productName));
        }
        int avail = ((Number) priced.get("available_quantity")).intValue();
        int qty = avail > 0 ? Math.min(reqQty, avail) : reqQty;
        double prev = payload.has("previous_unit_price") && !payload.get("previous_unit_price").isNull()
                ? payload.get("previous_unit_price").asDouble()
                : ((Number) priced.get("unit_price")).doubleValue();
        double unit = PromoEngine.goodwillUnit(policy, prev, qty);
        String destProvince = destProvince(payload);
        Map<String, Object> econ = PromoEngine.settle(
                policy, qty, unit, null, destProvince, String.valueOf(priced.get("sku")));
        String goal = payload.path("goal_text").asText("优化综合成本");
        Map<String, Object> narrative = narrator.narrate(policy, econ, goal);

        // 凑门槛对照（议价才披露）
        Map<String, Object> reachExample = null;
        Object nextTierObj = econ.get("next_tier");
        if (nextTierObj instanceof Map<?, ?> gapRaw) {
            @SuppressWarnings("unchecked")
            Map<String, Object> gap = (Map<String, Object>) gapRaw;
            Object tq = gap.get("target_qty");
            if (tq instanceof Number targetQtyNum) {
                int targetQty = targetQtyNum.intValue();
                Map<String, Object> altEcon = PromoEngine.settle(
                        policy, targetQty, unit, null, destProvince, String.valueOf(priced.get("sku")));
                reachExample = new LinkedHashMap<>();
                reachExample.put("target_qty", targetQty);
                double listUnit = num(altEcon.get("list_unit_price"), unit);
                reachExample.put("list_goods_total", CatalogPricer.round2(listUnit * targetQty));
                reachExample.put("goods_after_promo", altEcon.get("goods_after_promo"));
                reachExample.put("unit_after_promo", altEcon.get("unit_price"));
                reachExample.put("hint", gap.get("hint"));
                Object tier = gap.get("tier");
                if (tier instanceof Map<?, ?> tm && tm.get("label") != null) {
                    reachExample.put("label", tm.get("label"));
                }
            }
        }

        Map<String, Object> policyPublic = new LinkedHashMap<>();
        policyPublic.put("disclosed", true);
        policyPublic.put("hints", narrative.get("policy_hints"));
        policyPublic.put("talk_track", narrative.get("talk_track"));
        policyPublic.put("next_tier", econ.get("next_tier"));
        policyPublic.put("reach_example", reachExample);
        Map<String, Object> applied = new LinkedHashMap<>();
        applied.put("line_qty_save", econ.get("line_qty_save"));
        applied.put("full_reduction_save", econ.get("full_reduction_save"));
        applied.put("goods_after_promo", econ.get("goods_after_promo"));
        policyPublic.put("applied", applied);

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("quote_id", "quote-neg-" + UUID.randomUUID().toString().substring(0, 8));
        out.put("supplier_agent_id", agentId);
        out.put("status", "bargain_offer");
        out.put("unit_price", unit);
        out.put("currency", "CNY");
        out.put("tax_included", true);
        out.put("lead_time_days", priced.get("lead_time_days"));
        out.put("available_quantity", priced.get("available_quantity"));
        out.put("bargain_room", PromoEngine.promoLeverage(econ));
        Map<String, Object> product = new LinkedHashMap<>();
        product.put("name", priced.get("name"));
        product.put("sku", priced.get("sku"));
        product.put("quantity", qty);
        product.put("requested_quantity", reqQty);
        out.put("product", product);
        out.put("goods_total", econ.get("goods_total"));
        out.put("full_reduction_save", econ.get("full_reduction_save"));
        out.put("goods_after_promo", econ.get("goods_after_promo"));
        out.put("promo_settlement", econ);
        out.put("policy", policyPublic);
        out.put("policy_hints", narrative.get("policy_hints"));
        out.put("talk_track", narrative.get("talk_track"));
        out.put("counter_options", narrative.get("counter_options"));
        out.put("reach_promo_preview", reachExample);
        out.put("promotions_disclosed", true);
        out.put("negotiation_style", "threshold_trade_not_pure_cut");
        out.put("pricing_mode", "list_plus_promo_only");
        out.put("note", "无私下底价；议价只走活动门槛与补贴路径；不索取买方预算");
        out.put("runtime", "java-langchain4j");
        out.put("valid_until", Instant.now().plus(12, ChronoUnit.HOURS).toString());
        return PipelineOutcome.ok(
                "bargain_offer",
                BusinessEnvelope.wrap("agentlink.bargain_offer", businessId, out)
        );
    }

    private static double num(Object v, double fallback) {
        if (v instanceof Number n) return n.doubleValue();
        return fallback;
    }

    private PipelineOutcome blindBid(String businessId, JsonNode payload) {
        int qty = payload.path("quantity").asInt(1);
        String bidProduct = payload.path("product_name").asText(null);
        Map<String, Object> priced = CatalogPricer.quote(policy, qty, bidProduct, null, Map.of());
        if (!Boolean.TRUE.equals(priced.get("catalog_hit"))) {
            Object reason = priced.get("reject_reason");
            return PipelineOutcome.rejected(
                    reason != null ? String.valueOf(reason) : ("本厂目录无此物料，无法竞价: " + bidProduct));
        }
        // 竞价亦不砍挂牌价；优惠只结算 promotions
        double bid = CatalogPricer.round2(((Number) priced.get("unit_price")).doubleValue());
        Map<String, Object> econ = PromoEngine.settle(
                policy, qty, bid, null, destProvince(payload), String.valueOf(priced.get("sku")));
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("bid_id", "bid-" + UUID.randomUUID().toString().substring(0, 8));
        out.put("auction_id", payload.path("auction_id").asText(null));
        out.put("supplier_agent_id", agentId);
        out.put("unit_price", bid);
        out.put("currency", "CNY");
        out.put("lead_time_days", priced.get("lead_time_days"));
        out.put("sealed", true);
        out.put("policy_hints", econ.get("policy_hints"));
        out.put("runtime", "java-langchain4j");
        out.put("valid_until", Instant.now().plus(6, ChronoUnit.HOURS).toString());
        return PipelineOutcome.ok(
                "blind_bid",
                BusinessEnvelope.wrap("agentlink.blind_bid_offer", businessId, out)
        );
    }

    private PipelineOutcome contractAck(String businessId, JsonNode payload) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("contract_id", payload.path("contract_id").asText(null));
        out.put("party", "supplier");
        out.put("action", "confirmed");
        out.put("supplier_agent_id", agentId);
        out.put("confirmed_at", Instant.now().toString());
        out.put("note", "Java 供应侧演示自动确认");
        out.put("runtime", "java-langchain4j");
        return PipelineOutcome.ok(
                "contract_ack",
                BusinessEnvelope.wrap("agentlink.contract_ack_result", businessId, out)
        );
    }

    private static String destProvince(JsonNode payload) {
        if (payload.hasNonNull("dest_province")) {
            return payload.get("dest_province").asText();
        }
        JsonNode dest = payload.get("destination");
        if (dest != null && dest.hasNonNull("province")) {
            return dest.get("province").asText();
        }
        return "河北";
    }

    private static String text(JsonNode n, String field) {
        return n != null && n.has(field) && !n.get(field).isNull() ? n.get(field).asText() : "";
    }
}
