package com.agentlink.supplier.aip;

import com.agentlink.supplier.pipeline.PipelineOutcome;
import com.agentlink.supplier.pipeline.QuotePipeline;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
public class AipRpcController {
    private final QuotePipeline pipeline;
    private final String aic;
    private final String agentId;
    private final ObjectMapper mapper;

    public AipRpcController(QuotePipeline pipeline, String aic, String agentId, ObjectMapper mapper) {
        this.pipeline = pipeline;
        this.aic = aic;
        this.agentId = agentId;
        this.mapper = mapper;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok", "aic", aic, "agent_id", agentId, "runtime", "java");
    }

    @PostMapping(value = "/rpc", consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
    public AipModels.RpcResponse rpc(@RequestBody AipModels.RpcRequest req) {
        AipModels.RpcResponse resp = new AipModels.RpcResponse();
        resp.id = req.id;
        try {
            if (req.params == null || req.params.command == null) {
                resp.error = err(-32602, "missing params.command");
                return resp;
            }
            AipModels.TaskCommand cmd = req.params.command;
            String command = cmd.command == null ? "" : cmd.command;
            if ("get".equalsIgnoreCase(command) || "cancel".equalsIgnoreCase(command) || "complete".equalsIgnoreCase(command)) {
                resp.result = stubResult(cmd, "completed", null, null);
                return resp;
            }
            JsonNode envelope = extractEnvelope(cmd);
            if (envelope == null) {
                resp.result = stubResult(cmd, "awaiting-input", "请提供 StructuredDataItem 业务信封", null);
                return resp;
            }
            PipelineOutcome out = pipeline.handle(envelope);
            if ("awaiting-input".equals(out.aipState()) || "rejected".equals(out.aipState()) || "failed".equals(out.aipState())) {
                resp.result = stubResult(cmd, out.aipState(), out.message(), null);
                return resp;
            }
            resp.result = stubResult(cmd, "awaiting-completion", null, out);
            return resp;
        } catch (Exception e) {
            resp.error = err(-32000, e.getMessage() == null ? e.toString() : e.getMessage());
            return resp;
        }
    }

    private JsonNode extractEnvelope(AipModels.TaskCommand cmd) {
        if (cmd.dataItems == null) {
            return null;
        }
        for (AipModels.DataItem item : cmd.dataItems) {
            if (item == null) {
                continue;
            }
            if ("data".equals(item.type) && item.data != null) {
                return item.data;
            }
        }
        return null;
    }

    private AipModels.TaskResult stubResult(
            AipModels.TaskCommand cmd, String state, String textMsg, PipelineOutcome out
    ) {
        String taskId = cmd.taskId != null ? cmd.taskId : "task-" + UUID.randomUUID().toString().substring(0, 8);
        AipModels.TaskResult tr = new AipModels.TaskResult();
        tr.id = "msg-" + UUID.randomUUID().toString().substring(0, 8);
        tr.sentAt = Instant.now().toString();
        tr.senderId = aic;
        tr.senderRole = "partner";
        tr.sessionId = cmd.sessionId;
        tr.taskId = taskId;
        AipModels.TaskStatus st = new AipModels.TaskStatus();
        st.state = state;
        st.stateChangedAt = Instant.now().toString();
        if (textMsg != null) {
            AipModels.DataItem ti = new AipModels.DataItem();
            ti.type = "text";
            ti.text = textMsg;
            st.dataItems = List.of(ti);
        }
        tr.status = st;
        if (out != null && out.envelope() != null) {
            AipModels.Product p = new AipModels.Product();
            p.id = "product-" + taskId;
            p.name = out.productName();
            p.description = agentId + " structured product";
            AipModels.DataItem di = new AipModels.DataItem();
            di.type = "data";
            di.data = mapper.valueToTree(out.envelope());
            p.dataItems = List.of(di);
            tr.products = List.of(p);
        }
        return tr;
    }

    private static AipModels.RpcError err(int code, String msg) {
        AipModels.RpcError e = new AipModels.RpcError();
        e.code = code;
        e.message = msg;
        return e;
    }
}
