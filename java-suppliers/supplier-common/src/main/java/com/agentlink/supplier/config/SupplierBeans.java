package com.agentlink.supplier.config;

import com.agentlink.supplier.ai.BargainNarrator;
import com.agentlink.supplier.aip.AipRpcController;
import com.agentlink.supplier.aip.ErpProxyController;
import com.agentlink.supplier.pipeline.QuotePipeline;
import com.agentlink.supplier.policy.PolicyLoader;
import com.agentlink.supplier.policy.SupplierPolicy;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SupplierBeans {

    @Bean
    SupplierPolicy supplierPolicy(@Value("${agentlink.policy-resource}") String resource) {
        return PolicyLoader.loadClasspath(resource);
    }

    @Bean
    BargainNarrator bargainNarrator() {
        return new BargainNarrator();
    }

    @Bean
    QuotePipeline quotePipeline(
            SupplierPolicy policy,
            BargainNarrator narrator,
            @Value("${agentlink.agent-id}") String agentId
    ) {
        return new QuotePipeline(policy, agentId, narrator);
    }

    @Bean
    AipRpcController aipRpcController(
            QuotePipeline pipeline,
            @Value("${agentlink.aic}") String aic,
            @Value("${agentlink.agent-id}") String agentId,
            ObjectMapper mapper
    ) {
        return new AipRpcController(pipeline, aic, agentId, mapper);
    }

    @Bean
    ErpProxyController erpProxyController(
            @Value("${agentlink.erp-upstream:}") String upstream
    ) {
        return new ErpProxyController(upstream);
    }
}
