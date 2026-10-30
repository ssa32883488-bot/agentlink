(async () => {
  const grid = document.getElementById("grid");
  const tip = document.getElementById("tip");
  try {
    const r = await fetch("/api/products");
    const data = await r.json();
    if (!r.ok) throw new Error(JSON.stringify(data));
    grid.innerHTML = "";
    for (const p of data.items || []) {
      const card = document.createElement("article");
      card.className = "card";
      card.innerHTML = `
        <h3>${p.name}</h3>
        <p class="desc">${p.description || ""}</p>
        <div class="price">¥ ${Number(p.price).toFixed(0)}</div>
        <label>数量 <input type="number" min="1" max="500" value="20" data-sku="${p.sku}" /></label>
        <button type="button" class="buy" data-buy="${p.sku}">立即购买</button>`;
      grid.appendChild(card);
    }
    grid.querySelectorAll("[data-buy]").forEach((btn) => {
      btn.onclick = async () => {
        const sku = btn.getAttribute("data-buy");
        const qty = Number(grid.querySelector(`input[data-sku="${sku}"]`).value || 1);
        btn.disabled = true;
        try {
          const res = await fetch("/api/orders", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ sku, qty, customer_name: "C端用户" }),
          });
          const body = await res.json();
          if (!res.ok) throw new Error(body.detail || JSON.stringify(body));
          tip.textContent =
            `下单成功：${body.order_id}。` +
            (body.notification
              ? "原料不足已通知采购商A运营，请到后台处理。"
              : "库存充足，未触发原料告警。");
          tip.style.color = "#047857";
          alert(
            `订单 ${body.order_id} 已创建\n` +
              (body.notification ? body.notification.title : "未触发缺料告警")
          );
        } catch (e) {
          alert("下单失败：" + e.message);
        } finally {
          btn.disabled = false;
        }
      };
    });
  } catch (e) {
    grid.innerHTML = `<p class="err">商城加载失败：${e.message}<br>请确认采购商A(:8010)已启动。</p>`;
  }
})();
