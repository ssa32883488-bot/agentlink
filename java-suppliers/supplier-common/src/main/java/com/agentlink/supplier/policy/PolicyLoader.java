package com.agentlink.supplier.policy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import org.springframework.core.io.ClassPathResource;

import java.io.InputStream;

public final class PolicyLoader {
    private static final ObjectMapper YAML = new ObjectMapper(new YAMLFactory());

    private PolicyLoader() {}

    public static SupplierPolicy loadClasspath(String resourcePath) {
        try (InputStream in = new ClassPathResource(resourcePath).getInputStream()) {
            return YAML.readValue(in, SupplierPolicy.class);
        } catch (Exception e) {
            throw new IllegalStateException("Failed to load policy: " + resourcePath, e);
        }
    }
}
