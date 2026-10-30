package com.agentlink.supplier.policy;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@JsonIgnoreProperties(ignoreUnknown = true)
public class SupplierPolicy {
    public String strategy_tag;
    public String organization;
    public String ship_from_city;
    public double kg_per_unit = 0.4;
    public boolean default_tax_included = true;
    public int buffer_days = 1;
    public Integer production_days;
    public Integer production_days_base;
    public int available_quantity = 0;
    public String default_sku;
    public double base_cost = 30;
    public double markup = 0.12;
    public double bargain_discount = 0.012;
    public double max_unit_concession_pct = 0.012;
    public Integer moq;
    public List<String> min_custom_fields = new ArrayList<>();
    public List<CatalogItem> catalog = new ArrayList<>();
    public Promotions promotions = new Promotions();
    public Map<String, Object> merchant = new HashMap<>();
    public List<Map<String, Object>> substitutes = new ArrayList<>();
    public List<Integer> split_batch_days = List.of(5, 12);

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class CatalogItem {
        public String sku;
        public String name;
        public double unit_price;
        public double floor_price;
        public int available_quantity;
        public int lead_time_days;
        public Integer moq;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Promotions {
        public List<LineQtyDiscount> line_qty_discount = new ArrayList<>();
        public List<FullReduction> full_reduction = new ArrayList<>();
        public CrossProvinceSubsidy cross_province_subsidy;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class LineQtyDiscount {
        public String label;
        public List<String> skus = new ArrayList<>();
        public int threshold_qty;
        public double discount_pct;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class FullReduction {
        public String label;
        public Double threshold_amount;
        public Integer threshold_qty;
        public Double reduce_amount;
        public Double reduce_pct;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class CrossProvinceSubsidy {
        public boolean enabled;
        public String label;
        public String origin_province;
        public int min_qty = 1;
        public double subsidy_pct_of_freight = 0.5;
        public boolean uncertain = true;
        public String note;
    }
}
