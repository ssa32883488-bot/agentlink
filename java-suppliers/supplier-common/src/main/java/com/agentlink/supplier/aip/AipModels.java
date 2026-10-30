package com.agentlink.supplier.aip;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;

import java.util.List;
import java.util.Map;

/** Minimal AIP v2 JSON shapes compatible with Python acps-sdk RPC. */
public final class AipModels {
    private AipModels() {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class RpcRequest {
        public String jsonrpc = "2.0";
        public String method;
        public Object id;
        public RpcParams params;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class RpcParams {
        public TaskCommand command;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class TaskCommand {
        public String type = "task-command";
        public String id;
        public String sentAt;
        public String senderRole;
        public String senderId;
        public String sessionId;
        public String taskId;
        public String command;
        public Map<String, Object> commandParams;
        public List<DataItem> dataItems;
        public String groupId;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class DataItem {
        public String type;
        public String text;
        public JsonNode data;
        public Map<String, Object> metadata;
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class RpcResponse {
        public String jsonrpc = "2.0";
        public Object id;
        public TaskResult result;
        public RpcError error;
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class RpcError {
        public int code;
        public String message;
        public Object data;
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class TaskResult {
        public String type = "task-result";
        public String id;
        public String sentAt;
        public String senderRole = "partner";
        public String senderId;
        public String sessionId;
        public String taskId;
        public TaskStatus status;
        public List<Product> products;
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class TaskStatus {
        public String state;
        public String stateChangedAt;
        public List<DataItem> dataItems;
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class Product {
        public String id;
        public String name;
        public String description;
        public List<DataItem> dataItems;
    }
}
