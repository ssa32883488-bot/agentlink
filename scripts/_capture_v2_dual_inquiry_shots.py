# -*- coding: utf-8 -*-
"""commerce_v2 两种询价方式：浏览器全流程截图 + 处理轨迹日志。

路径 A 普通询价：需求 → 短名单 → 确认并询价 → 报价/决策
路径 B 组群竞价：需求 → 我要组群竞价 → 勾选入群 → 聊天室汇总 → 选方案

输出：docs/evidence/verify_ui_shots/v2_dual_<run_id>/
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = ROOT / "docs" / "evidence" / "verify_ui_shots" / f"v2_dual_{RUN_ID}"
SHOT = OUT / "screenshots"
LOGS = OUT / "logs"
SHOT.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)

BUYER_URL = os.environ.get("BUYER_UI_URL", "https://ashui.online:8090/")
Q_DEMAND = "帮我采购500脚轮和400坐垫"


def launch_browser(p):
    last = None
    for kw in (
        {"channel": "chrome", "headless": True},
        {"channel": "msedge", "headless": True},
        {"headless": True},
    ):
        try:
            return p.chromium.launch(
                **kw,
                args=["--proxy-server=direct://", "--no-proxy-server", "--ignore-certificate-errors"],
            )
        except Exception as e:  # noqa: BLE001
            last = e
            print("LAUNCH_FAIL", kw, str(e)[:160], flush=True)
    raise RuntimeError(f"cannot launch browser: {last}")


class Capturer:
    def __init__(self, browser) -> None:
        self.browser = browser
        self.n = 0
        self.steps: list[dict] = []
        self.ctx = None
        self.page = None

    def dismiss_group_room(self) -> None:
        """收起可能从上次会话恢复出来的组群聊天室遮罩。"""
        page = self.page
        assert page
        try:
            page.evaluate(
                """() => {
                  const m = document.getElementById('groupRoomModal');
                  if (m) m.classList.add('hidden');
                  try {
                    const S = window; // no-op; app state is inside IIFE
                  } catch (e) {}
                }"""
            )
        except Exception:
            pass
        close_btn = page.locator("#groupRoomClose")
        if close_btn.count():
            try:
                close_btn.first.click(timeout=2000, force=True)
            except Exception:
                pass
        page.wait_for_timeout(300)

    def open(self) -> None:
        if self.ctx:
            self.ctx.close()
        self.ctx = self.browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        self.page = self.ctx.new_page()
        self.page.goto(BUYER_URL, wait_until="domcontentloaded", timeout=90_000)
        self.page.wait_for_timeout(1200)
        # 清掉本地恢复的案/线程，避免旧组群弹窗挡点击
        try:
            self.page.evaluate(
                """() => {
                  try { localStorage.clear(); sessionStorage.clear(); } catch (e) {}
                }"""
            )
            self.page.reload(wait_until="domcontentloaded", timeout=90_000)
            self.page.wait_for_timeout(1000)
        except Exception:
            pass
        self.dismiss_group_room()
        nav = self.page.locator('button.nav[data-page="chat"]')
        if nav.count():
            try:
                nav.first.click(timeout=5000, force=True)
            except Exception:
                nav.first.click(force=True)
            self.page.wait_for_timeout(600)
        self.dismiss_group_room()
        if self.page.locator("#btnNewThread").count():
            self.page.locator("#btnNewThread").click(force=True, timeout=15_000)
            self.page.wait_for_timeout(700)
        self.dismiss_group_room()

    def close(self) -> None:
        if self.ctx:
            self.ctx.close()
            self.ctx = None
            self.page = None

    def _dump_logs(self, label: str) -> dict:
        page = self.page
        assert page
        data = page.evaluate(
            """() => {
              const trails = [];
              document.querySelectorAll('.think-trail, .think-panel, .assistant-bubble').forEach((el, i) => {
                const steps = [...el.querySelectorAll('.think-step')].map(s => ({
                  text: (s.dataset.text || s.textContent || '').trim(),
                  phase: s.dataset.phase || '',
                  cls: s.className || '',
                })).filter(x => x.text);
                const reply = (el.querySelector('.bubble, .msg-body, .assistant-text') || el).innerText || '';
                if (steps.length || (reply && reply.length > 8)) {
                  trails.push({ i, steps, reply: reply.slice(0, 4000) });
                }
              });
              // 兜底：聊天区全部文本
              const chat = (document.querySelector('#chatMsgs') || {}).innerText || '';
              const flow = (document.querySelector('#flowCaseLabel') || {}).innerText || '';
              const shortlist = (document.querySelector('#shortlistDock') || {}).innerText || '';
              const choice = (document.querySelector('#choiceDock') || {}).innerText || '';
              const room = (document.querySelector('#groupRoomModal') || {});
              const roomHidden = room.classList ? room.classList.contains('hidden') : true;
              const roomText = roomHidden ? '' : ((room.innerText || '').slice(0, 6000));
              const roomMeta = (document.querySelector('#groupRoomMeta') || {}).innerText || '';
              return { trails, chat: chat.slice(0, 12000), flow, shortlist: shortlist.slice(0, 3000),
                       choice: choice.slice(0, 2000), roomMeta, roomText, roomOpen: !roomHidden };
            }"""
        )
        path = LOGS / f"{self.n:02d}_{label}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        # 可读摘要
        md = LOGS / f"{self.n:02d}_{label}.md"
        lines = [f"# {label}", "", f"- flow: `{data.get('flow')}`", f"- roomOpen: {data.get('roomOpen')}", ""]
        if data.get("roomMeta"):
            lines += [f"- room: `{data.get('roomMeta')}`", ""]
        for t in data.get("trails") or []:
            lines.append("## 处理轨迹")
            for s in t.get("steps") or []:
                lines.append(f"- {s.get('text')}")
            if t.get("reply"):
                lines.append("")
                lines.append("### 回复摘录")
                lines.append("```")
                lines.append((t.get("reply") or "")[:2500])
                lines.append("```")
            lines.append("")
        if data.get("shortlist"):
            lines += ["## 短名单/组群面板", "```", data["shortlist"][:2000], "```", ""]
        if data.get("choice"):
            lines += ["## 决策按钮", "```", data["choice"][:1500], "```", ""]
        if data.get("roomText"):
            lines += ["## 组群聊天室", "```", data["roomText"][:3500], "```", ""]
        md.write_text("\n".join(lines), encoding="utf-8")
        return data

    def shot(self, label: str, *, note: str = "", chat: str = "") -> Path:
        self.n += 1
        name = f"{self.n:02d}_{label}.png"
        path = SHOT / name
        err = None
        try:
            self.page.screenshot(path=str(path), full_page=True)
        except Exception as e:  # noqa: BLE001
            err = str(e)
            try:
                self.page.screenshot(path=str(path), full_page=True)
            except Exception:
                path.write_bytes(b"")
        logs = self._dump_logs(label)
        row = {
            "step": self.n,
            "label": label,
            "file": name,
            "note": note,
            "chat": chat,
            "error": err,
            "flow": logs.get("flow"),
            "room_open": logs.get("roomOpen"),
            "log_json": f"logs/{self.n:02d}_{label}.json",
            "log_md": f"logs/{self.n:02d}_{label}.md",
        }
        self.steps.append(row)
        print("SHOT", name, "flow=", (logs.get("flow") or "")[:80], flush=True)
        return path

    def wait_idle(self, timeout_ms: int = 240_000) -> None:
        btn = self.page.locator("#btnSend")
        try:
            btn.wait_for(state="visible", timeout=15_000)
        except Exception:
            return
        deadline = time.time() + timeout_ms / 1000
        saw = False
        while time.time() < deadline:
            try:
                disabled = btn.is_disabled()
            except Exception:
                break
            if disabled:
                saw = True
            elif saw and not disabled:
                self.page.wait_for_timeout(900)
                return
            # 组群聊天室出现也算阶段完成
            try:
                modal = self.page.locator("#groupRoomModal")
                if modal.count() and "hidden" not in (modal.get_attribute("class") or ""):
                    msgs = self.page.locator("#groupRoomMsgs .gr-msg")
                    if msgs.count() >= 2:
                        self.page.wait_for_timeout(1200)
                        return
            except Exception:
                pass
            self.page.wait_for_timeout(400)

    def ask(self, text: str, label: str, *, timeout_ms: int = 240_000) -> None:
        box = self.page.locator("#chatText")
        box.wait_for(state="visible", timeout=20_000)
        box.fill(text)
        self.page.locator("#btnSend").click()
        self.wait_idle(timeout_ms)
        self.shot(label, note="发送后界面", chat=text)

    def expand_trails(self) -> None:
        """展开处理轨迹便于截图。"""
        toggles = self.page.locator(".think-toggle, .think-toggle-label, details.think-trail summary")
        for i in range(min(toggles.count(), 8)):
            try:
                toggles.nth(i).click(timeout=1000)
            except Exception:
                pass
        self.page.wait_for_timeout(400)

    def click_shortlist(self, label: str, *, prefer_all: bool = True) -> bool:
        form = self.page.locator(".shortlist-form[data-interactive='1']").first
        if not form.count():
            form = self.page.locator("#shortlistDock .shortlist-form").first
        if not form.count():
            self.shot(label, note="无短名单/组群勾选面板")
            return False
        checks = form.locator(".sl-check, input[type=checkbox]")
        n = checks.count()
        for i in range(n):
            el = checks.nth(i)
            try:
                if not el.is_checked():
                    el.check(force=True)
            except Exception:
                try:
                    el.click(force=True)
                except Exception:
                    pass
        btn = form.locator("button[data-action='submit'], button.sl-btn.primary, button.primary")
        if btn.count():
            btn.first.click()
            self.wait_idle(220_000)
            self.expand_trails()
            self.shot(label, note="已勾选并提交短名单/组群")
            return True
        self.shot(label, note="有勾选框但无提交按钮")
        return False

    def click_choice(self, label: str, *needles: str) -> bool:
        # 含组群聊天室内按钮
        panels = self.page.locator(
            "#groupRoomActions button, .choice-panel[data-interactive='1'] button, "
            "#choiceDock button, .choice-btn, button.sl-btn"
        )
        n = panels.count()
        for i in range(n):
            t = (panels.nth(i).inner_text() or "").strip()
            if any(x in t for x in needles):
                try:
                    panels.nth(i).click()
                except Exception:
                    panels.nth(i).click(force=True)
                self.wait_idle(180_000)
                self.expand_trails()
                self.shot(label, note=f"点击: {t[:60]}")
                return True
        self.shot(label, note=f"未找到选项: {needles}")
        return False

    def wait_group_room(self, label: str, timeout_ms: int = 180_000) -> bool:
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            modal = self.page.locator("#groupRoomModal")
            if modal.count() and "hidden" not in (modal.get_attribute("class") or ""):
                # 等到有汇总或报价消息
                txt = self.page.locator("#groupRoomMsgs").inner_text() if self.page.locator("#groupRoomMsgs").count() else ""
                if "汇总" in txt or "报价" in txt or self.page.locator("#groupRoomActions button").count():
                    self.page.wait_for_timeout(800)
                    self.shot(label, note="组群聊天室已出现内容")
                    return True
            self.page.wait_for_timeout(800)
        self.shot(label, note="等待组群聊天室超时")
        return False


def write_review(steps: list[dict], notes: dict) -> None:
    lines = [
        f"# commerce_v2 双路径询价截图 · {RUN_ID}",
        "",
        f"- UI: `{BUYER_URL}`",
        f"- 需求话术: `{Q_DEMAND}`",
        f"- 目录: `docs/evidence/verify_ui_shots/v2_dual_{RUN_ID}/`",
        "",
        "## 路径说明",
        "1. **普通询价**：发现短名单 →「确认并询价」→ 报价/决策",
        "2. **组群竞价**：发「我要组群竞价」→ 勾选供应+物流 → 组群聊天室全量报价 → 选方案",
        "",
        "## 运行备注",
        "```json",
        json.dumps(notes, ensure_ascii=False, indent=2)[:3000],
        "```",
        "",
        "## 逐步截图与日志",
        "",
    ]
    for s in steps:
        lines.append(f"### {s['step']:02d}. {s['label']}")
        if s.get("chat"):
            lines.append(f"- 输入: `{s['chat'][:180]}`")
        if s.get("note"):
            lines.append(f"- 说明: {s['note']}")
        if s.get("flow"):
            lines.append(f"- 案状态: `{s['flow']}`")
        lines.append(f"- 截图: ![{s['file']}](screenshots/{s['file']})")
        lines.append(f"- 日志: [`{s['log_md']}`]({s['log_md']}) · [`{s['log_json']}`]({s['log_json']})")
        lines.append("")
    (OUT / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "report.json").write_text(
        json.dumps({"run_id": RUN_ID, "url": BUYER_URL, "demand": Q_DEMAND, "notes": notes, "steps": steps}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    print("OUT", OUT, flush=True)
    print("URL", BUYER_URL, flush=True)
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)
    os.environ["NO_PROXY"] = "*"
    notes: dict = {"normal": {}, "group": {}}

    with sync_playwright() as p:
        browser = launch_browser(p)
        cap = Capturer(browser)
        try:
            # ---------- 路径 A：普通询价 ----------
            print("=== NORMAL PATH ===", flush=True)
            cap.open()
            cap.shot("N00_home", note="新建对话首页")
            cap.ask(Q_DEMAND, "N01_after_demand", timeout_ms=260_000)
            cap.expand_trails()
            cap.shot("N01b_trails_expanded", note="展开处理轨迹")
            ok_sl = cap.click_shortlist("N02_shortlist_confirm")
            notes["normal"]["shortlist_clicked"] = ok_sl
            # 若系统提示可组群，先不点组群，继续普通路径的决策按钮
            cap.click_choice("N03_decide_try", "下单", "采纳", "最优", "确认", "继续", "订货")
            cap.expand_trails()
            cap.shot("N04_normal_end", note="普通询价路径阶段结束")
            notes["normal"]["flow"] = (cap.steps[-1].get("flow") if cap.steps else "")
            cap.close()

            # ---------- 路径 B：组群竞价 ----------
            print("=== GROUP PATH ===", flush=True)
            cap.open()
            cap.shot("G00_home", note="组群路径新建对话")
            cap.ask(Q_DEMAND, "G01_after_demand", timeout_ms=260_000)
            cap.expand_trails()
            cap.shot("G01b_trails", note="展开处理轨迹（进入组群前）")
            cap.ask("我要组群竞价", "G02_enter_group", timeout_ms=180_000)
            ok_g = cap.click_shortlist("G03_confirm_group_members")
            notes["group"]["group_confirm_clicked"] = ok_g
            # 有时确认组群是独立 choice 按钮
            if not ok_g:
                cap.click_choice("G03b_confirm_group_choice", "确认组群竞价", "确认进行组群", "组群竞价")
            room_ok = cap.wait_group_room("G04_group_room", timeout_ms=200_000)
            notes["group"]["room_opened"] = room_ok
            # 若卡在空消息，点续跑
            if room_ok:
                resume = cap.page.locator("#btnGroupResume")
                if resume.count():
                    resume.first.click()
                    cap.wait_idle(200_000)
                    cap.shot("G04b_after_resume", note="点击继续组群报价汇总")
            # 等汇总选项
            for _ in range(40):
                if cap.page.locator("#groupRoomActions button, .choice-btn").count():
                    break
                cap.page.wait_for_timeout(1500)
            cap.shot("G05_room_before_decide", note="汇总前/决策前聊天室")
            decided = cap.click_choice(
                "G06_pick_plan",
                "全量覆盖",
                "拆单",
                "单家全包",
                "最优",
                "plan_split",
                "plan_best",
                "采纳",
            )
            notes["group"]["plan_clicked"] = decided
            cap.expand_trails()
            cap.shot("G07_group_end", note="组群路径阶段结束")
            notes["group"]["flow"] = (cap.steps[-1].get("flow") if cap.steps else "")
            cap.close()
        finally:
            browser.close()

    write_review(cap.steps, notes)
    print("REVIEW", OUT / "REVIEW.md", flush=True)
    print("STEPS", len(cap.steps), flush=True)
    print("DONE", RUN_ID, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
