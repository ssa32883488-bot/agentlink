package com.agentlink.supplier.ai;

import com.agentlink.supplier.policy.SupplierPolicy;
import dev.langchain4j.model.chat.ChatLanguageModel;
import dev.langchain4j.model.openai.OpenAiChatModel;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * LangChain4j：议价话术必须由 LLM 生成；禁止固定模板话术。
 * 数字与选项仍由规则层提供。
 */
public class BargainNarrator {
    private static final Logger log = LoggerFactory.getLogger(BargainNarrator.class);
    private final ChatLanguageModel model;

    public BargainNarrator() {
        String key = firstNonBlank(System.getenv("LLM_API_KEY"), System.getenv("OPENAI_API_KEY"));
        String base = firstNonBlank(System.getenv("LLM_BASE_URL"), "https://api.deepseek.com");
        String modelName = firstNonBlank(System.getenv("LLM_MODEL"), "deepseek-chat");
        if (key == null || key.isBlank()) {
            this.model = null;
            log.warn("BargainNarrator: no LLM_API_KEY — talk_track will be empty (no template fallback)");
        } else {
            this.model = OpenAiChatModel.builder()
                    .apiKey(key)
                    .baseUrl(base.endsWith("/") ? base : base + "/")
                    .modelName(modelName)
                    .timeout(Duration.ofSeconds(45))
                    .temperature(0.3)
                    .build();
            log.info("BargainNarrator: LangChain4j OpenAI-compatible model={}", modelName);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> narrate(SupplierPolicy policy, Map<String, Object> economics, String goalText) {
        Object merchantObj = policy.merchant != null ? policy.merchant.get("trade_name") : null;
        String name = merchantObj == null ? "本厂" : String.valueOf(merchantObj);
        List<String> hints = economics.get("policy_hints") instanceof List<?> l
                ? (List<String>) l
                : List.of();

        List<Map<String, Object>> options = new ArrayList<>();
        Map<String, Object> keep = new LinkedHashMap<>();
        keep.put("option_id", "keep_qty");
        keep.put("title", "维持现量");
        keep.put("quantity", economics.get("quantity"));
        keep.put("summary", "挂牌价不变；吃已触发的满减/单品折扣/补贴（若有）");
        options.add(keep);

        Object gap = economics.get("next_tier");
        if (gap instanceof Map<?, ?> g && g.get("target_qty") != null) {
            Map<String, Object> reach = new LinkedHashMap<>();
            reach.put("option_id", "reach_full_reduction");
            reach.put("title", "凑活动门槛");
            reach.put("quantity", g.get("target_qty"));
            reach.put("summary", String.valueOf(g.get("hint") != null ? g.get("hint") : "加量触发优惠"));
            options.add(reach);
        }

        String talk = "";
        if (model != null) {
            try {
                Object next = economics.get("next_tier");
                String facts = "商号:" + name
                        + "\n目标:" + (goalText == null ? "优化综合成本" : goalText)
                        + "\n当前数量:" + economics.get("quantity")
                        + "\n挂牌单价:" + economics.get("list_unit_price")
                        + "\n当前量单品折扣节省:" + economics.get("line_qty_save")
                        + "\n满减节省:" + economics.get("full_reduction_save")
                        + "\n下一档门槛:" + next
                        + "\n跨省补贴:" + economics.get("cross_province_subsidy")
                        + "\n已公示活动:" + hints
                        + "\n说明:本厂无私下底价，挂牌价不议；必须点名已公示活动与凑门槛对照（若有 next_tier）。";
                String polished = model.generate(
                        "你是供应商销售助手。根据事实写一段不超过120字的中文议价话术；"
                                + "若当前量未达门槛，必须说明活动规则，并给出「例如买满 N 件，目录总价 x，优惠后 y」对照；"
                                + "数字只能来自事实，勿编造；勿固定开场白；勿输出「你可以：1/2/3」口令清单。\n"
                                + facts
                );
                if (polished != null && !polished.isBlank()) {
                    talk = polished.trim();
                }
            } catch (Exception e) {
                log.warn("LLM narrate failed: {}", e.toString());
            }
        }

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("talk_track", talk);
        out.put("counter_options", options);
        out.put("policy_hints", hints);
        out.put("negotiation_style", "threshold_trade_not_pure_cut");
        out.put("ai_engine", model == null ? "none" : "langchain4j");
        return out;
    }

    private static String firstNonBlank(String a, String b) {
        if (a != null && !a.isBlank()) {
            return a;
        }
        return b;
    }
}
