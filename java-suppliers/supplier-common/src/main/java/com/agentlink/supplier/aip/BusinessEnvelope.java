package com.agentlink.supplier.aip;

import com.fasterxml.jackson.databind.JsonNode;

import java.util.LinkedHashMap;
import java.util.Map;

public record BusinessEnvelope(String schemaType, String schemaVersion, String businessId, JsonNode payload) {

    public static Map<String, Object> wrap(String schemaType, String businessId, Map<String, Object> payload) {
        Map<String, Object> env = new LinkedHashMap<>();
        env.put("schema_type", schemaType);
        env.put("schema_version", "1.0");
        env.put("business_id", businessId);
        env.put("payload", payload);
        return env;
    }
}
