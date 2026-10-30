package com.agentlink.supplier.pipeline;

import java.util.Map;

public record PipelineOutcome(
        String aipState,
        String productName,
        Map<String, Object> envelope,
        String message
) {
    public static PipelineOutcome ok(String productName, Map<String, Object> envelope) {
        return new PipelineOutcome("awaiting-completion", productName, envelope, null);
    }

    public static PipelineOutcome awaitingInput(String msg) {
        return new PipelineOutcome("awaiting-input", null, null, msg);
    }

    public static PipelineOutcome rejected(String msg) {
        return new PipelineOutcome("rejected", null, null, msg);
    }
}
