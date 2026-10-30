(() => {
  const S = {
    domain: null,
    agentId: null,
    page: "chat",
    isSupplierDomain: false,
    flowCaseId: null,
    flowCase: null,
    /** 各智能体独立会话态，禁止共用对话窗 */
    flowByAgent: {},
    threadId: null,
    /** 用户主动收起组群聊天室后，轮询不得再强制弹出 */
    groupRoomCollapsed: false,
    groupRoomCollapsedCaseId: null,
  };

  const $ = (id) => document.getElementById(id);

  function agentMeta(id) {
    return (S.domain?.agents || []).find((a) => a.id === (id || S.agentId)) || {};
  }

  function agentTitle(id) {
    return agentMeta(id).title || id || S.agentId || "—";
  }

  function workspaceOf(id) {
    const m = agentMeta(id);
    if (m.workspace) return m.workspace;
    // 供应侧也走对话 ERP
    if ((id || S.agentId || "").startsWith("supplier")) return "chat";
    if ((id || S.agentId || "").startsWith("buyer")) return "chat";
    return "peer";
  }

  function isSupplierAgent(id) {
    return (id || S.agentId || "").startsWith("supplier");
  }

  function saveAgentFlow() {
    if (!S.agentId) return;
    S.flowByAgent[S.agentId] = { flowCaseId: S.flowCaseId, flowCase: S.flowCase };
  }

  function restoreAgentFlow() {
    const snap = S.flowByAgent[S.agentId] || {};
    S.flowCaseId = snap.flowCaseId || null;
    S.flowCase = snap.flowCase || null;
  }

  async function api(path, opts) {
    const r = await fetch(path, opts);
    const t = await r.text();
    let data; try { data = JSON.parse(t); } catch { data = { raw: t }; }
    if (!r.ok) throw Object.assign(new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data)), { data });
    return data;
  }

  function proxy(agentId, path, body, method) {
    const m = method || (body !== undefined ? "POST" : "GET");
    return api(`/api/proxy/${agentId}/${path}`, {
      method: m,
      headers: { "content-type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  }

  function resolveUiRole(agentId, domainId) {
    const id = (agentId || "").toLowerCase();
    const did = (domainId || "").toLowerCase();
    if (id.startsWith("logistics") || did.startsWith("logistics")) return "logistics";
    if (id.startsWith("supplier") || did.startsWith("supplier")) return "supplier";
    if (id.startsWith("buyer") || did.startsWith("buyer")) return "buyer";
    return "buyer";
  }

  function applyRoleTheme(role) {
    const r = role || "buyer";
    document.body.classList.remove("role-buyer", "role-supplier", "role-logistics");
    document.body.classList.add(`role-${r}`);
    const labels = { buyer: "采购商", supplier: "供应商", logistics: "物流" };
    const chip = $("roleChip");
    if (chip) chip.textContent = labels[r] || r;
    S.uiRole = r;
  }

  async function loadDomain() {
    S.domain = await api("/api/domain");
    const did = S.domain.domain_id || "";
    S.isSupplierDomain = did === "supplier-domain" || did.startsWith("supplier-");
    $("domainTitle").textContent = S.domain.domain_title || "智能体控制台";
    $("domainBadge").textContent = did;
    document.title = $("domainTitle").textContent;
    applyRoleTheme(resolveUiRole((S.domain.agents[0] || {}).id, did));

    const mallLink = $("mallLink");
    const ws0 = (S.domain.agents[0] && S.domain.agents[0].workspace) || "";
    const isSupplier = S.isSupplierDomain || (S.domain.agents[0] || {}).id?.startsWith("supplier");
    const isChat = ws0 === "chat" || did.startsWith("buyer-") || did.startsWith("supplier-") || isSupplier;
    if (isSupplier) {
      mallLink.classList.add("hidden");
      document.querySelectorAll(".buyer-only").forEach((el) => el.classList.add("hidden"));
      document.querySelectorAll(".supplier-only").forEach((el) => el.classList.remove("hidden"));
      document.querySelectorAll(".chat-nav").forEach((el) => el.classList.remove("hidden"));
      S.page = "chat";
    } else if (isChat) {
      mallLink.classList.remove("hidden");
      document.querySelectorAll(".buyer-only").forEach((el) => el.classList.remove("hidden"));
      document.querySelectorAll(".supplier-only").forEach((el) => el.classList.add("hidden"));
      document.querySelectorAll(".chat-nav").forEach((el) => el.classList.remove("hidden"));
      S.page = "chat";
    } else {
      mallLink.classList.add("hidden");
      document.querySelectorAll(".buyer-only").forEach((el) => el.classList.add("hidden"));
      document.querySelectorAll(".supplier-only").forEach((el) => el.classList.add("hidden"));
      S.page = "peer";
    }

    renderAgentSwitch();
    S.agentId = S.domain.agents[0].id;
    restoreAgentFlow();
    highlightAgent();
    if (workspaceOf() === "chat") S.page = "chat";
    else if ((S.domain.agents[0] || {}).id === "logistics") S.page = "mailbox";
    else S.page = "mailbox";
    showPage();
    await refreshHealth();
    await refreshConsole();
  }

  function renderAgentSwitch() {
    const box = $("agentSwitch");
    box.innerHTML = "";
    const agents = S.domain.agents || [];
    // 单智能体独立控制台：隐藏聚合切换条
    if (agents.length <= 1) {
      box.classList.add("hidden");
      return;
    }
    box.classList.remove("hidden");
    for (const a of agents) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "as-btn";
      b.dataset.id = a.id;
      b.innerHTML = `<div class="t">${a.title}</div><div class="b">${a.blurb || a.id}</div>`;
      b.onclick = async () => {
        if (S.agentId === a.id) return;
        saveAgentFlow();
        S.agentId = a.id;
        applyRoleTheme(resolveUiRole(a.id, S.domain.domain_id));
        restoreAgentFlow();
        highlightAgent();
        if ($("chatMsgs")) $("chatMsgs").innerHTML = "";
        S.page = workspaceOf(a.id) === "chat" ? "chat" : "peer";
        showPage();
        await refreshConsole();
      };
      box.appendChild(b);
    }
  }

  function highlightAgent() {
    document.querySelectorAll(".as-btn").forEach((el) => {
      el.classList.toggle("active", el.dataset.id === S.agentId);
    });
  }

  function showPage() {
    const who = agentTitle();
    const map = {
      chat: ["pageChat", `${who} · 智能对话`, ""],
      peer: ["pagePeer", `${who} · 工作区`, ""],
      notify: ["pageNotify", `${who} · 通知中心`, ""],
      workbench: ["pageWorkbench", `${who} · 工作台`, ""],
      sales: ["pageSales", `${who} · 销售订单`, ""],
      inventory: ["pageInventory", `${who} · 原料库存`, ""],
      history: ["pageHistory", `${who} · 对话历史`, ""],
      mailbox: ["pageMailbox", `${who} · 邮箱`, ""],
      tickets: ["pageTickets", `${who} · 工单待办`, ""],
      audit: ["pageAudit", `${who} · 回溯审计`, ""],
      catalog: ["pageCatalog", `${who} · 库存与价目`, ""],
      inbox: ["pageInbox", `${who} · 询价箱`, ""],
    };
    const [id, title, sub] = map[S.page] || map.chat;
    document.querySelectorAll(".page").forEach((p) => p.classList.add("hidden"));
    $(id).classList.remove("hidden");
    $("pageTitle").textContent = title;
    $("pageSub").textContent = sub;
    $("pageSub").classList.toggle("hidden", !sub);
    document.querySelectorAll(".nav").forEach((n) => n.classList.toggle("active", n.dataset.page === S.page));
    const chatOn = workspaceOf() === "chat";
    document.querySelectorAll(".chat-nav").forEach((el) => {
      el.classList.toggle("hidden", !chatOn);
    });
    document.querySelectorAll(".buyer-only").forEach((el) => {
      if (isSupplierAgent() || S.isSupplierDomain) {
        el.classList.add("hidden");
        return;
      }
      el.classList.toggle("hidden", !chatOn);
    });
    document.querySelectorAll(".supplier-only").forEach((el) => {
      el.classList.toggle("hidden", !(isSupplierAgent() || S.isSupplierDomain));
    });
    if ($("chatAgentTag")) {
      $("chatAgentTag").textContent = "";
      $("chatAgentTag").classList.add("hidden");
    }
    if (S.page === "peer") renderPeerWorkspace();
  }

  function renderPeerWorkspace() {
    const who = agentTitle();
    $("peerTitle").textContent = `${who} 工作区`;
    $("peerBody").textContent = "";
  }

  async function refreshHealth() {
    const box = $("healthPills");
    box.innerHTML = "";
    for (const a of S.domain.agents) {
      const h = await api(`/api/agents/${a.id}/health`);
      const s = document.createElement("span");
      s.className = "pill " + (h._ui?.online ? "ok" : "down");
      s.textContent = `${a.title}${h._ui?.online ? "·在线" : "·离线"}`;
      box.appendChild(s);
    }
  }

  async function refreshConsole() {
    const office = [loadMailbox(), loadTickets(), loadAudit()];
    if (workspaceOf() === "chat") {
      await loadThreads();
      if (!isSupplierAgent()) await loadFlow();
      const tasks = [loadNotifications(), loadChatHistory(), loadWorkbench(), ...office];
      if (isSupplierAgent() || S.isSupplierDomain) {
        tasks.push(loadCatalog(), loadInbox());
      } else {
        tasks.push(loadSales(), loadInventory());
      }
      await Promise.all(tasks);
    } else {
      renderPeerWorkspace();
      if ($("chatMsgs")) $("chatMsgs").innerHTML = "";
      await Promise.all(office);
    }
    renderRight();
  }

  const FLOW_ORDER = [
    "DRAFT", "DISCOVERING", "SHORTLIST_PENDING", "SOURCING", "COMPARE_PENDING",
    "NEGOTIATING", "NEGOTIATE_REVIEW", "BIDDING", "BID_REVIEW",
    "ORDER_DRAFT", "CONTRACT_PENDING", "ACTIVE",
  ];

  async function loadFlow() {
    const bar = $("chatFlowBar");
    if (!bar) return;
    if (workspaceOf() !== "chat" || isSupplierAgent()) {
      bar.classList.add("hidden");
      return;
    }
    bar.classList.remove("hidden");
    if (!S.flowCaseId) {
      $("flowCaseLabel").textContent = "";
      bar.classList.add("hidden");
      renderFlowSteps(null);
      renderAuctionWatch();
      renderRight();
      return;
    }
    try {
      S.flowCase = await proxy(S.agentId, `api/flow/cases/${S.flowCaseId}`);
      const h = S.flowCase.hitl_pending;
      const phaseTag = h?.phase || h?.gate ? ` · ${h.phase || h.gate}` : "";
      const hitl = h?.prompt;
      const deg = S.flowCase.discovery_meta?.degrade
        ? ` · 发现:${S.flowCase.discovery_meta.source || "容灾"}`
        : S.flowCase.discovery_meta?.source
          ? ` · 发现:${S.flowCase.discovery_meta.source}`
          : "";
      $("flowCaseLabel").textContent = hitl
        ? `${S.flowCase.case_id} · ${S.flowCase.state}${phaseTag}${deg} · 待确认：${hitl}`
        : `${S.flowCase.case_id} · ${S.flowCase.state}${deg}`;
      renderFlowSteps(S.flowCase);
      renderAuctionWatch();
      renderRight();
      renderShortlistDock();
      maybeOpenGroupRoom(S.flowCase);
    } catch (e) {
      $("flowCaseLabel").textContent = `状态同步失败：${e.message || e}`;
    }
  }

  function groupRoomActive(c) {
    if (!c || !c.group_room) return false;
    const st = c.state || "";
    return ["GROUP_BIDDING", "GROUP_DECIDE", "GROUP_LOGISTICS", "GROUP_TICKETS"].includes(st)
      || c.group_room.status === "connecting"
      || c.group_room.status === "review"
      || c.group_room.status === "live";
  }

  function closeGroupRoom() {
    const m = $("groupRoomModal");
    if (m) m.classList.add("hidden");
    S.groupRoomCollapsed = true;
    S.groupRoomCollapsedCaseId = (S.flowCase && S.flowCase.case_id) || S.flowCaseId || null;
    syncGroupRoomReopenChip();
  }

  function openGroupRoomFromChip() {
    S.groupRoomCollapsed = false;
    S.groupRoomCollapsedCaseId = null;
    if (S.flowCase?.group_room) renderGroupRoom(S.flowCase, { show: true });
    syncGroupRoomReopenChip();
  }

  function syncGroupRoomReopenChip() {
    const chip = $("groupRoomReopen");
    if (!chip) return;
    const show = !!(S.groupRoomCollapsed && groupRoomActive(S.flowCase));
    chip.classList.toggle("hidden", !show);
  }

  function maybeOpenGroupRoom(caseObj, { force = false } = {}) {
    const c = caseObj || S.flowCase;
    if ((!c || !groupRoomActive(c)) && !force) {
      syncGroupRoomReopenChip();
      return;
    }
    if (!c?.group_room) {
      syncGroupRoomReopenChip();
      return;
    }
    const cid = c.case_id || S.flowCaseId || null;
    // 新 case 开群：清除上一案的收起标记
    if (cid && S.groupRoomCollapsedCaseId && cid !== S.groupRoomCollapsedCaseId) {
      S.groupRoomCollapsed = false;
      S.groupRoomCollapsedCaseId = null;
    }
    // 用户已收起本案：轮询/流式只刷新内容，不再强弹
    if (S.groupRoomCollapsed && (!S.groupRoomCollapsedCaseId || S.groupRoomCollapsedCaseId === cid)) {
      renderGroupRoom(c, { show: false });
      syncGroupRoomReopenChip();
      return;
    }
    renderGroupRoom(c, { show: true });
    syncGroupRoomReopenChip();
  }

  function renderGroupRoom(caseObj, { show = true } = {}) {
    const modal = $("groupRoomModal");
    if (!modal) return;
    const room = caseObj.group_room || {};
    if (show) modal.classList.remove("hidden");
    const transport = room.transport || "—";
    const gid = room.group_id ? ` · 组 ${String(room.group_id).slice(0, 14)}` : "";
    if ($("groupRoomTitle")) $("groupRoomTitle").textContent = "组群竞价聊天室";
    if ($("groupRoomMeta")) {
      $("groupRoomMeta").textContent = `${caseObj.case_id || ""} · ${caseObj.state || ""} · 通道 ${transport}${gid}`;
    }
    const ticker = $("groupRoomTicker");
    if (ticker) {
      const items = room.ticker || [];
      const html = items.length
        ? items.map((t) => `<span class="${escapeHtml(t.kind || "")}">${escapeHtml(t.text || "")}</span>`).join("")
        : `<span>等待成员入群…</span>`;
      ticker.innerHTML = `<div class="group-room-ticker-track">${html}${html}</div>`;
    }
    const mem = $("groupRoomMembers");
    if (mem) {
      mem.innerHTML = (room.members || []).map((m) => {
        const st = m.status || "invited";
        return `<span class="group-room-seat ${escapeHtml(st)}">${escapeHtml(m.title || m.id)} · ${escapeHtml(st)}</span>`;
      }).join("");
    }
    const box = $("groupRoomMsgs");
    if (box) {
      box.innerHTML = (room.messages || []).map((m) => {
        const role = m.role || "system";
        return `<div class="gr-msg ${escapeHtml(role)}">
          <div class="who">${escapeHtml(m.name || m.agent_id || role)}</div>
          <div class="bubble">${formatChatHtml(m.content || "")}</div>
        </div>`;
      }).join("") || `<div class="muted">群聊消息载入中…</div>`;
      box.scrollTop = box.scrollHeight;
    }
    const actions = $("groupRoomActions");
    if (actions) {
      const pc = caseObj.pending_choices;
      if (pc && Array.isArray(pc.choices) && pc.choices.length && caseObj.state === "GROUP_DECIDE") {
        const w = {
          kind: "choice_actions",
          case_id: caseObj.case_id,
          prompt: pc.prompt || "请点选组群采购方案",
          allow_note: false,
          choices: pc.choices,
        };
        actions.innerHTML = renderChoiceActions(w, { interactive: true });
        bindChoiceActions(actions);
        // 点选后收起由 sendChat 刷新
        actions.querySelectorAll(".choice-btn").forEach((btn) => {
          btn.addEventListener("click", () => {
            setTimeout(() => closeGroupRoom(), 400);
          }, { once: true });
        });
      } else if (room.status === "closed" || caseObj.state === "GROUP_TICKETS") {
        actions.innerHTML = `<p class="muted">工单已生成，可收起聊天室，到「工单待办」确认。</p>`;
      } else if (caseObj.state === "GROUP_BIDDING" && !(room.messages || []).length) {
        actions.innerHTML = `
          <p class="muted">入群已完成，报价可能曾被跨云 AIP 卡住。点下方按钮立即续跑主持抛需求与报价。</p>
          <button type="button" class="sl-btn primary" id="btnGroupResume">继续组群报价汇总</button>`;
        const b = $("btnGroupResume");
        if (b) {
          b.onclick = () => {
            b.disabled = true;
            sendChatText("继续组群");
          };
        }
      } else {
        actions.innerHTML = `<p class="muted">成员连接 / 报价进行中…（聊天室会自动刷新）</p>`;
      }
    }
  }

  function agentDisplayName(agentId) {
    const id = String(agentId || "");
    const map = {
      "supplier-a": "供应商A",
      "supplier-b": "供应商B",
      "supplier-c": "供应商C",
      logistics: "物流",
      "buyer-a": "采购A",
      "buyer-b": "采购B",
    };
    if (map[id]) return map[id];
    if (id.startsWith("supplier-")) return `供应·${id.slice(9)}`;
    return id || "伙伴";
  }

  function auctionWatchActive() {
    const st = S.flowCase?.state || "";
    return st === "BIDDING" || st === "BID_REVIEW";
  }

  function renderAuctionWatch(chatItems) {
    const box = $("auctionWatch");
    if (!box) return;
    if (workspaceOf() !== "chat" || isSupplierAgent() || !auctionWatchActive() || !S.flowCase) {
      box.classList.add("hidden");
      box.innerHTML = "";
      return;
    }
    const c = S.flowCase;
    const st = c.state || "";
    const live = st === "BIDDING";
    const summary = c.auction_summary || {};
    const bids = Array.isArray(c.auction_bids) ? c.auction_bids : [];
    const schemes = Array.isArray(summary.schemes) ? summary.schemes : [];
    const ranked = Array.isArray(summary.ranked) ? summary.ranked : [];
    const shortlist = Array.isArray(c.shortlist) ? c.shortlist : [];
    const product = (c.brief || {}).product_name || "标的";
    const qty = (c.brief || {}).quantity ?? "—";
    const transport = summary.transport || (bids.length ? "rpc" : "group");
    const offersGot = summary.offers_got != null ? summary.offers_got : null;

    const bidBySid = {};
    for (const b of bids) {
      if (b && b.supplier_agent_id) bidBySid[b.supplier_agent_id] = b;
    }

    const members = [];
    const seen = new Set();
    for (const p of shortlist) {
      const sid = p.agent_id || p.candidate_id;
      if (!sid || seen.has(sid)) continue;
      seen.add(sid);
      members.push({ id: sid, role: "supplier", name: p.name || agentDisplayName(sid) });
    }
    for (const b of bids) {
      const sid = b.supplier_agent_id;
      if (!sid || seen.has(sid)) continue;
      seen.add(sid);
      members.push({ id: sid, role: "supplier", name: agentDisplayName(sid) });
    }
    if (!seen.has("logistics")) {
      members.push({ id: "logistics", role: "logistics", name: "物流（旁听）" });
    }

    const seats = members.map((m) => {
      if (m.role === "logistics") {
        return `<div class="auction-seat bid-skip"><div class="nm">${escapeHtml(m.name)}</div>
          <div class="st">${live ? "组内旁听 · TCO" : "已合入到岸成本"}</div></div>`;
      }
      const b = bidBySid[m.id];
      if (live && !bids.length) {
        return `<div class="auction-seat bid-wait"><div class="nm">${escapeHtml(m.name)}</div>
          <div class="st">密封出价中…</div></div>`;
      }
      if (!b) {
        return `<div class="auction-seat bid-wait"><div class="nm">${escapeHtml(m.name)}</div>
          <div class="st">${live ? "等待回执" : "未出价"}</div></div>`;
      }
      if (b.error) {
        return `<div class="auction-seat bid-err"><div class="nm">${escapeHtml(m.name)}</div>
          <div class="st">失败</div></div>`;
      }
      if (b.unit_price == null && b.skipped) {
        return `<div class="auction-seat bid-skip"><div class="nm">${escapeHtml(m.name)}</div>
          <div class="st">跳过</div></div>`;
      }
      if (live) {
        return `<div class="auction-seat bid-ok"><div class="nm">${escapeHtml(m.name)}</div>
          <div class="st">已密封提交</div></div>`;
      }
      const tco = b.tco != null ? ` · TCO ${b.tco}` : "";
      const lead = b.lead_time_days != null ? ` · ${b.lead_time_days}天` : "";
      return `<div class="auction-seat bid-ok"><div class="nm">${escapeHtml(m.name)}</div>
        <div class="st">出价 ${escapeHtml(String(b.unit_price))}${escapeHtml(tco)}${escapeHtml(lead)}</div></div>`;
    }).join("");

    let schemeHtml = "";
    if (!live && schemes.length) {
      const rows = schemes.slice(0, 6).map((sch, i) => {
        const sid = sch.supplier_agent_id || sch.agent_id || "—";
        const tco = sch.tco ?? sch.grand_total ?? sch.total ?? "—";
        const freight = sch.freight ?? sch.shipping_fee ?? "—";
        const unit = sch.unit_price ?? "—";
        return `<tr class="${i === 0 ? "best" : ""}">
          <td>${i + 1}</td>
          <td>${escapeHtml(agentDisplayName(sid))}</td>
          <td>${escapeHtml(String(unit))}</td>
          <td>${escapeHtml(String(freight))}</td>
          <td>${escapeHtml(String(tco))}</td>
        </tr>`;
      }).join("");
      schemeHtml = `<table class="auction-schemes">
        <thead><tr><th>#</th><th>供应</th><th>单价</th><th>运费</th><th>TCO</th></tr></thead>
        <tbody>${rows}</tbody></table>`;
    } else if (!live && ranked.length) {
      const rows = ranked.slice(0, 6).map((b, i) => `<tr class="${i === 0 ? "best" : ""}">
        <td>${i + 1}</td>
        <td>${escapeHtml(agentDisplayName(b.supplier_agent_id))}</td>
        <td>${escapeHtml(String(b.unit_price))}</td>
        <td>—</td>
        <td>${escapeHtml(String(b.tco ?? b.unit_price))}</td>
      </tr>`).join("");
      schemeHtml = `<table class="auction-schemes">
        <thead><tr><th>#</th><th>供应</th><th>单价</th><th>运费</th><th>TCO</th></tr></thead>
        <tbody>${rows}</tbody></table>`;
    }

    const sealNote = live
      ? `<div class="auction-seal-note">盲拍进行中：各方密封出价，互不可见；物流旁听合入到岸成本。开标后在此点选方案。</div>`
      : `<div class="auction-seal-note">竞价已开标（仅采购可见）。请在下方点选订货方案；右侧可滚动查看 AIP 协作链路。</div>`;

    let decisions = "";
    if (!live) {
      const pc = c.pending_choices;
      let choiceW = null;
      if (pc && Array.isArray(pc.choices) && pc.choices.length) {
        choiceW = {
          kind: "choice_actions",
          case_id: c.case_id,
          prompt: pc.prompt || "组群竞价已完成，请点选订货方案",
          allow_note: pc.allow_note !== false,
          choices: pc.choices,
        };
      } else if (chatItems) {
        const fromChat = latestChoiceWidget(chatItems);
        if (fromChat && (fromChat.choices || []).length) choiceW = fromChat;
      }
      if (choiceW) {
        decisions = renderChoiceActions(choiceW, { interactive: true });
      }
    }

    const metaBits = [
      `通道 ${transport}`,
      offersGot != null ? `回执 ${offersGot}` : null,
      summary.group_id ? `组 ${String(summary.group_id).slice(0, 10)}` : null,
    ].filter(Boolean).join(" · ");

    box.innerHTML = `
      <div class="auction-watch-head">
        <span class="auction-watch-title">组群竞价观察</span>
        <span class="auction-phase ${live ? "live" : "review"}">${live ? "BIDDING · 密封中" : "BID_REVIEW · 待点选"}</span>
        <span class="auction-meta">${escapeHtml(String(product))} × ${escapeHtml(String(qty))}${metaBits ? ` · ${escapeHtml(metaBits)}` : ""}</span>
      </div>
      ${sealNote}
      <div class="auction-members">${seats}</div>
      ${schemeHtml}
      ${decisions}`;
    box.classList.remove("hidden");
    if (decisions) bindChoiceActions(box);
  }

  function renderFlowSteps(caseObj) {
    const box = $("flowSteps");
    if (!box) return;
    if (!caseObj) {
      box.innerHTML = "";
      return;
    }
    const cur = caseObj.state || "DRAFT";
    const idx = FLOW_ORDER.indexOf(cur);
    box.innerHTML = FLOW_ORDER.map((s, i) => {
      const cls = i < idx ? "done" : i === idx ? "active" : "";
      return `<span class="fstep ${cls}">${s}</span>`;
    }).join("");
  }

  const toastedIds = new Set();

  function showToast(n) {
    const stack = $("toastStack");
    if (!stack || !n || !n.id || toastedIds.has(n.id)) return;
    toastedIds.add(n.id);
    const kind = (n.payload && n.payload.kind) || "";
    const el = document.createElement("div");
    el.className = "toast" + (kind === "order_spawned" || kind === "docs_sent" ? " order" : "");
    el.innerHTML = `<h4>${escapeHtml(n.title || "通知")}</h4>
      <p>${escapeHtml(n.body || "")}</p>
      <div class="toast-go">${kind === "order_spawned" ? "点击前往工单确认 →" : "点击查看 →"}</div>`;
    el.onclick = async () => {
      try {
        await proxy(S.agentId, `api/erp/notifications/${n.id}/read`, {});
      } catch (_) { /* ignore */ }
      el.remove();
      if (kind === "order_spawned" || (n.payload && n.payload.ticket_id)) {
        S.page = "tickets";
        showPage();
        await loadTickets();
      } else if (!S.isSupplierDomain) {
        S.page = "notify";
        showPage();
        await loadNotifications();
      }
    };
    stack.appendChild(el);
    setTimeout(() => { if (el.parentNode) el.remove(); }, 9000);
  }

  async function pollToasts() {
    if (!S.agentId) return;
    try {
      const data = await proxy(S.agentId, "api/erp/notifications?unread_only=true&limit=20");
      const items = data.items || [];
      if ($("badgeNtf")) $("badgeNtf").textContent = String(items.length);
      for (const n of items) {
        const kind = (n.payload && n.payload.kind) || "";
        if (kind === "order_spawned" || kind === "docs_sent" || /新订单|电子订单/.test(n.title || "")) {
          showToast(n);
        }
      }
    } catch (_) { /* ignore */ }
  }

  async function loadNotifications() {
    let data;
    try {
      data = await proxy(S.agentId, "api/erp/notifications");
    } catch (e) {
      if ($("notifyList")) $("notifyList").innerHTML = `<p class="muted">通知加载失败</p>`;
      return;
    }
    const items = data.items || [];
    if ($("badgeNtf")) $("badgeNtf").textContent = String(items.filter((n) => !n.read).length);
    const box = $("notifyList");
    if (!box) return;
    box.innerHTML = "";
    if (!items.length) { box.innerHTML = `<p class="muted">暂无通知</p>`; return; }
    for (const n of items) {
      const el = document.createElement("div");
      el.className = "item" + (n.read ? "" : " unread");
      const kind = (n.payload && n.payload.kind) || "";
      el.innerHTML = `<h4>${escapeHtml(n.title || "")}</h4><p>${escapeHtml(n.body || "")}</p>
        <div class="row">
          ${!n.read ? `<button type="button" class="sec" data-read="${escapeHtml(n.id)}">标为已读</button>` : ""}
          ${kind === "order_spawned" || (n.payload && n.payload.ticket_id)
            ? `<button type="button" class="sec" data-goto-ticket="${escapeHtml((n.payload && n.payload.ticket_id) || "")}">去工单</button>`
            : ""}
        </div>`;
      box.appendChild(el);
    }
    box.querySelectorAll("[data-read]").forEach((b) => {
      b.onclick = async () => {
        await proxy(S.agentId, `api/erp/notifications/${b.getAttribute("data-read")}/read`, {});
        await loadNotifications();
      };
    });
    box.querySelectorAll("[data-goto-ticket]").forEach((b) => {
      b.onclick = async () => {
        S.page = "tickets";
        showPage();
        await loadTickets();
      };
    });
  }

  async function loadSales() {
    const data = await proxy(S.agentId, "api/erp/sales-orders");
    $("salesTable").innerHTML = table(
      ["单号", "商品", "数量", "金额", "状态", "时间"],
      (data.items || []).map((o) => [o.id, o.sku, o.qty, o.amount, o.status, (o.created_at || "").slice(0, 19)])
    );
  }

  async function loadInventory() {
    const data = await proxy(S.agentId, "api/erp/inventory");
    let html = `<table><thead><tr><th>编码</th><th>名称</th><th>可用</th><th>安全</th><th>单位</th><th>优选供应商</th><th>状态</th></tr></thead><tbody>`;
    for (const i of data.items || []) {
      html += `<tr class="${i.low ? "low" : ""}"><td>${i.code}</td><td>${i.name}</td><td>${i.available}</td><td>${i.safety_stock}</td><td>${i.unit}</td><td>${i.preferred_supplier}</td><td>${i.low ? "不足" : "正常"}</td></tr>`;
    }
    html += `</tbody></table>`;
    $("invTable").innerHTML = html;
  }

  function closeThreadMenu() {
    const menu = $("threadMenu");
    const btn = $("threadCurrent");
    if (menu) menu.classList.add("hidden");
    if (btn) btn.setAttribute("aria-expanded", "false");
  }

  function renderThreadMenu(items) {
    const menu = $("threadMenu");
    const label = $("threadCurrentLabel");
    if (!menu || !label) return;
    const active = (items || []).find((t) => t.id === S.threadId) || (items || [])[0];
    label.textContent = active ? (active.title || active.id) : "选择对话";
    menu.innerHTML = "";
    if (!(items || []).length) {
      menu.innerHTML = `<div class="thread-empty muted">暂无历史对话</div>`;
      return;
    }
    for (const t of items) {
      const row = document.createElement("div");
      row.className = "thread-item" + (t.id === S.threadId ? " active" : "");
      row.dataset.id = t.id;
      const title = document.createElement("button");
      title.type = "button";
      title.className = "thread-item-main";
      title.textContent = t.title || t.id;
      title.title = t.title || t.id;
      title.onclick = async (e) => {
        e.stopPropagation();
        closeThreadMenu();
        if (t.id !== S.threadId) await switchThread(t.id);
      };
      const del = document.createElement("button");
      del.type = "button";
      del.className = "thread-del";
      del.title = "删除此对话";
      del.setAttribute("aria-label", "删除");
      del.textContent = "×";
      del.onclick = async (e) => {
        e.stopPropagation();
        if (!confirm(`删除对话「${t.title || t.id}」？`)) return;
        try {
          const out = await proxy(S.agentId, `api/erp/chat/threads/${t.id}`, undefined, "DELETE");
          S.threadId = out.active_thread_id || null;
          S.flowCaseId = null;
          S.flowCase = null;
          saveAgentFlow();
          closeThreadMenu();
          await loadThreads();
          await loadFlow();
          await loadChatHistory();
        } catch (err) {
          alert("删除失败：" + (err.message || err));
        }
      };
      row.appendChild(title);
      row.appendChild(del);
      menu.appendChild(row);
    }
  }

  async function loadThreads() {
    if (workspaceOf() !== "chat" || !$("threadPicker")) return;
    let data;
    try {
      data = await proxy(S.agentId, "api/erp/chat/threads");
    } catch (_) {
      return;
    }
    const items = data.items || [];
    if (!items.length) {
      const t = await proxy(S.agentId, "api/erp/chat/threads", { title: "默认对话" });
      S.threadId = t.id;
      data = await proxy(S.agentId, "api/erp/chat/threads");
    } else {
      S.threadId = data.active_thread_id || items[0].id;
    }
    renderThreadMenu(data.items || []);
  }

  async function switchThread(threadId) {
    if (!threadId) return;
    S.threadId = threadId;
    S.flowCaseId = null;
    S.flowCase = null;
    saveAgentFlow();
    const act = await proxy(S.agentId, `api/erp/chat/threads/${threadId}/activate`, {});
    // 只恢复本窗绑定案，禁止挂到其它窗口的历史案
    if (act && act.case_id) {
      S.flowCaseId = act.case_id;
      saveAgentFlow();
    }
    await loadFlow();
    await loadChatHistory();
  }

  async function newThread() {
    const t = await proxy(S.agentId, "api/erp/chat/threads", { title: `对话 ${new Date().toLocaleString("zh-CN")}` });
    S.threadId = t.id;
    S.flowCaseId = null;
    S.flowCase = null;
    saveAgentFlow();
    await loadThreads();
    await loadFlow();
    await loadChatHistory();
  }

  async function loadChatHistory() {
    const q = S.threadId
      ? `api/erp/conversations?thread_id=${encodeURIComponent(S.threadId)}`
      : "api/erp/conversations";
    let data;
    try {
      data = await proxy(S.agentId, q);
    } catch (_) {
      // v2/旧端缺 conversations 时不阻断整页加载
      data = { items: [], thread_id: S.threadId };
    }
    if (data.thread_id) S.threadId = data.thread_id;
    const items = data.items || [];
    // 从最近消息恢复采购案，便于短名单表单判断是否仍可勾选
    for (let i = items.length - 1; i >= 0; i--) {
      const meta = parseMeta(items[i]);
      if (meta.case_id) {
        S.flowCaseId = meta.case_id;
        break;
      }
    }
    if (S.flowCaseId && (!S.flowCase || S.flowCase.case_id !== S.flowCaseId)) {
      try {
        S.flowCase = await proxy(S.agentId, `api/flow/cases/${S.flowCaseId}`);
      } catch (_) { /* ignore */ }
    }
    renderChat(items);
    const hist = $("histList");
    if (!hist) return;
    hist.innerHTML = "";
    for (const m of items) {
      const el = document.createElement("div");
      el.className = "item";
      el.innerHTML = `<h4>${m.role}</h4><p>${escapeHtml(m.content)}</p>`;
      hist.appendChild(el);
    }
  }

  function parseMeta(m) {
    if (m.meta && typeof m.meta === "object") return m.meta;
    if (m.meta_json) {
      try { return JSON.parse(m.meta_json); } catch { return {}; }
    }
    return {};
  }

  function money(v) {
    if (v == null || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return escapeHtml(String(v));
    return `¥${n.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
  }

  function renderQuoteCard(result) {
    if (!result || !result.results) return "";
    const rows = (result.results || []).filter((r) => r.quote).map((r) => {
      const pay = (r.quote && r.quote.payload) || r.quote || {};
      const prod = pay.product || {};
      return [
        r.supplier || pay.supplier_agent_id || "—",
        r.material_code || "—",
        prod.name || "—",
        prod.quantity ?? "—",
        pay.unit_price != null ? `¥${pay.unit_price}` : "—",
        pay.lead_time_days ?? "—",
        pay.available_quantity ?? "—",
      ];
    });
    if (!rows.length) return "";
    const bid = escapeHtml(result.business_id || "");
    return `<div class="quote-card"><div class="quote-bid">业务单 ${bid} · ${rows.length} 份报价</div>${table(
      ["供应商", "物料", "名称", "数量", "单价", "交期(天)", "可供"],
      rows
    )}</div>`;
  }

  function renderCompareTableWidget(w) {
    if (!w) return "";
    const tbl = w.table;
    if (tbl && Array.isArray(tbl.headers) && Array.isArray(tbl.rows)) {
      const rows = tbl.rows.map((r) => {
        const cells = [...(r || [])];
        // 货价/运费/总价列做货币格式（索引 2,3,4）
        [2, 3, 4].forEach((i) => {
          if (cells[i] != null && cells[i] !== "—") cells[i] = money(cells[i]);
        });
        return cells;
      });
      const sum = w.summary || {};
      const foot = sum.lowest_grand_total != null
        ? `<div class="quote-bid">最低总价 ${money(sum.lowest_grand_total)} · 有效 ${sum.ok_count ?? "—"} / 失败 ${sum.fail_count ?? "—"}</div>`
        : "";
      return `<div class="quote-card ui-widget" data-kind="quote_compare_table">
        <div class="quote-bid">询价对比 · ${escapeHtml(w.case_id || "")}</div>
        ${table(tbl.headers, rows)}${foot}
      </div>`;
    }
    const quotes = w.quotes || [];
    if (!quotes.length) return "";
    const rows = quotes.map((q) => {
      const p = q.partner || {};
      const fr = q.freight || {};
      return [
        p.name || p.agent_id || p.aic || "—",
        q.status || "—",
        money(q.goods_total),
        money(fr.amount),
        money(q.grand_total),
        q.lead_time_days ?? "—",
      ];
    });
    return `<div class="quote-card ui-widget" data-kind="quote_compare_table">
      <div class="quote-bid">询价对比 · ${escapeHtml(w.case_id || "")}</div>
      ${table(["供应商", "状态", "货价", "运费", "总价", "交期(天)"], rows)}
    </div>`;
  }

  function renderShortlistForm(w, { interactive = true } = {}) {
    if (!w || !Array.isArray(w.candidates) || !w.candidates.length) return "";
    const hint = w.ui_hint || {};
    const minSel = Number(hint.min_select || 1);
    const maxSel = Number(hint.max_select || 5);
    const title = hint.title || "请确认询价短名单";
    const caseId = w.case_id || "";
    const uid = `sl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
    const rows = w.candidates.map((c, i) => {
      const id = escapeHtml(c.candidate_id || c.agent_id || `cand-${i}`);
      const trade = escapeHtml(c.trade_name || c.name || c.agent_id || id);
      const agentTag = escapeHtml(c.agent_id || "");
      const addr = escapeHtml(c.address || "");
      const biz = escapeHtml(c.business || c.match_reason || c.source_label || "平台发现");
      const city = escapeHtml(c.city || "");
      const checked = i < Math.min(3, maxSel) ? "checked" : "";
      const input = interactive
        ? `<input type="checkbox" class="sl-check" value="${id}" ${checked} data-form="${uid}" />`
        : `<span class="sl-mark">·</span>`;
      return `<label class="sl-row">${input}
        <span class="sl-body">
          <span class="sl-name">${trade}${agentTag ? ` · ${agentTag}` : ""}</span>
          <span class="sl-meta">${city ? `${city} · ` : ""}${addr || "地址待补充"}</span>
          <span class="sl-reason">${biz}</span>
        </span>
      </label>`;
    }).join("");
    const isGroupAsk = (w.mode === "group_ask")
      || (S.flowCase && (S.flowCase.state === "GROUP_ASK" || (S.flowCase.hitl_pending || {}).phase === "group_ask"));
    const submitLabel = escapeHtml(w.submit_label || (isGroupAsk ? "确认组群竞价" : "确认并询价"));
    const actions = interactive
      ? `<div class="sl-actions">
          <button type="button" class="sl-btn primary" data-action="submit" data-form="${uid}" data-mode="${isGroupAsk ? "group_ask" : "rfq"}">${submitLabel}</button>
          <button type="button" class="sl-btn" data-action="refresh" data-form="${uid}">换一批再发现</button>
          <span class="sl-range muted">可选 ${minSel}–${maxSel} 家${isGroupAsk ? " · 组群" : ""}</span>
        </div>`
      : `<div class="widget-hint muted">历史短名单（只读）</div>`;
    return `<div class="shortlist-form ui-widget" data-kind="shortlist_confirm" data-form-id="${uid}"
      data-case="${escapeHtml(caseId)}" data-min="${minSel}" data-max="${maxSel}" data-interactive="${interactive ? "1" : "0"}"
      data-mode="${isGroupAsk ? "group_ask" : "rfq"}">
      <div class="sl-title">${escapeHtml(title)}</div>
      <div class="sl-list">${rows}</div>
      ${actions}
    </div>`;
  }

  function renderChoiceActions(w, { interactive = true } = {}) {
    if (!w || !Array.isArray(w.choices) || !w.choices.length) return "";
    const uid = `ch-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
    const prompt = escapeHtml(w.prompt || w.ui_hint?.title || "请点选下一步");
    const allowNote = w.allow_note !== false;
    const note = interactive && allowNote
      ? `<textarea class="choice-note" data-choice-note="${uid}" rows="1" placeholder="补充说明（可选）" title="点按钮时一并发送"></textarea>`
      : "";
    const btns = w.choices.map((c, i) => {
      const id = escapeHtml(c.id || `opt-${i + 1}`);
      const label = escapeHtml(c.label || c.title || id);
      const rawMsg = String(c.message || c.action || c.label || id);
      const encMsg = encodeURIComponent(rawMsg);
      const tip = escapeHtml(c.hint || c.label || c.title || id);
      const primary = c.primary ? " primary" : "";
      if (!interactive) {
        return `<div class="choice-btn${primary}" data-readonly="1" title="${tip}">${label}</div>`;
      }
      return `<button type="button" class="choice-btn${primary}" title="${tip}" data-choice-id="${id}" data-choice-msg="${encMsg}" data-choice-uid="${uid}">${label}</button>`;
    }).join("");
    return `<div class="choice-panel ui-widget" data-kind="choice_actions" data-interactive="${interactive ? "1" : "0"}" data-uid="${uid}" data-case="${escapeHtml(w.case_id || "")}">
      <div class="choice-head"><div class="choice-title">${prompt}</div>${note}</div>
      <div class="choice-actions">${btns}</div>
    </div>`;
  }

  function bindChoiceActions(root) {
    const scope = root || document;
    scope.querySelectorAll(".choice-panel[data-interactive='1']").forEach((panel) => {
      if (panel.dataset.bound === "1") return;
      panel.dataset.bound = "1";
      panel.addEventListener("click", (e) => {
        const btn = e.target.closest(".choice-btn[data-choice-msg]");
        if (!btn || !panel.contains(btn)) return;
        e.preventDefault();
        const uid = btn.dataset.choiceUid || panel.dataset.uid;
        const noteEl = uid ? panel.querySelector(`[data-choice-note="${uid}"]`) : null;
        const note = (noteEl && noteEl.value || "").trim();
        let msg = "";
        try { msg = decodeURIComponent(btn.dataset.choiceMsg || ""); } catch (_) { msg = btn.dataset.choiceMsg || ""; }
        if (!msg) msg = (btn.textContent || "").trim();
        if (note) msg = `${msg}\n【补充】${note}`;
        panel.querySelectorAll("button").forEach((b) => { b.disabled = true; });
        const dock = $("choiceDock");
        if (dock) { dock.classList.add("hidden"); dock.innerHTML = ""; }
        sendChatText(msg);
      });
    });
  }

  function renderUiWidgets(widgets, { interactive = true } = {}) {
    if (!Array.isArray(widgets) || !widgets.length) return "";
    return widgets.map((w) => {
      if (w.kind === "shortlist_confirm") return renderShortlistForm(w, { interactive });
      if (w.kind === "quote_compare_table") return renderCompareTableWidget(w);
      if (w.kind === "choice_actions") return renderChoiceActions(w, { interactive });
      return "";
    }).join("");
  }

  function latestChoiceWidget(items) {
    for (let i = (items || []).length - 1; i >= 0; i--) {
      const meta = parseMeta(items[i]);
      const widgets = meta.ui_widgets || [];
      for (let j = widgets.length - 1; j >= 0; j--) {
        if (widgets[j]?.kind === "choice_actions" && (widgets[j].choices || []).length) {
          return widgets[j];
        }
      }
    }
    // 案上挂的 pending_choices
    const pc = S.flowCase?.pending_choices;
    if (pc && Array.isArray(pc.choices) && pc.choices.length) {
      return {
        kind: "choice_actions",
        case_id: S.flowCase?.case_id || S.flowCaseId,
        prompt: pc.prompt,
        allow_note: pc.allow_note !== false,
        choices: pc.choices,
      };
    }
    return null;
  }

  function renderChoiceDock(items) {
    const dock = $("choiceDock");
    if (!dock) return;
    // 普通短名单优先占 dock；组群断点①保留底部「确认组群竞价」按钮，避免无处可点
    if (shortlistStillPending() && candidatesFromCase().length && !isGroupAskPending()) {
      dock.classList.add("hidden");
      dock.innerHTML = "";
      return;
    }
    // 组群竞价观察页已挂决策按钮时，避免底部再重复一套
    if (auctionWatchActive()) {
      const hasPending = !!(S.flowCase?.pending_choices?.choices?.length);
      const hasWatchBtns = !!$("auctionWatch")?.querySelector(".choice-panel[data-interactive='1']");
      if (hasPending || hasWatchBtns) {
        dock.classList.add("hidden");
        dock.innerHTML = "";
        return;
      }
    }
    const w = latestChoiceWidget(items);
    if (!w) {
      dock.classList.add("hidden");
      dock.innerHTML = "";
      return;
    }
    dock.innerHTML = renderChoiceActions(w, { interactive: true });
    dock.classList.remove("hidden");
    bindChoiceActions(dock);
  }

  function bindShortlistForms(root) {
    const scope = root || document;
    scope.querySelectorAll(".shortlist-form[data-interactive='1']").forEach((form) => {
      if (form.dataset.bound === "1") return;
      form.dataset.bound = "1";
      form.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-action]");
        if (!btn || !form.contains(btn)) return;
        e.preventDefault();
        const action = btn.dataset.action;
        if (action === "refresh") {
          sendChatText("平台结果不合适，请换查询词再发现供应商");
          return;
        }
        if (action !== "submit") return;
        const minSel = Number(form.dataset.min || 1);
        const maxSel = Number(form.dataset.max || 5);
        const checks = [...form.querySelectorAll(".sl-check:checked")].map((el) => el.value);
        if (checks.length < minSel || checks.length > maxSel) {
          alert(`请勾选 ${minSel}–${maxSel} 家供应商`);
          return;
        }
        form.querySelectorAll("button").forEach((b) => { b.disabled = true; });
        const caseId = form.dataset.case || "";
        const mode = form.dataset.mode || btn.dataset.mode || "rfq";
        let msg;
        if (mode === "group_ask") {
          // 一次提交：记录成员 + 确认开群，避免「确认组群竞价」按钮被短名单盖住后无处可点
          msg = caseId
            ? `确认组群竞价：已确认短名单，请对以下 candidate_id 调用 rfq.send_batch：${checks.join(",")}（case_id=${caseId}）`
            : `确认组群竞价：已确认短名单，请对以下 candidate_id 调用 rfq.send_batch：${checks.join(",")}`;
        } else {
          msg = caseId
            ? `已确认短名单，请对以下 candidate_id 调用 rfq.send_batch：${checks.join(",")}（case_id=${caseId}）`
            : `已确认短名单，请对以下 candidate_id 调用 rfq.send_batch：${checks.join(",")}`;
        }
        sendChatText(msg);
      });
    });
  }

  function isGroupAskPending() {
    const st = S.flowCase?.state || "";
    const hitl = S.flowCase?.hitl_pending || {};
    return st === "GROUP_ASK" || hitl.phase === "group_ask"
      || (S.flowCase?.path === "group" && hitl.gate === "confirm_shortlist");
  }

  function shortlistStillPending() {
    const st = S.flowCase?.state || "";
    const hitl = S.flowCase?.hitl_pending || {};
    if (st === "SHORTLIST_PENDING") return true;
    if (st === "GROUP_ASK") return true;
    if ((hitl.gate || hitl.phase) === "confirm_shortlist") return true;
    if (hitl.phase === "group_ask") return true;
    return false;
  }

  function candidatesFromCase() {
    const c = S.flowCase || {};
    const list = c.candidates || c.discovery_meta?.ui_candidates || [];
    return Array.isArray(list) ? list : [];
  }

  function renderShortlistDock() {
    const dock = $("shortlistDock");
    if (!dock) return;
    const pending = shortlistStillPending();
    const cands = candidatesFromCase();
    if (!pending || !cands.length) {
      dock.classList.add("hidden");
      dock.innerHTML = "";
      return;
    }
    const groupAsk = isGroupAskPending();
    const widget = {
      kind: "shortlist_confirm",
      mode: groupAsk ? "group_ask" : "rfq",
      submit_label: groupAsk ? "确认组群竞价" : "确认并询价",
      case_id: S.flowCase?.case_id || S.flowCaseId || "",
      candidates: cands.map((c, i) => ({
        candidate_id: c.candidate_id || c.agent_id || `cand-${i + 1}`,
        agent_id: c.agent_id,
        name: c.trade_name || c.name || c.agent_id,
        trade_name: c.trade_name || c.name,
        address: c.address || "",
        city: c.city || "",
        business: c.business || c.match_reason || "",
        aic: c.aic || "",
        skills: c.skills || [],
        match_reason: c.match_reason || c.source_label || "平台发现",
        source_label: c.source_label,
      })),
      title: groupAsk
        ? "组群竞价：勾选入群供应，再点「确认组群竞价」"
        : "请勾选供应商（名称/地址/主营如下），确认后统一询价",
      ui_hint: {
        form: "shortlist_confirm",
        title: groupAsk
          ? "组群竞价：勾选入群供应，再点「确认组群竞价」"
          : "请勾选供应商（名称/地址/主营如下），确认后统一询价",
        min_select: 1,
        max_select: Math.min(5, Math.max(1, cands.length)),
      },
    };
    dock.innerHTML = renderShortlistForm(widget, { interactive: true });
    dock.classList.remove("hidden");
    bindShortlistForms(dock);
  }

  function renderThinkTrailHtml(steps, { collapsed = false } = {}) {
    const list = Array.isArray(steps) ? steps.filter((s) => s && (s.text || s.message)) : [];
    if (!list.length) return "";
    const items = list
      .map((s, idx) => {
        const text = s.text || s.message || "";
        const done = idx < list.length - 1;
        return `<li class="think-step ${done ? "done" : "done"}" data-text="${escapeHtml(text)}" data-phase="${escapeHtml(s.phase || "")}">
          <span class="think-mark">✓</span><span class="think-text">${escapeHtml(text)}</span>
        </li>`;
      })
      .join("");
    const last = list[list.length - 1];
    const label = escapeHtml((last && (last.text || last.message)) || "处理轨迹");
    return `<div class="think-trail${collapsed ? " collapsed" : ""}">
      <button type="button" class="think-toggle" aria-expanded="${collapsed ? "false" : "true"}">
        <span class="think-toggle-label">处理轨迹</span>
        <span class="think-toggle-meta">${list.length} 步</span>
      </button>
      <ol class="think-steps">${items}</ol>
    </div>`;
  }

  function bindThinkToggles(root) {
    (root || document).querySelectorAll(".think-trail .think-toggle").forEach((toggle) => {
      if (toggle.dataset.bound === "1") return;
      toggle.dataset.bound = "1";
      toggle.onclick = () => {
        const trail = toggle.closest(".think-trail");
        if (!trail) return;
        const open = !trail.classList.contains("collapsed");
        trail.classList.toggle("collapsed", open);
        toggle.setAttribute("aria-expanded", open ? "false" : "true");
      };
    });
  }

  function renderChat(items) {
    const box = $("chatMsgs");
    box.innerHTML = "";
    if (!items.length) {
      box.innerHTML = `<div class="msg ai"><div class="bubble">你好，我是${agentTitle()}助手。</div></div>`;
      renderShortlistDock();
      renderChoiceDock([]);
      return;
    }
    // 气泡内历史表单一律只读；可勾选/点选交互放在底部 dock
    for (let i = 0; i < items.length; i++) {
      const m = items[i];
      const el = document.createElement("div");
      el.className = "msg " + (m.role === "user" ? "user" : "ai");
      const meta = parseMeta(m);
      let extra = "";
      if (meta.ui_widgets) {
        // 气泡内 choice 只读摘要；真正点选在 choiceDock
        const bubbleWidgets = (meta.ui_widgets || []).filter((w) => w.kind !== "choice_actions");
        extra += renderUiWidgets(bubbleWidgets, { interactive: false });
      }
      if (meta.intent === "rfq" && meta.result) {
        extra += renderQuoteCard(meta.result);
      }
      let content = m.content || "";
      if (extra && content.includes("报价明细：")) {
        content = content.split("报价明细：")[0].trim();
      }
      const trailHtml =
        m.role !== "user" ? renderThinkTrailHtml(meta.think_steps || meta.think_trail || [], { collapsed: false }) : "";
      el.innerHTML = `${trailHtml}<div class="bubble">${formatChatHtml(content)}${extra}</div>`;
      box.appendChild(el);
    }
    bindThinkToggles(box);
    box.scrollTop = box.scrollHeight;
    renderAuctionWatch(items);
    renderShortlistDock();
    renderChoiceDock(items);
  }

  function closeDetailModal() {
    const m = $("detailModal");
    if (m) m.classList.add("hidden");
  }

  function openDetailModal(title, html) {
    if ($("detailTitle")) $("detailTitle").textContent = title || "详情";
    if ($("detailBody")) $("detailBody").innerHTML = html;
    if ($("detailModal")) $("detailModal").classList.remove("hidden");
  }

  function prettyJson(obj) {
    try {
      return escapeHtml(JSON.stringify(obj, null, 2));
    } catch {
      return escapeHtml(String(obj));
    }
  }

  function renderMailDetailHtml(m) {
    const kindMap = { e_order: "电子订单", e_invoice: "电子发票", notice: "通知" };
    const doc = (m.attachment && (m.attachment.doc || m.attachment)) || null;
    let docHtml = "";
    if (doc && typeof doc === "object") {
      const rows = Object.entries(doc)
        .filter(([k]) => k !== "order_draft")
        .map(([k, v]) => `<span>${escapeHtml(k)}</span><div>${escapeHtml(typeof v === "object" ? JSON.stringify(v) : String(v ?? ""))}</div>`)
        .join("");
      docHtml = `<div class="detail-section">单据字段</div><div class="kv">${rows}</div>
        <div class="detail-section">原始附件 JSON</div><pre>${prettyJson(m.attachment)}</pre>`;
    }
    return `
      <div class="kv">
        <span>类型</span><div>${escapeHtml(kindMap[m.mail_kind] || m.mail_kind || "")}</div>
        <span>主题</span><div>${escapeHtml(m.subject || "")}</div>
        <span>方向</span><div>${escapeHtml(m.folder || m.direction || "")}</div>
        <span>发件</span><div>${escapeHtml(m.from_email || m.from_agent || "")}</div>
        <span>收件</span><div>${escapeHtml(m.to_email || m.to_agent || "")}</div>
        <span>工单</span><div>${escapeHtml(m.ticket_id || "—")}</div>
        <span>时间</span><div>${escapeHtml((m.created_at || "").slice(0, 19))}</div>
        <span>邮件 ID</span><div>${escapeHtml(m.id || "")}</div>
      </div>
      <div class="detail-section">正文</div>
      <p>${escapeHtml(m.body || "")}</p>
      ${docHtml}
      ${m.meta ? `<div class="detail-section">元数据</div><pre>${prettyJson(m.meta)}</pre>` : ""}
      ${m.ticket_id ? `<div class="row-actions" style="margin-top:1rem"><button type="button" class="sec" id="btnMailToProv">查看本单全链路审计</button></div>` : ""}
    `;
  }

  async function showMailDetail(mailId) {
    const m = await proxy(S.agentId, `api/erp/mailbox/${encodeURIComponent(mailId)}`);
    const kindMap = { e_order: "电子订单", e_invoice: "电子发票", notice: "通知" };
    openDetailModal(`${kindMap[m.mail_kind] || "邮件"}详情`, renderMailDetailHtml(m));
    const btn = $("btnMailToProv");
    if (btn && m.ticket_id) {
      btn.onclick = () => {
        closeDetailModal();
        S.page = "audit";
        showPage();
        openOrderProvenance({ ticket_id: m.ticket_id });
      };
    }
    await loadMailbox();
  }

  async function loadMailbox() {
    const folder = ($("mailFolder") && $("mailFolder").value) || "";
    const q = folder ? `api/erp/mailbox?folder=${encodeURIComponent(folder)}` : "api/erp/mailbox";
    let data;
    try {
      data = await proxy(S.agentId, q);
    } catch (e) {
      if ($("mailList")) $("mailList").innerHTML = `<p class="muted">邮箱加载失败：${escapeHtml(e.message || e)}</p>`;
      return;
    }
    if ($("mailAddr")) $("mailAddr").textContent = data.email || "";
    const unread = (data.items || []).filter((m) => m.folder === "inbox" && !m.read).length;
    if ($("badgeMail")) $("badgeMail").textContent = String(unread);
    const box = $("mailList");
    if (!box) return;
    box.innerHTML = "";
    if (!(data.items || []).length) {
      box.innerHTML = `<p class="muted">暂无邮件</p>`;
      return;
    }
    for (const m of data.items) {
      const el = document.createElement("div");
      el.className = "item clickable" + (m.read ? "" : " unread");
      const kindMap = { e_order: "电子订单", e_invoice: "电子发票", notice: "通知" };
      el.innerHTML = `<h4>${escapeHtml(kindMap[m.mail_kind] || m.mail_kind)} · ${escapeHtml(m.subject || "")}</h4>
        <p class="muted">${m.folder === "sent" ? "发往" : "来自"} ${escapeHtml(m.folder === "sent" ? (m.to_email || m.to_agent || "") : (m.from_email || m.from_agent || ""))}
        · ${(m.created_at || "").slice(0, 19)}${m.ticket_id ? ` · 工单 ${escapeHtml(m.ticket_id)}` : ""}</p>
        <p>${escapeHtml((m.body || "").slice(0, 180))}</p>
        <div class="row-actions"><button type="button" class="sec btn-mail-detail">查看详情</button></div>`;
      el.querySelector(".btn-mail-detail").onclick = (ev) => {
        ev.stopPropagation();
        showMailDetail(m.id).catch((e) => alert("详情失败：" + (e.message || e)));
      };
      el.onclick = () => showMailDetail(m.id).catch((e) => alert("详情失败：" + (e.message || e)));
      box.appendChild(el);
    }
  }

  function orderAckLabel(t) {
    const st = t.state || {};
    if (st.cancelled) return { text: "已取消", cls: "wait" };
    if (t.kind === "logistics_order") {
      // 新链路：采购↔物流；兼容旧工单供应↔物流
      const shipperAck = !!(st.buyer_logistics_ack || st.supplier_logistics_ack);
      const logAck = !!st.logistics_agent_ack;
      let selfAck;
      let peerAck;
      if (S.agentId.startsWith("buyer")) {
        selfAck = !!st.buyer_logistics_ack;
        peerAck = logAck;
      } else if (S.agentId.startsWith("supplier")) {
        selfAck = !!st.supplier_logistics_ack;
        peerAck = logAck;
      } else {
        selfAck = logAck;
        peerAck = shipperAck;
      }
      if (t.status === "closed" || st.effective) return { text: "物流已生效", cls: "done" };
      if (selfAck && peerAck) return { text: "双方已确认物流", cls: "done" };
      if (selfAck && !peerAck) return { text: "己方已确认物流 · 等待对端", cls: "wait" };
      if (!selfAck && peerAck) return { text: "对端已确认物流 · 请本方确认", cls: "wait" };
      return { text: "待确认物流订单", cls: "wait" };
    }
    const isBuyer = S.agentId.startsWith("buyer");
    const selfAck = !!(isBuyer ? st.buyer_order_ack : st.supplier_order_ack);
    const peerAck = !!(isBuyer ? st.supplier_order_ack : st.buyer_order_ack);
    if (t.status === "closed" && st.order_effective) return { text: "订单已生效并回档", cls: "done" };
    if (t.status === "closed") return { text: "已回档", cls: "done" };
    if (st.order_effective || st.phase === "effective") return { text: "订单已生效", cls: "done" };
    if (st.docs_sent || st.phase === "docs_sent") return { text: "双方已确认 · 单据已发", cls: "done" };
    if (selfAck && peerAck) return { text: "双方已确认", cls: "done" };
    if (selfAck && !peerAck) return { text: "己方已确认 · 等待对端", cls: "wait" };
    if (!selfAck && peerAck) return { text: "对端已确认 · 请本方确认", cls: "wait" };
    return { text: "待确认订单（或取消）", cls: "wait" };
  }

  async function loadTickets() {
    const st = ($("ticketFilter") && $("ticketFilter").value) || "";
    const q = st ? `api/erp/tickets?status=${encodeURIComponent(st)}` : "api/erp/tickets";
    let data;
    try {
      data = await proxy(S.agentId, q);
    } catch (e) {
      if ($("ticketList")) $("ticketList").innerHTML = `<p class="muted">工单加载失败：${escapeHtml(e.message || e)}</p>`;
      return;
    }
    const box = $("ticketList");
    if (!box) return;
    box.innerHTML = "";
    const statusLabel = { open: "待办", suspended: "挂起", closed: "已回档" };
    const openCount = (data.items || []).filter((t) => t.status === "open" || t.status === "suspended").length;
    if ($("badgeTicket")) $("badgeTicket").textContent = String(openCount);
    if (!(data.items || []).length) {
      box.innerHTML = `<p class="muted">暂无工单</p>`;
      return;
    }
    for (const t of data.items) {
      const el = document.createElement("div");
      el.className = "item" + (t.kind === "order" || t.kind === "logistics_order" ? " ticket-item order-ticket" : "");
      const flags = `订单己方${t.order_recv_self ? "✓" : "·"}对端${t.order_recv_peer ? "✓" : "·"} · 发票己方${t.invoice_recv_self ? "✓" : "·"}对端${t.invoice_recv_peer ? "✓" : "·"}`;
      const phase = t.kind === "order" || t.kind === "logistics_order" ? orderAckLabel(t) : null;
      const phaseHtml = phase
        ? `<span class="ticket-phase ${phase.cls}">${escapeHtml(phase.text)}</span>`
        : "";
      const quoteHint = t.kind === "logistics_order" && t.state && t.state.quote
        ? `<p class="muted">运费 ${escapeHtml(String(t.state.quote.shipping_cost ?? "—"))} · ETA ${escapeHtml(String(t.state.quote.eta_days ?? "—"))}天 · ${escapeHtml(t.state.quote.origin_city || "?")}→${escapeHtml(t.state.quote.dest_city || "?")}</p>`
        : "";
      el.innerHTML = `<h4>${escapeHtml(t.title || t.id)} <span class="muted">${statusLabel[t.status] || t.status}</span>${phaseHtml}</h4>
        <p class="muted">${escapeHtml(t.id)} · ${escapeHtml(t.kind || "")}${t.peer_agent_id ? ` · 对端 ${escapeHtml(t.peer_agent_id)}` : ""}${t.case_id ? ` · 案 ${escapeHtml(t.case_id)}` : ""}</p>
        ${quoteHint}
        <p class="muted">${flags}</p>
        <div class="row-actions"></div>`;
      const actions = el.querySelector(".row-actions");
      const stt = t.state || {};
      const isBuyer = S.agentId.startsWith("buyer");
      const selfAck = !!(isBuyer ? stt.buyer_order_ack : stt.supplier_order_ack);
      if (t.kind === "order" && t.status !== "closed" && !stt.cancelled && !selfAck && !stt.docs_sent) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "sec btn-ack";
        b.textContent = "确认订单";
        b.onclick = async () => {
          b.disabled = true;
          try {
            const ack = await proxy(S.agentId, `api/erp/tickets/${t.id}/ack-order`, {});
            await loadTickets();
            await loadMailbox();
            await loadAudit();
            await pollToasts();
            // 双方生效后回对话可见「去询物流」；切页也不丢
            if (S.agentId.startsWith("buyer")) {
              await loadFlow();
              await loadChatHistory();
              const st = (ack && ack.case_state) || (S.flowCase && S.flowCase.state) || "";
              if (st === "LOGISTICS_HINT" || (ack.order && ack.order.effective)) {
                alert("货单已生效。请回到「智能对话」确认是否建立物流单。");
              }
            }
          } catch (e) {
            alert("确认失败：" + (e.message || e));
            b.disabled = false;
          }
        };
        actions.appendChild(b);
        const bCancel = document.createElement("button");
        bCancel.type = "button";
        bCancel.className = "sec";
        bCancel.textContent = "取消订单";
        bCancel.onclick = async () => {
          const reason = prompt("请填写取消理由（必填）");
          if (!reason || !reason.trim()) return;
          try {
            await proxy(S.agentId, `api/erp/tickets/${t.id}/cancel-order`, { reason: reason.trim() });
            await loadTickets();
            await loadAudit();
            await pollToasts();
          } catch (e) {
            alert("取消失败：" + (e.message || e));
          }
        };
        actions.appendChild(bCancel);
      }
      if (t.kind === "logistics_order" && t.status !== "closed" && !stt.cancelled) {
        const selfLogAck = S.agentId.startsWith("buyer")
          ? !!stt.buyer_logistics_ack
          : S.agentId.startsWith("supplier")
            ? !!stt.supplier_logistics_ack
            : !!stt.logistics_agent_ack;
        // 供应侧新链路不再确认物流（工单对端是采购）；仅旧工单保留供应按钮
        const canAckLogistics =
          S.agentId.startsWith("buyer") ||
          S.agentId === "logistics" ||
          S.agentId.startsWith("logistics") ||
          (S.agentId.startsWith("supplier") && !stt.buyer_agent_id && !String(t.peer_agent_id || "").startsWith("buyer"));
        if (!selfLogAck && canAckLogistics) {
          const b = document.createElement("button");
          b.type = "button";
          b.className = "sec btn-ack";
          b.textContent = "确认物流订单";
          b.onclick = async () => {
            b.disabled = true;
            try {
              await proxy(S.agentId, `api/erp/tickets/${t.id}/ack-logistics`, {});
              await loadTickets();
              await loadAudit();
              await pollToasts();
            } catch (e) {
              alert("确认失败：" + (e.message || e));
              b.disabled = false;
            }
          };
          actions.appendChild(b);
          const bCancel = document.createElement("button");
          bCancel.type = "button";
          bCancel.className = "sec";
          bCancel.textContent = "取消物流";
          bCancel.onclick = async () => {
            const reason = prompt("请填写取消物流理由（必填）");
            if (!reason || !reason.trim()) return;
            try {
              await proxy(S.agentId, `api/erp/tickets/${t.id}/cancel-logistics`, { reason: reason.trim() });
              await loadTickets();
              await loadAudit();
            } catch (e) {
              alert("取消失败：" + (e.message || e));
            }
          };
          actions.appendChild(bCancel);
        }
      }
      if (t.status === "open" && t.kind !== "order" && t.kind !== "logistics_order") {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "sec";
        b.textContent = "挂起";
        b.onclick = async () => {
          await proxy(S.agentId, `api/erp/tickets/${t.id}/suspend`, { reason: "用户挂起", state: t.state || {} });
          await loadTickets();
          await loadAudit();
        };
        actions.appendChild(b);
      }
      if (t.status === "suspended") {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "sec";
        b.textContent = "续办";
        b.onclick = async () => {
          await proxy(S.agentId, `api/erp/tickets/${t.id}/resume`, {});
          await loadTickets();
          await loadAudit();
        };
        actions.appendChild(b);
      }
      if (t.status !== "closed" && t.peer_agent_id && t.kind !== "order" && t.kind !== "logistics_order") {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "sec";
        b.textContent = "发电子订单+发票";
        b.onclick = async () => {
          const orderNo = `EO-${Date.now().toString(36).toUpperCase()}`;
          const invNo = `EI-${Date.now().toString(36).toUpperCase()}`;
          await proxy(S.agentId, `api/erp/tickets/${t.id}/send-final-docs`, {
            to_agent: t.peer_agent_id,
            order_doc: { order_no: orderNo, summary: `电子订单 ${orderNo}（工单 ${t.id}）`, ticket_id: t.id },
            invoice_doc: { invoice_no: invNo, summary: `电子发票 ${invNo}（工单 ${t.id}）`, ticket_id: t.id },
          });
          await loadTickets();
          await loadMailbox();
          await loadAudit();
        };
        actions.appendChild(b);
      }
      const bDetail = document.createElement("button");
      bDetail.type = "button";
      bDetail.className = "sec";
      bDetail.textContent = "查看详情";
      bDetail.onclick = () => showTicketDetail(t.id).catch((e) => alert(e.message || e));
      actions.appendChild(bDetail);
      if (t.kind === "order" || t.case_id) {
        const bProv = document.createElement("button");
        bProv.type = "button";
        bProv.className = "sec";
        bProv.textContent = "全链路审计";
        bProv.onclick = () => {
          S.page = "audit";
          showPage();
          openOrderProvenance({ ticket_id: t.id, case_id: t.case_id });
        };
        actions.appendChild(bProv);
      }
      box.appendChild(el);
    }
  }

  async function showTicketDetail(ticketId) {
    const t = await proxy(S.agentId, `api/erp/tickets/${encodeURIComponent(ticketId)}`);
    const st = t.state || {};
    const summary = st.summary || {};
    const flags = t.completion || {};
    openDetailModal(`工单详情 · ${t.title || t.id}`, `
      <div class="kv">
        <span>工单</span><div>${escapeHtml(t.id || "")}</div>
        <span>类型</span><div>${escapeHtml(t.kind || "")}</div>
        <span>状态</span><div>${escapeHtml(t.status || "")}</div>
        <span>采购案</span><div>${escapeHtml(t.case_id || "—")}</div>
        <span>对端</span><div>${escapeHtml(t.peer_agent_id || "—")}</div>
        <span>订单状态</span><div>${escapeHtml(st.order_status || st.phase || "—")}</div>
        <span>买方确认</span><div>${st.buyer_order_ack ? "是" : "否"}</div>
        <span>卖方确认</span><div>${st.supplier_order_ack ? "是" : "否"}</div>
        <span>收妥标志</span><div>订单 ${flags.order_self ? "己" : "·"}${flags.order_peer ? "对" : "·"} / 发票 ${flags.invoice_self ? "己" : "·"}${flags.invoice_peer ? "对" : "·"}</div>
      </div>
      <div class="detail-section">订单摘要</div>
      <div class="kv">
        <span>品名</span><div>${escapeHtml(summary.product_name || "—")}</div>
        <span>数量</span><div>${escapeHtml(String(summary.quantity ?? "—"))}</div>
        <span>单价</span><div>${escapeHtml(String(summary.unit_price ?? "—"))}</div>
        <span>货款</span><div>${escapeHtml(String(summary.goods_total ?? "—"))}</div>
        <span>运费</span><div>${escapeHtml(String(summary.freight ?? "—"))}</div>
      </div>
      <div class="detail-section">工单事件</div>
      <pre>${prettyJson(t.events || [])}</pre>
      <div class="detail-section">完整 state</div>
      <pre>${prettyJson(st)}</pre>
    `);
  }

  function renderProvenanceHtml(p) {
    const chain = (p.code_chain || [])
      .map((n) => {
        const evs = (n.events || [])
          .map((e) => `${(e.at || e.created_at || "").toString().slice(0, 19)} · ${e.event || ""}${e.state ? ` → ${e.state}` : ""}`)
          .join("<br>");
        return `<div class="chain-node ${n.hit ? "hit" : ""}">
          <h5>${escapeHtml(n.title)}${n.platform ? ` · <span class="muted">${escapeHtml(n.platform)}</span>` : ""}${n.hit ? " ✓" : ""}</h5>
          <div class="chain-mods">${(n.modules || []).map((m) => escapeHtml(m)).join("<br>")}</div>
          ${evs ? `<div class="chain-ev">${evs}</div>` : `<div class="chain-ev muted">本阶段暂无落库事件</div>`}
        </div>`;
      })
      .join("");

    const adp = (p.platform && p.platform.adp) || {};
    const amp = (p.platform && p.platform.amp) || {};
    const aip = (p.platform && p.platform.aip_interactions) || [];
    const cands = (adp.candidates || [])
      .map((c) => `${escapeHtml(c.name || c.agent_id || "")} · AIC …${escapeHtml((c.aic || "").slice(-10))} · ${escapeHtml(c.source || "")}`)
      .join("<br>");
    const ampHops = (amp.access || [])
      .slice(0, 20)
      .map((r) => {
        const body = r.body || {};
        const caller = ((body.caller || {}).aic || "").slice(-10);
        const callee = ((body.callee || {}).aic || "").slice(-10);
        const code = ((body.response || {}).statusCode) || "";
        return `<div class="hop-mini">${escapeHtml((r.timestamp || "").slice(0, 19))} · Access ${escapeHtml(caller)} → ${escapeHtml(callee)} · ${escapeHtml(String(code))} · corr ${escapeHtml((r.correlationId || r.correlation_id || "").slice(0, 18))}</div>`;
      })
      .join("");
    const msgHops = (amp.messages || [])
      .slice(0, 20)
      .map((r) => {
        const body = r.body || {};
        return `<div class="hop-mini">${escapeHtml((r.timestamp || "").slice(0, 19))} · Message ${escapeHtml(body.eventType || "")} · ${escapeHtml(body.operationName || "")} · msg ${escapeHtml((body.messageId || "").slice(0, 16))}</div>`;
      })
      .join("");
    const aipHops = aip
      .slice(0, 25)
      .map((r) => {
        return `<div class="hop-mini">${escapeHtml((r.ts || "").slice(0, 19))} · AIP ${escapeHtml(r.direction || "")} · ${escapeHtml((r.req_schema || "") + "")} · task ${escapeHtml((r.task_id || "").slice(0, 16))} · ${escapeHtml(r.state || "")}<br>
          <span class="muted">${escapeHtml((r.from_aic || "").slice(-12))} → ${escapeHtml((r.to_aic || "").slice(-12))}${r.to_url ? ` · ${escapeHtml(r.to_url)}` : ""}</span></div>`;
      })
      .join("");

    const docs = (p.documents || [])
      .map((d) => {
        const doc = (d.attachment && (d.attachment.doc || d.attachment)) || {};
        return `<div class="item clickable" data-mail="${escapeHtml(d.id || "")}">
          <h4>${escapeHtml(d.mail_kind === "e_invoice" ? "电子发票" : "电子订单")} · ${escapeHtml(d.subject || "")}</h4>
          <p class="muted">${escapeHtml(d.folder || "")} · ${(d.created_at || "").slice(0, 19)} · ${escapeHtml(doc.order_no || doc.invoice_no || "")}</p>
        </div>`;
      })
      .join("") || `<p class="muted">暂无关联电子订单/发票</p>`;

    return `
      <div class="kv">
        <span>采购案</span><div>${escapeHtml(p.case_id || "—")}</div>
        <span>工单</span><div>${escapeHtml(p.ticket_id || "—")}</div>
        <span>案状态</span><div>${escapeHtml((p.case && p.case.state) || "—")}</div>
        <span>选定供应商</span><div>${escapeHtml((p.case && p.case.selected_supplier) || (p.ticket && p.ticket.peer_agent_id) || "—")}</div>
      </div>
      <div class="detail-section">代码级成立链路</div>
      ${chain}
      <div class="detail-section">梧桐平台交互</div>
      <div class="plat-block">
        <h5>ADP 发现</h5>
        <p class="muted">来源 ${escapeHtml(adp.source || "—")} · ${escapeHtml(adp.discovery_url || "")} · ${adp.elapsed_ms != null ? adp.elapsed_ms + "ms" : ""}</p>
        <p class="muted">查询：${escapeHtml(adp.query || "—")}</p>
        ${cands ? `<p>${cands}</p>` : `<p class="muted">无候选快照</p>`}
      </div>
      <div class="plat-block">
        <h5>AMP Access / Message（本地日志 · 已上报 Kafka amp.*）</h5>
        <p class="muted">Access ${amp.access_count || 0} · Message ${amp.message_count || 0}</p>
        ${ampHops || `<p class="muted">时间窗内无 Access 记录</p>`}
        ${msgHops ? `<div class="detail-section" style="margin-top:.5rem">Message</div>${msgHops}` : ""}
      </div>
      <div class="plat-block">
        <h5>AIP RPC 交互（本机 interactions）</h5>
        ${aipHops || `<p class="muted">无匹配 AIP 交互</p>`}
      </div>
      <div class="detail-section">电子订单 / 发票</div>
      <div class="list" id="provDocs">${docs}</div>
      <div class="detail-section">采购案 audit</div>
      <pre>${prettyJson((p.case && p.case.audit) || [])}</pre>
      <div class="detail-section">工单事件</div>
      <pre>${prettyJson(p.ticket_events || [])}</pre>
    `;
  }

  async function openOrderProvenance(opts) {
    const q = [];
    if (opts.ticket_id) q.push(`ticket_id=${encodeURIComponent(opts.ticket_id)}`);
    if (opts.case_id) q.push(`case_id=${encodeURIComponent(opts.case_id)}`);
    const panel = $("auditDetail");
    if (panel) {
      panel.classList.remove("hidden");
      panel.innerHTML = `<p class="muted">加载全链路…</p>`;
    }
    try {
      const p = await proxy(S.agentId, `api/erp/order-provenance?${q.join("&")}`);
      if (panel) {
        panel.innerHTML = `<div class="office-toolbar" style="padding:0 0 .5rem"><strong>订单全链路回溯</strong>
          <button type="button" class="sec" id="btnProvClose">收起</button></div>` + renderProvenanceHtml(p);
        const close = $("btnProvClose");
        if (close) close.onclick = () => panel.classList.add("hidden");
        panel.querySelectorAll("[data-mail]").forEach((el) => {
          el.onclick = () => showMailDetail(el.getAttribute("data-mail")).catch((e) => alert(e.message || e));
        });
      }
      document.querySelectorAll("#auditOrderList .item").forEach((el) => {
        el.classList.toggle("active", el.getAttribute("data-tid") === (opts.ticket_id || ""));
      });
    } catch (e) {
      if (panel) panel.innerHTML = `<p class="muted">加载失败：${escapeHtml(e.message || e)}</p>`;
    }
  }

  async function loadAudit() {
    const orderBox = $("auditOrderList");
    if (orderBox) {
      orderBox.innerHTML = "";
      try {
        const list = await proxy(S.agentId, "api/erp/order-provenance/list");
        if (!(list.items || []).length) {
          orderBox.innerHTML = `<p class="muted">暂无订单可回溯</p>`;
        } else {
          for (const it of list.items) {
            const el = document.createElement("div");
            el.className = "item clickable";
            el.setAttribute("data-tid", it.ticket_id || "");
            el.innerHTML = `<h4>${escapeHtml(it.title || it.ticket_id || "")} <span class="muted">${escapeHtml(it.status || "")}</span></h4>
              <p class="muted">${escapeHtml(it.ticket_id || "")}${it.case_id ? ` · 案 ${escapeHtml(it.case_id)}` : ""} · ${escapeHtml(it.peer_agent_id || "")}
              · ${(it.updated_at || "").slice(0, 19)}</p>
              <div class="row-actions"><button type="button" class="sec">查看代码级全链路 + 梧桐交互</button></div>`;
            el.onclick = () => openOrderProvenance({ ticket_id: it.ticket_id, case_id: it.case_id });
            orderBox.appendChild(el);
          }
        }
      } catch (e) {
        orderBox.innerHTML = `<p class="muted">订单列表失败：${escapeHtml(e.message || e)}</p>`;
      }
    }

    const box = $("auditList");
    if (!box) return;
    box.innerHTML = `<div class="detail-section">工单事件时间线</div>`;
    let office = { items: [] };
    try {
      office = await proxy(S.agentId, "api/erp/office-audit");
    } catch (_) { /* ignore */ }
    let legacy = { items: [] };
    try {
      legacy = await proxy(S.agentId, "api/erp/audit-tasks");
    } catch (_) { /* ignore */ }
    for (const e of office.items || []) {
      const el = document.createElement("div");
      el.className = "item";
      el.innerHTML = `<h4>${escapeHtml(e.event || "")} · ${escapeHtml(e.ticket_title || e.ticket_id || "")}</h4>
        <p class="muted">${escapeHtml(e.ticket_status || "")} · ${(e.created_at || "").slice(0, 19)} · ${escapeHtml(e.actor || "")}</p>`;
      box.appendChild(el);
    }
    for (const t of legacy.items || []) {
      const el = document.createElement("div");
      el.className = "item";
      el.innerHTML = `<h4>${escapeHtml(t.title || "")}</h4><p class="muted">${escapeHtml(t.kind || "")} · ${escapeHtml(t.status || "")}<br>${(t.created_at || "").slice(0, 19)}</p>`;
      box.appendChild(el);
    }
    if (box.children.length <= 1) {
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = "暂无事件时间线";
      box.appendChild(p);
    }
  }

  function merchantCardHtml(m) {
    if (!m || !m.trade_name) return "";
    const loc = [m.province, m.city].filter(Boolean).join(" · ");
    const ship = m.ship_from_city
      ? `发货地 ${m.ship_from_city}`
      : m.ship_to_city
        ? `收货地 ${m.ship_to_city}`
        : "";
    return `<div class="card"><strong>商家信息</strong>
      <p>${escapeHtml(m.trade_name)}</p>
      <p class="muted">${escapeHtml(loc)}${m.postal_code ? ` · ${escapeHtml(m.postal_code)}` : ""}</p>
      <p class="muted">${escapeHtml(m.address || "")}</p>
      ${ship ? `<p class="muted">${escapeHtml(ship)}</p>` : ""}</div>`;
  }

  async function loadWorkbench() {
    let merchant = null;
    try {
      merchant = await proxy(S.agentId, "api/erp/merchant");
    } catch (_) { /* ignore */ }
    if (isSupplierAgent()) {
      let sum = {};
      try {
        sum = await proxy(S.agentId, "api/erp/workbench-summary");
      } catch (_) { /* ignore */ }
      const notes = await proxy(S.agentId, "api/erp/notifications?unread_only=true").catch(() => ({ items: [] }));
      $("workbench").innerHTML = `
        ${merchantCardHtml(merchant)}
        <div class="card"><strong>未读通知</strong><p class="muted">${(notes.items || []).length || sum.unread_notifications || 0} 条</p></div>
        <div class="card"><strong>待确认销售订单</strong><p class="muted">${sum.order_pending || 0} 单</p></div>
        <div class="card"><strong>待确认物流工单</strong><p class="muted">${sum.logistics_pending || 0} 单</p></div>
        <div class="card"><strong>价目 / 询价箱</strong><p class="muted">${sum.catalog_count || 0} SKU · ${sum.inbox_count || 0} 询价</p></div>`;
      return;
    }
    const notes = await proxy(S.agentId, "api/erp/notifications?unread_only=true");
    const inv = await proxy(S.agentId, "api/erp/inventory");
    const low = (inv.items || []).filter((i) => i.low);
    $("workbench").innerHTML = `
      ${merchantCardHtml(merchant)}
      <div class="card"><strong>未读通知</strong><p class="muted">${(notes.items || []).length} 条</p></div>
      <div class="card"><strong>低于安全库存</strong><p class="muted">${low.map((i) => i.name).join("、") || "无"}</p></div>`;
  }

  async function loadCatalog() {
    if (!S.agentId.startsWith("supplier")) return;
    let data = { items: [] };
    try {
      data = await proxy(S.agentId, "api/erp/catalog");
    } catch (_) { /* v2 缺路由时不阻断 */ }
    let merchant = null;
    try {
      merchant = await proxy(S.agentId, "api/erp/merchant");
    } catch (_) { /* ignore */ }
    const head = merchantCardHtml(merchant);
    const box = $("catalogTable");
    if (!box) return;
    box.innerHTML =
      (head ? `<div class="cards" style="margin-bottom:.75rem">${head}</div>` : "") +
      table(
        ["编码", "名称", "挂牌价", "库存", "策略", "MOQ"],
        (data.items || []).map((i) => [
          i.code || i.sku,
          i.name,
          i.list_price,
          i.on_hand,
          i.strategy_tag,
          i.moq,
        ])
      );
  }

  async function loadInbox() {
    if (!S.agentId.startsWith("supplier")) return;
    let data = { items: [] };
    try {
      data = await proxy(S.agentId, "api/erp/rfq-inbox");
    } catch (_) { /* v2 缺路由时不阻断 */ }
    const box = $("inboxTable");
    if (!box) return;
    box.innerHTML = table(
      ["ID", "物料", "数量", "状态", "时间"],
      (data.items || []).map((i) => [i.id, i.material_code, i.qty, i.status, (i.created_at || "").slice(0, 19)])
    );
  }

  function peerLabel(aic, url) {
    const s = String(aic || "");
    const u = String(url || "");
    if (u.includes(":8011") || s.includes("WP4OOG") || s.includes("NH4J42")) return "供应商A";
    if (u.includes(":8013") || s.includes("6CW2XR") || s.includes("SHDUXP")) return "供应商B";
    if (u.includes(":8014") || s.includes("1VQMIO") || s.includes("8R39K3")) return "供应商C";
    if (u.includes(":8015") || s.includes("JOBNF9") || s.includes("ZBD999")) return "物流";
    if (s.includes("IFL6BJ") || s.includes("L18AT6") || s.includes("ODIFWZ") || s.includes("21P09A")) return "采购";
    if (!s) return "伙伴";
    const parts = s.split(".");
    return parts.length > 1 ? `Agent·${parts[parts.length - 2]}` : s.slice(-10);
  }

  function schemaLabel(schema) {
    const m = {
      "agentlink.quote_request": "询价请求",
      "agentlink.initial_quote": "初轮报价",
      "agentlink.bargain_round": "议价",
      "agentlink.bargain_offer": "议价回复",
      "agentlink.blind_bid": "匿名竞价",
      "agentlink.blind_bid_offer": "竞价出价",
      "agentlink.shipping_request": "物流询价",
      "agentlink.shipping_quote": "运费报价",
      "agentlink.contract_ack": "合同确认",
      "agentlink.order_contract": "合同",
    };
    return m[schema] || schema || "AIP";
  }

  function setCollabPanels(headHtml, timelineHtml) {
    const head = $("collabHead");
    const timeline = $("collabTimeline");
    const box = $("rightAudit");
    if (head && timeline) {
      head.innerHTML = headHtml || "";
      timeline.innerHTML = timelineHtml || "";
      return;
    }
    if (box) box.innerHTML = (headHtml || "") + (timelineHtml || "");
  }

  async function loadCollab() {
    const agentsBox = $("collabAgents");
    if (isSupplierAgent() || S.isSupplierDomain) {
      if (agentsBox) agentsBox.innerHTML = `<span class="collab-pill">供应协同</span><span class="collab-pill">物流</span>`;
      try {
        const tickets = await proxy(S.agentId, "api/erp/tickets?status=open");
        const items = tickets.items || [];
        if (!items.length) {
          setCollabPanels("", `<p class="muted">暂无待办工单</p>`);
          return;
        }
        setCollabPanels("", items.slice(0, 8).map((t) =>
          `<div class="hop"><strong>${escapeHtml(t.kind || "")}</strong> · ${escapeHtml(t.title || t.id)}
           <div class="muted">${escapeHtml((t.state || {}).order_status || (t.state || {}).logistics_status || t.status || "")}</div></div>`
        ).join(""));
      } catch (_) {
        setCollabPanels("", `<p class="muted">暂无记录</p>`);
      }
      return;
    }
    if (agentsBox && S.domain?.agents) {
      agentsBox.innerHTML = S.domain.agents.map((a) =>
        `<span class="collab-pill" data-id="${a.id}">${escapeHtml(a.title)}</span>`
      ).join("");
    }
    const c = S.flowCase;
    let items = [];
    try {
      const bid = c?.case_id ? `&business_id=${encodeURIComponent(c.case_id)}` : "";
      const data = await api(`/api/agents/${S.agentId}/interactions?limit=36${bid}`);
      items = data.items || [];
    } catch (_) {
      items = [];
    }
    let head = "";
    if (c) {
      const h = c.hitl_pending;
      const hitl = h?.prompt || "无待确认";
      const phase = h?.phase || h?.gate || "—";
      const dec = (h?.decisions || []).join(" / ") || "approve / edit / reject / respond";
      const meta = c.discovery_meta || {};
      const srcBadge = meta.degrade
        ? `<span class="src-badge degrade">容灾 · ${escapeHtml(meta.source || "local")}</span>`
        : meta.source
          ? `<span class="src-badge platform">平台 · ${escapeHtml(meta.source)}</span>`
          : "";
      head = `<div class="collab-case"><strong>${escapeHtml(c.case_id)}</strong> · ${escapeHtml(c.state)} · 阶段 ${escapeHtml(phase)}
        ${srcBadge}
        <div class="muted">HITL：${escapeHtml(hitl)}</div>
        <div class="muted">可用决策：${escapeHtml(dec)}${h?.hint ? ` · ${escapeHtml(h.hint)}` : ""}</div>
        ${c.voided ? `<div class="muted voided">已作废（reject）</div>` : ""}</div>`;
    }
    let metricsHtml = "";
    try {
      const m = await proxy(S.agentId, "api/flow/metrics");
      const k = m.kpi || {};
      metricsHtml = `<div class="metrics-strip">
        <span>AMP访问 ${k.access ?? 0}</span>
        <span>消息 ${k.messages ?? 0}</span>
        <span>任务 ${k.tasks ?? 0}</span>
        <span>成功率 ${k.success_rate_pct ?? 0}%</span>
      </div>`;
    } catch (_) { /* ignore */ }
    if (!items.length) {
      setCollabPanels(head + metricsHtml, `<p class="muted">暂无协作记录</p>`);
      return;
    }
    const parsed = items.map((row) => {
      const tms = Date.parse(row.ts || "") || 0;
      return { row, tms };
    });
    const hops = parsed.map((item, idx) => {
      const row = item.row;
      const inbound = row.direction === "inbound";
      const peer = inbound
        ? peerLabel(row.from_aic, row.to_url)
        : peerLabel(row.to_aic, row.to_url);
      const dir = inbound ? "←" : "→";
      const schema = schemaLabel(row.req_schema || row.res_schema);
      const ts = (row.ts || "").replace("T", " ").slice(11, 19);
      const state = row.state || "";
      const ok = /complet|accept|ok|success|awaiting-completion/i.test(state) || state === "";
      const stCls = ok ? "hop-ok" : "hop-warn";
      const tid = row.task_id ? String(row.task_id).slice(0, 12) : "";
      const left = inbound ? peer : "Leader·采购A";
      const right = inbound ? "Leader·采购A" : peer;
      let dur = "";
      if (idx < parsed.length - 1 && item.tms && parsed[idx + 1].tms) {
        const ms = Math.abs(item.tms - parsed[idx + 1].tms);
        if (ms < 600000) dur = ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
      }
      return `<div class="collab-hop">
        <div class="collab-hop-top"><span class="collab-dir">${dir}</span>
          <strong>${escapeHtml(left)}</strong> ${dir} <strong>${escapeHtml(right)}</strong>
          <span class="hop-action">${escapeHtml(schema)}</span>
          <span class="muted">${escapeHtml(ts)}${dur ? ` · ${dur}` : ""}</span></div>
        <div class="muted"><span class="${stCls}">${escapeHtml(state || "ok")}</span>${tid ? ` · task ${escapeHtml(tid)}` : ""}</div>
      </div>`;
    }).join("");
    setCollabPanels(
      head + metricsHtml,
      `<div class="collab-title">AIP 协作时间线（角色 · 动作 · 状态 · 耗时）</div>${hops}`
    );
  }

  function renderRight() {
    loadCollab().catch(() => {
      setCollabPanels("", `<p class="muted">协作面板加载失败</p>`);
    });
  }

  function table(headers, rows) {
    return `<table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function isMdTableRow(line) {
    const t = String(line || "").trim();
    return t.startsWith("|") && t.includes("|", 1);
  }

  function isMdTableSep(line) {
    const t = String(line || "").trim();
    if (!t.startsWith("|")) return false;
    return /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(t);
  }

  function splitMdRow(line) {
    let t = String(line || "").trim();
    if (t.startsWith("|")) t = t.slice(1);
    if (t.endsWith("|")) t = t.slice(0, -1);
    return t.split("|").map((c) => c.trim());
  }

  function formatInlineMd(escaped) {
    return escaped
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
  }

  function formatCellHtml(cell) {
    const raw = String(cell ?? "");
    let html = formatInlineMd(escapeHtml(raw));
    if (/缺料|无可用|不足/.test(raw)) {
      html = `<span class="cell-bad">${html}</span>`;
    } else if (/低于安全线|偏低|告警/.test(raw)) {
      html = `<span class="cell-warn">${html}</span>`;
    } else if (/充足|正常|达标/.test(raw)) {
      html = `<span class="cell-ok">${html}</span>`;
    }
    return html;
  }

  function mdTableToHtml(headerLine, bodyLines) {
    const headers = splitMdRow(headerLine);
    const rows = bodyLines.map(splitMdRow).filter((r) => r.some((c) => c !== ""));
    const thead = `<thead><tr>${headers.map((h) => `<th>${formatInlineMd(escapeHtml(h))}</th>`).join("")}</tr></thead>`;
    const tbody = `<tbody>${rows.map((r) => {
      const cells = headers.map((_, i) => formatCellHtml(r[i] ?? ""));
      return `<tr>${cells.map((c) => `<td>${c}</td>`).join("")}</tr>`;
    }).join("")}</tbody>`;
    return `<div class="md-table"><table>${thead}${tbody}</table></div>`;
  }

  /** 轻量渲染：GFM 表格 + 粗体/行内代码，其余转义。 */
  function formatChatHtml(src) {
    const lines = String(src || "").replace(/\r\n/g, "\n").split("\n");
    const out = [];
    let i = 0;
    while (i < lines.length) {
      if (isMdTableRow(lines[i]) && i + 1 < lines.length && isMdTableSep(lines[i + 1])) {
        const header = lines[i];
        i += 2;
        const body = [];
        while (i < lines.length && isMdTableRow(lines[i])) {
          body.push(lines[i]);
          i += 1;
        }
        out.push(mdTableToHtml(header, body));
        continue;
      }
      const textLines = [];
      while (i < lines.length) {
        if (isMdTableRow(lines[i]) && i + 1 < lines.length && isMdTableSep(lines[i + 1])) break;
        textLines.push(lines[i]);
        i += 1;
      }
      const block = textLines.join("\n").replace(/\n+$/, "");
      if (block.trim()) {
        out.push(`<div class="md-text">${formatInlineMd(escapeHtml(block)).replace(/\n/g, "<br>")}</div>`);
      } else if (textLines.length) {
        out.push("<div class=\"md-gap\"></div>");
      }
    }
    return out.join("") || "";
  }

  function setBubbleContent(bubble, text, extraHtml) {
    bubble.innerHTML = `${formatChatHtml(text)}${extraHtml || ""}`;
  }

  function appendChatMsg(role, content, extraHtml) {
    const box = $("chatMsgs");
    const empty = box.querySelector(".msg.ai .bubble");
    if (box.children.length === 1 && empty && /^你好，我是.+助手。?$/.test((empty.textContent || "").trim())) {
      box.innerHTML = "";
    }
    const el = document.createElement("div");
    el.className = "msg " + (role === "user" ? "user" : "ai");
    const body = role === "user" ? escapeHtml(content || "") : formatChatHtml(content || "");
    el.innerHTML = `<div class="bubble">${body}${extraHtml || ""}</div>`;
    box.appendChild(el);
    box.scrollTop = box.scrollHeight;
    return el.querySelector(".bubble");
  }

  function appendAiShell() {
    const box = $("chatMsgs");
    const empty = box.querySelector(".msg.ai .bubble");
    if (box.children.length === 1 && empty && /^你好，我是.+助手。?$/.test((empty.textContent || "").trim())) {
      box.innerHTML = "";
    }
    const el = document.createElement("div");
    el.className = "msg ai";
    el.innerHTML = `
      <div class="think-trail" hidden>
        <button type="button" class="think-toggle" aria-expanded="true">
          <span class="think-toggle-label">处理中</span>
          <span class="think-toggle-meta"></span>
        </button>
        <ol class="think-steps"></ol>
      </div>
      <div class="bubble streaming"></div>`;
    box.appendChild(el);
    box.scrollTop = box.scrollHeight;
    const trail = el.querySelector(".think-trail");
    const steps = el.querySelector(".think-steps");
    const toggle = el.querySelector(".think-toggle");
    const bubble = el.querySelector(".bubble");
    toggle.onclick = () => {
      const open = !trail.classList.contains("collapsed");
      trail.classList.toggle("collapsed", open);
      toggle.setAttribute("aria-expanded", open ? "false" : "true");
    };
    return { el, trail, steps, toggle, bubble };
  }

  function pushThinkStep(ui, text, phase) {
    if (!text) return;
    ui.trail.hidden = false;
    const last = ui.steps.querySelector(".think-step:last-child");
    if (last && last.dataset.text === text) return;
    if (last) {
      last.classList.remove("active");
      last.classList.add("done");
      const mark = last.querySelector(".think-mark");
      if (mark) mark.textContent = "✓";
    }
    const li = document.createElement("li");
    li.className = "think-step active";
    li.dataset.text = text;
    li.dataset.phase = phase || "";
    li.innerHTML = `<span class="think-mark">●</span><span class="think-text">${escapeHtml(text)}</span>`;
    ui.steps.appendChild(li);
    const n = ui.steps.children.length;
    ui.toggle.querySelector(".think-toggle-label").textContent = text;
    ui.toggle.querySelector(".think-toggle-meta").textContent = `${n} 步`;
    $("chatMsgs").scrollTop = $("chatMsgs").scrollHeight;
  }

  function finishThinkTrail(ui, ok) {
    const last = ui.steps.querySelector(".think-step.active");
    if (last) {
      last.classList.remove("active");
      last.classList.add(ok ? "done" : "err");
      const mark = last.querySelector(".think-mark");
      if (mark) mark.textContent = ok ? "✓" : "!";
    }
    const n = ui.steps.children.length;
    if (n) {
      ui.toggle.querySelector(".think-toggle-label").textContent = ok ? "处理轨迹" : "处理中断";
      ui.toggle.querySelector(".think-toggle-meta").textContent = `${n} 步`;
      // 保留展开，便于回看本轮动作；用户仍可手动收起
      ui.trail.classList.remove("collapsed");
      ui.toggle.setAttribute("aria-expanded", "true");
      ui.trail.hidden = false;
    }
  }

  async function sendChatText(text) {
    text = (text || "").trim();
    if (!text) return;
    if (workspaceOf() !== "chat") {
      alert(`「${agentTitle()}」暂无对话工作区`);
      return;
    }
    if ($("btnSend").disabled) return;
    $("chatText").value = "";
    $("btnSend").disabled = true;
    appendChatMsg("user", text);
    const ui = appendAiShell();
    const bubble = ui.bubble;
    let reply = "";
    let startedReply = false;
    pushThinkStep(ui, "正在理解你的意图…", "think");
    try {
      const r = await fetch(`/api/proxy/${S.agentId}/api/erp/chat/stream`, {
        method: "POST",
        headers: { "content-type": "application/json", accept: "text/event-stream" },
        body: JSON.stringify({ text, thread_id: S.threadId }),
      });
      if (!r.ok) {
        const t = await r.text();
        throw new Error(t || `HTTP ${r.status}`);
      }
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() || "";
        for (const part of parts) {
          const line = part.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          let ev;
          try { ev = JSON.parse(line.slice(5).trim()); } catch { continue; }
          if (ev.type === "token") {
            if (!startedReply) {
              pushThinkStep(ui, "正在输出回复…", "reply");
              startedReply = true;
            }
            reply += ev.text || "";
            setBubbleContent(bubble, reply);
            bubble.classList.add("streaming");
            $("chatMsgs").scrollTop = $("chatMsgs").scrollHeight;
          } else if (ev.type === "status") {
            pushThinkStep(ui, ev.text || ev.message || "…", ev.phase || "status");
          } else if (ev.type === "done" || ev.type === "final") {
            if (ev.type === "final" && reply && (ev.reply || ev.message) === reply) {
              // final 与 done 重复时跳过二次收尾
              continue;
            }
            if (ev.thread_id) S.threadId = ev.thread_id;
            reply = ev.reply || ev.message || reply;
            let extra = "";
            if (ev.ui_widgets) {
              const bubbleWidgets = (ev.ui_widgets || []).filter((w) => w.kind !== "choice_actions");
              extra += renderUiWidgets(bubbleWidgets, { interactive: false });
              const choiceW = (ev.ui_widgets || []).find((w) => w.kind === "choice_actions");
              if (choiceW && !(shortlistStillPending() && candidatesFromCase().length)) {
                if (auctionWatchActive() && $("auctionWatch")) {
                  if (choiceW.choices?.length) {
                    S.flowCase = S.flowCase || {};
                    S.flowCase.pending_choices = choiceW;
                  }
                  renderAuctionWatch();
                } else {
                  const dock = $("choiceDock");
                  if (dock) {
                    dock.innerHTML = renderChoiceActions(choiceW, { interactive: true });
                    dock.classList.remove("hidden");
                    bindChoiceActions(dock);
                  }
                }
              }
            }
            if (ev.data) extra += renderQuoteCard(ev.data);
            if (extra && reply.includes("报价明细：")) {
              reply = reply.split("报价明细：")[0].trim();
            }
            if (ev.case_id) {
              S.flowCaseId = ev.case_id;
              saveAgentFlow();
              extra += `<div class="muted case-chip">采购案 ${escapeHtml(ev.case_id)} · ${escapeHtml(ev.case_state || "")}</div>`;
            }
            if (ev.case) {
              S.flowCase = ev.case;
              if (ev.case.group_room || ev.open_group_room) maybeOpenGroupRoom(ev.case, { force: true });
            } else if (ev.group_room) {
              S.flowCase = S.flowCase || {};
              S.flowCase.group_room = ev.group_room;
              S.flowCase.state = ev.case_state || S.flowCase.state;
              maybeOpenGroupRoom(S.flowCase, { force: true });
            }
            setBubbleContent(bubble, reply, extra);
            finishThinkTrail(ui, true);
          } else if (ev.type === "error") {
            bubble.textContent = ev.message || "对话失败";
            finishThinkTrail(ui, false);
          }
        }
      }
      if (!reply && !(bubble.textContent || "").trim()) setBubbleContent(bubble, "（无回复）");
      if (ui.steps.querySelector(".think-step.active")) finishThinkTrail(ui, !!reply);
      await loadNotifications();
      await loadTickets();
      await loadMailbox();
      await loadAudit();
      await pollToasts();
      // 禁止用「全库最新案」覆盖本窗 case（会串物料主体）
      await loadFlow();
      await loadCollab();
      await loadThreads(); // 刷新标题（首条用户消息会改名）
      await loadChatHistory(); // 从线程历史回放（含轨迹）
    } catch (e) {
      bubble.textContent = "失败：" + (e.message || e);
      finishThinkTrail(ui, false);
    } finally {
      bubble.classList.remove("streaming");
      $("btnSend").disabled = false;
    }
  }

  async function sendChat() {
    await sendChatText($("chatText").value);
  }

  document.querySelectorAll(".nav").forEach((b) => {
    b.onclick = async () => {
      S.page = b.dataset.page;
      showPage();
      if (S.page === "chat") {
        // 切回对话必须回灌线程历史，否则只剩欢迎语
        try {
          await loadThreads();
          await loadFlow();
          await loadChatHistory();
          await loadCollab();
        } catch (_) { /* ignore */ }
      }
      if (S.page === "history") {
        try { await loadChatHistory(); } catch (_) { /* ignore */ }
      }
      if (S.page === "mailbox") loadMailbox();
      if (S.page === "tickets") loadTickets();
      if (S.page === "audit") loadAudit();
      if (S.page === "notify") loadNotifications();
      if (S.page === "workbench") loadWorkbench();
    };
  });
  if ($("btnSend")) $("btnSend").onclick = sendChat;
  if ($("chatText")) {
    $("chatText").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
    });
  }
  if ($("mailFolder")) $("mailFolder").onchange = () => loadMailbox();
  if ($("btnMailRefresh")) $("btnMailRefresh").onclick = () => loadMailbox();
  if ($("ticketFilter")) $("ticketFilter").onchange = () => loadTickets();
  if ($("btnTicketRefresh")) $("btnTicketRefresh").onclick = () => loadTickets();
  if ($("btnAuditRefresh")) $("btnAuditRefresh").onclick = () => loadAudit();
  if ($("detailClose")) $("detailClose").onclick = closeDetailModal;
  if ($("detailBackdrop")) $("detailBackdrop").onclick = closeDetailModal;
  if ($("groupRoomClose")) $("groupRoomClose").onclick = closeGroupRoom;
  if ($("groupRoomBackdrop")) $("groupRoomBackdrop").onclick = closeGroupRoom;
  if ($("groupRoomReopenBtn")) $("groupRoomReopenBtn").onclick = openGroupRoomFromChip;
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeGroupRoom();
      closeDetailModal();
    }
  });
  if ($("btnTicketNew")) {
    $("btnTicketNew").onclick = async () => {
      const title = prompt("工单标题", `${agentTitle()} 采购协作工单`);
      if (!title) return;
      const peer = prompt("对端智能体 id（如 supplier-a / buyer-a）", S.agentId.startsWith("buyer") ? "supplier-a" : "buyer-a");
      await proxy(S.agentId, "api/erp/tickets", {
        title,
        kind: "procurement",
        peer_agent_id: peer || null,
        state: { note: "新建待办", at: new Date().toISOString() },
      });
      S.page = "tickets";
      showPage();
      await loadTickets();
      await loadAudit();
    };
  }
  if ($("threadCurrent")) {
    $("threadCurrent").onclick = (e) => {
      e.stopPropagation();
      const menu = $("threadMenu");
      const btn = $("threadCurrent");
      if (!menu || !btn) return;
      const open = menu.classList.toggle("hidden") === false;
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    };
  }
  document.addEventListener("click", (e) => {
    const picker = $("threadPicker");
    if (picker && !picker.contains(e.target)) closeThreadMenu();
  });
  if ($("btnNewThread")) $("btnNewThread").onclick = () => newThread();

  loadDomain().catch((e) => alert("加载失败: " + e.message));
  setInterval(() => refreshHealth().catch(() => {}), 8000);
  setInterval(() => {
    if (S.isSupplierDomain || S.page !== "chat") return;
    loadCollab().catch(() => {});
    // 竞价/组群进行中定期拉案
    if (S.flowCaseId && ["BIDDING", "GROUP_BIDDING", "GROUP_DECIDE"].includes(S.flowCase?.state)) {
      loadFlow().catch(() => {});
    }
  }, 4000);
  setInterval(() => {
    pollToasts().catch(() => {});
    if (S.page === "tickets") loadTickets().catch(() => {});
    if (S.page === "mailbox") loadMailbox().catch(() => {});
  }, 5000);
})();
