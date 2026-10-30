"""ACPs Group（AMQP）薄封装：采购 Leader 建组，供应/物流 Partner 入组与 ping 回执。

P0 目标：建组 → ACL → RPC 邀请入组 → 广播一条 ping → 收齐回执 → 可解散。
正式 broker：wt.ioa.pub:5671 + mq-auth（EXTERNAL mTLS），非 localhost。
"""
from __future__ import annotations

import asyncio
import logging
import os
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from acps_sdk.aip import ACSObject, Product, StructuredDataItem, TaskCommand, TaskResult
from acps_sdk.aip.aip_group_leader import GroupLeader
from acps_sdk.aip.aip_group_model import RabbitMQRequest
from acps_sdk.aip.aip_group_partner import GroupPartnerMqClient

from commerce.env_loader import load_dotenv

def _agentlink_root() -> Path:
    """commerce/_legacy/group_mq.py → 仓库根；兼容旧布局与 /opt/agentlink。"""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2],  # .../agentlink/commerce/_legacy → agentlink
        here.parents[1],  # 若文件在 commerce/group_mq.py
        Path("/opt/agentlink"),
        Path.cwd(),
    ]
    for p in candidates:
        if (p / "certs" / "platform" / "trust-bundle.pem").is_file():
            return p
    return here.parents[2]


_ROOT = _agentlink_root()
_logger = logging.getLogger("agentlink.group_mq")

# agent_id → 证书目录名 / 默认公网 join URL 环境变量
_AGENT_CERT_DIR = {
    "buyer-a": "buyer-a",
    "buyer-b": "buyer-b",
    "supplier-a": "supplier-a",
    "supplier-b": "supplier-b",
    "supplier-c": "supplier-c",
    "logistics": "logistics",
}

_PARTNER_META = {
    "supplier-a": {
        "aic_env": "SUPPLIER_A_AIC",
        "rpc_env": "SUPPLIER_A_RPC_URL",
        "default_rpc": "https://39.105.20.113:8011/rpc",
    },
    "supplier-b": {
        "aic_env": "SUPPLIER_B_AIC",
        "rpc_env": "SUPPLIER_B_RPC_URL",
        "default_rpc": "https://39.105.20.113:8013/rpc",
    },
    "supplier-c": {
        "aic_env": "SUPPLIER_C_AIC",
        "rpc_env": "SUPPLIER_C_RPC_URL",
        "default_rpc": "https://39.105.20.113:8014/rpc",
    },
    "logistics": {
        "aic_env": "LOGISTICS_AIC",
        "rpc_env": "LOGISTICS_RPC_URL",
        "default_rpc": "https://ashui.online:8015/rpc",
    },
}


def mq_rabbit_config() -> dict[str, Any]:
    load_dotenv()
    host = (os.getenv("ACPS_MQ_HOST") or "wt.ioa.pub").strip()
    port = int((os.getenv("ACPS_MQ_PORT") or "5671").strip())
    vhost = (os.getenv("ACPS_MQ_VHOST") or "acps").strip() or "acps"
    auth = (os.getenv("ACPS_MQ_AUTH_URL") or "https://wt.ioa.pub/mq-auth").strip().rstrip(
        "/"
    )
    user = (os.getenv("ACPS_MQ_USER") or "").strip() or None
    password = (os.getenv("ACPS_MQ_PASSWORD") or "").strip() or None
    cfg: dict[str, Any] = {
        "host": host,
        "port": port,
        "vhost": vhost,
        "auth_service_url": auth,
    }
    if user and password:
        cfg["user"] = user
        cfg["password"] = password
    return cfg


def _cert_paths(agent_id: str) -> tuple[Path, Path, Path] | None:
    """返回 (agent-cert, agent-key, trust-bundle)；缺失则 None。"""
    load_dotenv()
    # 优先环境变量（云上部署）
    cert = (os.getenv("AIP_CLIENT_CERT") or "").strip()
    key = (os.getenv("AIP_CLIENT_KEY") or "").strip()
    ca = (os.getenv("AIP_TRUST_BUNDLE") or "").strip()
    if cert and key and ca and Path(cert).is_file() and Path(key).is_file():
        return Path(cert), Path(key), Path(ca)

    folder = _AGENT_CERT_DIR.get(agent_id)
    if not folder:
        return None
    base = _ROOT / "certs" / "platform" / folder
    c, k = base / "agent-cert.pem", base / "agent-key.pem"
    ca_p = _ROOT / "certs" / "platform" / "trust-bundle.pem"
    if c.is_file() and k.is_file() and ca_p.is_file():
        return c, k, ca_p
    return None


def build_agent_ssl_context(agent_id: str) -> ssl.SSLContext:
    """客户端 mTLS：系统 CA（校验 wt.ioa.pub HTTPS）+ 平台 trust-bundle（AMQPS）+ agent 证书。"""
    paths = _cert_paths(agent_id)
    if not paths:
        raise RuntimeError(
            f"缺少 mTLS 证书: agent_id={agent_id}（设 AIP_CLIENT_CERT/KEY + TRUST_BUNDLE 或放 certs/platform/{agent_id}/）"
        )
    cert, key, ca = paths
    # 先带系统信任根，再叠平台 CA，避免 mq-auth HTTPS 因只有平台 bundle 而校验失败
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.load_verify_locations(cafile=str(ca))
    ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    if os.getenv("AIP_SSL_CHECK_HOSTNAME", "0") != "1":
        ctx.check_hostname = False
    return ctx


def ssl_cert_tuple(agent_id: str) -> tuple[str, str] | None:
    paths = _cert_paths(agent_id)
    if not paths:
        return None
    return str(paths[0]), str(paths[1])


def partner_join_url(agent_id: str) -> str:
    meta = _PARTNER_META[agent_id]
    load_dotenv()
    rpc = (os.getenv(meta["rpc_env"]) or meta["default_rpc"]).rstrip("/")
    if rpc.endswith("/rpc"):
        return rpc[: -len("/rpc")] + "/group/join"
    return rpc + "/group/join"


def aic_from_cert(agent_id: str) -> str | None:
    """从 agent-cert.pem 的 CN 读取 AIC（与 mTLS 身份对齐）。"""
    paths = _cert_paths(agent_id)
    if not paths:
        return None
    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend

        cert = x509.load_pem_x509_certificate(paths[0].read_bytes(), default_backend())
        attrs = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
        if attrs:
            cn = str(attrs[0].value)
            if cn.count(".") >= 5:
                return cn
    except Exception:  # noqa: BLE001
        return None
    return None


def partner_aic(agent_id: str) -> str:
    meta = _PARTNER_META[agent_id]
    load_dotenv()
    raw = (os.getenv(meta["aic_env"]) or "").strip()
    if raw.count(".") >= 5:
        return raw
    # 环境未配或仍是本地短 ID：从 agent 证书 CN 读取
    cn = aic_from_cert(agent_id)
    if cn:
        return cn
    return raw or f"{agent_id}-local-aic"


def leader_aic_for(agent_id: str) -> str:
    """采购 Leader AIC：优先环境变量，否则证书 CN。"""
    load_dotenv()
    env_key = {
        "buyer-a": "BUYER_A_AIC",
        "buyer-b": "BUYER_B_AIC",
    }.get(agent_id, "")
    raw = (os.getenv(env_key) or "").strip() if env_key else ""
    if raw.count(".") >= 5:
        return raw
    cn = aic_from_cert(agent_id)
    if cn:
        return cn
    raise RuntimeError(f"无法解析 {agent_id} 的 Leader AIC（缺 {env_key or 'env'} / 证书）")


def _group_identity_binding() -> bool:
    """Group 平面必须带 AMQP user_id；阿里云若 AIP_IDENTITY_BINDING=0 会导致 Leader 丢弃回执。"""
    raw = (os.getenv("ACPS_GROUP_IDENTITY_BINDING") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def build_group_leader(*, leader_aic: str, leader_agent_id: str = "buyer-a") -> GroupLeader:
    cfg = mq_rabbit_config()
    return GroupLeader(
        leader_aic=leader_aic,
        rabbitmq_config=cfg,
        ssl_context=build_agent_ssl_context(leader_agent_id),
        ssl_cert=ssl_cert_tuple(leader_agent_id),
        identity_binding_enabled=_group_identity_binding(),
    )


def build_group_partner(*, partner_aic_value: str, partner_agent_id: str) -> GroupPartnerMqClient:
    cfg = mq_rabbit_config()
    return GroupPartnerMqClient(
        partner_aic=partner_aic_value,
        rabbitmq_host=cfg["host"],
        rabbitmq_port=int(cfg["port"]),
        rabbitmq_vhost=cfg["vhost"],
        rabbitmq_user=cfg.get("user"),
        rabbitmq_password=cfg.get("password"),
        ssl_context=build_agent_ssl_context(partner_agent_id),
        identity_binding_enabled=_group_identity_binding(),
    )


@dataclass
class GroupSessionRecord:
    session_id: str
    group_id: str
    leader_aic: str
    members: list[dict[str, str]]
    created_at: str
    task_id: str | None = None
    results: list[dict[str, Any]] = field(default_factory=list)
    status: str = "open"


# 进程内会话表（P0；P1 可挂 case）
_SESSIONS: dict[str, GroupSessionRecord] = {}
_LEADERS: dict[str, GroupLeader] = {}
_PARTNERS: dict[str, GroupPartnerMqClient] = {}  # key=aic


def get_session(session_id: str) -> GroupSessionRecord | None:
    return _SESSIONS.get(session_id)


def list_sessions() -> list[GroupSessionRecord]:
    return list(_SESSIONS.values())


async def open_group(
    *,
    leader_aic: str,
    leader_agent_id: str = "buyer-a",
    member_agent_ids: list[str] | None = None,
    invite: bool = True,
) -> GroupSessionRecord:
    """建组并对成员发 RPC 邀请（默认三供+物流）。"""
    members_ids = member_agent_ids or [
        "supplier-a",
        "supplier-b",
        "supplier-c",
        "logistics",
    ]
    partners = [
        ACSObject(aic=partner_aic(mid))
        for mid in members_ids
        if mid in _PARTNER_META
    ]
    if not partners:
        raise ValueError("无有效 Partner")

    session_id = f"grp-{uuid4().hex[:12]}"
    leader = build_group_leader(leader_aic=leader_aic, leader_agent_id=leader_agent_id)
    _LEADERS[session_id] = leader

    results_box: list[dict[str, Any]] = []

    async def _on_msg(msg: Any) -> None:
        if isinstance(msg, TaskResult):
            results_box.append(
                {
                    "senderId": msg.senderId,
                    "taskId": msg.taskId,
                    "state": str(msg.status.state) if msg.status else None,
                    "at": datetime.now(timezone.utc).isoformat(),
                }
            )
            rec = _SESSIONS.get(session_id)
            if rec:
                rec.results = list(results_box)

    session = await leader.create_group_session(
        session_id=session_id, initial_partners=partners
    )
    # 挂结果收集（覆盖默认 handler 链：SDK 已 set_message_handler 到 _handle_group_message）
    # 再包一层监听 TaskResult
    inner = session.leader_mq_client._message_handler

    async def _wrapped(msg: Any) -> None:
        await _on_msg(msg)
        if inner:
            await inner(msg)

    session.leader_mq_client.set_message_handler(_wrapped)

    # 跨云 Partner HTTPS 多为自签：邀请 RPC 不校验服务端证书；AMQP mTLS 仍用正式 ssl_context
    if (os.getenv("AIP_SSL_INSECURE") or "1").strip() not in ("0", "false", "no", "off"):
        _mq = session.leader_mq_client
        _orig_invite = _mq.invite_partner
        _client_cert = ssl_cert_tuple(leader_agent_id)

        async def _invite_insecure(
            partner_acs: Any,
            partner_rpc_url: str,
            ssl_context: Any = None,
            client_cert: Any = None,
            timeout: float = 30.0,
        ) -> Any:
            return await _orig_invite(
                partner_acs,
                partner_rpc_url,
                ssl_context=False,
                client_cert=client_cert if client_cert is not None else _client_cert,
                timeout=timeout,
            )

        _mq.invite_partner = _invite_insecure  # type: ignore[method-assign]

    member_rows: list[dict[str, str]] = []
    invite_errors: list[str] = []
    invite_elapsed_ms = 0.0
    if invite:
        # 并行邀请 + 单家短超时，避免串行跨云 ReadTimeout 把整场拖到分钟级
        try:
            invite_timeout = float(os.getenv("ACPS_GROUP_INVITE_TIMEOUT_SEC") or "12")
        except ValueError:
            invite_timeout = 12.0
        invite_timeout = max(1.0, min(invite_timeout, 30.0))
        targets = [mid for mid in members_ids if mid in _PARTNER_META]

        async def _invite_one(mid: str) -> dict[str, str]:
            aic = partner_aic(mid)
            join_url = partner_join_url(mid)
            try:
                await asyncio.wait_for(
                    leader.invite_partner(
                        session_id=session_id,
                        partner_acs=ACSObject(aic=aic),
                        partner_rpc_url=join_url,
                    ),
                    timeout=invite_timeout,
                )
                return {
                    "agent_id": mid,
                    "aic": aic,
                    "join_url": join_url,
                    "status": "joined",
                }
            except Exception as exc:  # noqa: BLE001
                _logger.warning("invite failed %s: %s", mid, exc)
                invite_errors.append(f"{mid}: {type(exc).__name__}: {exc}")
                err_name = (
                    "TimeoutError"
                    if isinstance(exc, (asyncio.TimeoutError, TimeoutError))
                    else type(exc).__name__
                )
                return {
                    "agent_id": mid,
                    "aic": aic,
                    "join_url": join_url,
                    "status": f"error:{err_name}",
                }

        t_inv0 = asyncio.get_event_loop().time()
        # 供应先并行入组；物流旁听串行殿后。物流 invite 若拖垮 channel，
        # 不应连坐导致供应也全灭（实证：仅 A/C 可 joined，A/C+logistics 并行常全 Timeout）。
        suppliers = [m for m in targets if str(m).startswith("supplier")]
        others = [m for m in targets if m not in suppliers]
        member_rows = []
        if suppliers:
            member_rows.extend(await asyncio.gather(*[_invite_one(m) for m in suppliers]))
        for mid in others:
            member_rows.append(await _invite_one(mid))
        invite_elapsed_ms = round((asyncio.get_event_loop().time() - t_inv0) * 1000.0, 1)

    rec = GroupSessionRecord(
        session_id=session_id,
        group_id=session.group_id,
        leader_aic=leader_aic,
        members=member_rows,
        created_at=datetime.now(timezone.utc).isoformat(),
        status="open" if not invite_errors else "partial",
    )
    if invite_errors:
        rec.results.append({"invite_errors": invite_errors})
    if invite:
        rec.results.append(
            {
                "invite_parallel": True,
                "invite_timeout_sec": float(os.getenv("ACPS_GROUP_INVITE_TIMEOUT_SEC") or "5"),
                "invite_elapsed_ms": invite_elapsed_ms,
            }
        )
    _SESSIONS[session_id] = rec
    return rec


async def ping_group(session_id: str, *, text: str = "agentlink.group.ping") -> dict[str, Any]:
    leader = _LEADERS.get(session_id)
    rec = _SESSIONS.get(session_id)
    if not leader or not rec:
        raise KeyError(session_id)
    task_id = await leader.start_task(session_id=session_id, task_content=text)
    rec.task_id = task_id
    # 等待回执（最多 25s）
    expected = {m["aic"] for m in rec.members if m.get("status") == "joined"}
    deadline = asyncio.get_event_loop().time() + 25.0
    while asyncio.get_event_loop().time() < deadline:
        got = {r["senderId"] for r in rec.results if r.get("senderId")}
        if expected and expected.issubset(got):
            break
        await asyncio.sleep(0.4)
    return {
        "session_id": session_id,
        "task_id": task_id,
        "expected": sorted(expected),
        "got": sorted({r["senderId"] for r in rec.results if r.get("senderId")}),
        "results": rec.results,
    }


async def dissolve_group(session_id: str) -> None:
    leader = _LEADERS.pop(session_id, None)
    rec = _SESSIONS.get(session_id)
    if leader:
        try:
            await leader.dissolve_group_session(session_id)
        except Exception:  # noqa: BLE001
            _logger.exception("dissolve failed")
        try:
            await leader.close()
        except Exception:  # noqa: BLE001
            pass
    # 清理本进程内为该会话服务的 Partner MQ 客户端（同进程冒烟 / 单进程 Partner）
    if rec:
        for m in rec.members:
            aic = m.get("aic") or ""
            client = _PARTNERS.pop(aic, None)
            if client is None:
                continue
            try:
                close = getattr(client, "close", None) or getattr(client, "disconnect", None)
                if close:
                    await close()
            except Exception:  # noqa: BLE001
                _logger.exception("partner close failed aic=%s", aic)
        rec.status = "dissolved"


async def open_group_inprocess_join(
    *,
    leader_aic: str,
    leader_agent_id: str = "buyer-a",
    member_agent_ids: list[str] | None = None,
) -> GroupSessionRecord:
    """本地冒烟：不经 HTTP，Leader 建组后直接调 Partner.join_group（同进程）。"""
    from acps_sdk.aip.aip_group_model import (
        AMQPConfig,
        GroupInfo,
        RabbitMQRequestParams,
        RabbitMQServerConfig,
    )

    members_ids = member_agent_ids or [
        "supplier-a",
        "supplier-b",
        "supplier-c",
        "logistics",
    ]
    partners = [ACSObject(aic=partner_aic(mid)) for mid in members_ids]
    session_id = f"grp-local-{uuid4().hex[:10]}"
    leader = build_group_leader(leader_aic=leader_aic, leader_agent_id=leader_agent_id)
    _LEADERS[session_id] = leader

    results_box: list[dict[str, Any]] = []

    async def _on_msg(msg: Any) -> None:
        if isinstance(msg, TaskResult):
            results_box.append(
                {
                    "senderId": msg.senderId,
                    "taskId": msg.taskId,
                    "state": str(msg.status.state) if msg.status else None,
                }
            )
            if session_id in _SESSIONS:
                _SESSIONS[session_id].results = list(results_box)

    session = await leader.create_group_session(
        session_id=session_id, initial_partners=partners
    )
    inner = session.leader_mq_client._message_handler

    async def _wrapped(msg: Any) -> None:
        await _on_msg(msg)
        if inner:
            await inner(msg)

    session.leader_mq_client.set_message_handler(_wrapped)

    mq = session.leader_mq_client
    assert mq._group_id and mq._exchange_name
    server = RabbitMQServerConfig(
        host=leader.rabbitmq_host,
        port=leader.rabbitmq_port,
        vhost=leader.rabbitmq_vhost,
        accessToken=None,
    )
    amqp = AMQPConfig(
        exchange=mq._exchange_name, exchangeType="fanout", routingKey=""
    )
    group_info = GroupInfo(
        groupId=mq._group_id,
        leader=ACSObject(aic=leader_aic),
        partners=partners,
    )

    member_rows: list[dict[str, str]] = []
    for mid in members_ids:
        aic = partner_aic(mid)
        client = build_group_partner(partner_aic_value=aic, partner_agent_id=mid)
        _PARTNERS[aic] = client
        await wire_partner_group_handler(client, agent_id=mid)

        req = RabbitMQRequest(
            id=str(uuid4()),
            params=RabbitMQRequestParams(
                protocol="rabbitmq:4.0",
                group=group_info,
                server=server,
                amqp=amqp,
            ),
        )
        resp = await client.join_group(req)
        status = "joined" if resp.result else f"error:{resp.error}"
        member_rows.append({"agent_id": mid, "aic": aic, "status": status})

    rec = GroupSessionRecord(
        session_id=session_id,
        group_id=session.group_id,
        leader_aic=leader_aic,
        members=member_rows,
        created_at=datetime.now(timezone.utc).isoformat(),
        status="open",
    )
    _SESSIONS[session_id] = rec
    return rec


def _load_agent_policy(agent_id: str) -> dict[str, Any]:
    import yaml

    folder = agent_id.replace("-", "_") if "_" not in agent_id else agent_id
    # agent_id supplier-a → agents/supplier_a/policy.yaml
    cand = [
        _ROOT / "agents" / agent_id / "policy.yaml",
        _ROOT / "agents" / folder / "policy.yaml",
        _ROOT / "agents" / agent_id.replace("-", "_") / "policy.yaml",
    ]
    for p in cand:
        if p.is_file():
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {}


async def wire_partner_group_handler(
    client: GroupPartnerMqClient,
    *,
    agent_id: str,
    policy: dict[str, Any] | None = None,
) -> None:
    """Group 任务处理：ping 回执 + blind_bid 竞价出价。"""
    from agentlink_runtime.aip_payload import extract_structured, extract_text
    from agentlink_runtime.graph_base import new_state
    from agents.supplier_common.negotiate import handle_blind_bid

    pol = policy if policy is not None else _load_agent_policy(agent_id)

    async def on_command(command: TaskCommand, is_mentioned: bool = True) -> None:
        cmd = getattr(command.command, "value", command.command)
        if str(cmd) != "start":
            return
        if not is_mentioned:
            return
        sid = command.sessionId or ""
        tid = command.taskId
        envelope = extract_structured(command.dataItems)
        text = extract_text(command.dataItems)
        try:
            await client.accept_task(tid, sid)
            await client.start_working(tid, sid)

            schema = (envelope or {}).get("schema_type") if envelope else None
            if schema == "agentlink.blind_bid":
                if agent_id.startswith("logistics"):
                    product = Product(
                        id=f"skip-{tid}",
                        name="group_bid_skip",
                        description="logistics skips blind_bid",
                        dataItems=[
                            StructuredDataItem(
                                data={
                                    "schema_type": "agentlink.group.bid_skip",
                                    "reason": "logistics_not_bidder",
                                    "partner_aic": client.partner_aic,
                                }
                            )
                        ],
                    )
                else:
                    state = new_state(
                        agent_id=agent_id,
                        aic=client.partner_aic,
                        tenant_id=f"{agent_id}-org",
                        business_id=str(envelope.get("business_id") or tid),
                        aip_task_id=tid,
                        session_id=sid,
                        authz_level="negotiate",
                    )
                    state = handle_blind_bid(state=state, envelope=envelope, policy=pol)
                    out_env = (state.get("outcome") or {}).get("envelope") or {}
                    product = Product(
                        id=f"bid-{tid}-{client.partner_aic[-8:]}",
                        name="blind_bid",
                        description="group blind bid offer",
                        dataItems=[StructuredDataItem(data=out_env)],
                    )
            elif schema in ("agentlink.shipping_request", "agentlink.shipping_quote_request"):
                if not agent_id.startswith("logistics"):
                    product = Product(
                        id=f"skip-ship-{tid}",
                        name="group_ship_skip",
                        description="non-logistics skips shipping",
                        dataItems=[
                            StructuredDataItem(
                                data={
                                    "schema_type": "agentlink.group.bid_skip",
                                    "reason": "not_logistics",
                                    "partner_aic": client.partner_aic,
                                }
                            )
                        ],
                    )
                else:
                    from agents.logistics.graph import run_logistics_pipeline

                    state = new_state(
                        agent_id=agent_id,
                        aic=client.partner_aic,
                        tenant_id="logistics-org",
                        business_id=str(envelope.get("business_id") or tid),
                        aip_task_id=tid,
                        session_id=sid,
                        authz_level="negotiate",
                    )
                    state = run_logistics_pipeline(
                        state=state, envelope=envelope, policy=pol or _load_agent_policy("logistics")
                    )
                    out_env = (state.get("outcome") or {}).get("envelope") or {
                        "schema_type": "agentlink.group.ship_error",
                        "payload": {"reason": (state.get("outcome") or {}).get("reason") or "ship_failed"},
                    }
                    # 回带询价关联的供应商，便于 Leader 合 TCO
                    if isinstance(out_env.get("payload"), dict):
                        hint = (envelope.get("payload") or {}).get("supplier_agent_id")
                        if hint:
                            out_env["payload"]["supplier_agent_id"] = hint
                    product = Product(
                        id=f"ship-{tid}-{client.partner_aic[-8:]}",
                        name="shipping_quote",
                        description="group shipping quote",
                        dataItems=[StructuredDataItem(data=out_env)],
                    )
            else:
                product = Product(
                    id=f"ping-{tid}-{client.partner_aic[-8:]}",
                    name="group_ping_ack",
                    description="group ping ack",
                    dataItems=[
                        StructuredDataItem(
                            data={
                                "schema_type": "agentlink.group.ping_ack",
                                "partner_aic": client.partner_aic,
                                "echo": "pong",
                                "text": text[:200] if text else "",
                            }
                        )
                    ],
                )

            await client.submit_for_completion(tid, sid, [product])
            await client.complete_task(tid, sid)
        except Exception:  # noqa: BLE001
            _logger.exception("group handler failed aic=%s", client.partner_aic)
            try:
                await client.fail_task(tid, sid, "group handler error")
            except Exception:  # noqa: BLE001
                pass

    client.set_command_handler(on_command)


# 兼容旧名
async def wire_partner_ping_handler(client: GroupPartnerMqClient) -> None:
    await wire_partner_group_handler(client, agent_id="supplier-a", policy={})


def get_or_create_partner_client(*, aic: str, agent_id: str) -> GroupPartnerMqClient:
    existing = _PARTNERS.get(aic)
    if existing:
        return existing
    client = build_group_partner(partner_aic_value=aic, partner_agent_id=agent_id)
    _PARTNERS[aic] = client
    return client


async def partner_handle_join_request(
    *,
    agent_id: str,
    aic: str,
    body: dict[str, Any],
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """HTTP /group/join 入口。"""
    request = RabbitMQRequest.model_validate(body)
    client = get_or_create_partner_client(aic=aic, agent_id=agent_id)
    await wire_partner_group_handler(client, agent_id=agent_id, policy=policy)
    _logger.info(
        "group_join_begin agent_id=%s aic=%s group_id=%s identity_binding=%s",
        agent_id,
        aic,
        getattr(request.params.group, "groupId", None),
        client._identity_binding_enabled,
    )
    response = await client.join_group(request)
    _logger.info(
        "group_join_done agent_id=%s aic=%s ok=%s",
        agent_id,
        aic,
        bool(response.result),
    )
    return response.model_dump(exclude_none=True)


def _extract_structured_result(
    msg: TaskResult, *, schemas: set[str]
) -> dict[str, Any] | None:
    from agentlink_runtime.aip_payload import extract_structured

    for prod in msg.products or []:
        env = extract_structured(prod.dataItems)
        if env and env.get("schema_type") in schemas:
            return env
    return None


def _extract_offer_from_result(msg: TaskResult) -> dict[str, Any] | None:
    return _extract_structured_result(
        msg, schemas={"agentlink.blind_bid_offer", "agentlink.group.bid_skip"}
    )


async def run_group_blind_auction(
    *,
    leader_aic: str,
    leader_agent_id: str = "buyer-a",
    member_agent_ids: list[str],
    bid_envelope: dict[str, Any],
    wait_sec: float = 45.0,
    dissolve: bool = True,
    with_tco: bool = True,
    dest_postal: str | None = None,
    quantity: int | None = None,
) -> dict[str, Any]:
    """建组 → 盲拍 →（可选）同组询运合 TCO → 方案排序。"""
    from acps_sdk.aip.aip_base_model import TaskCommandType
    from agentlink_runtime.aip_payload import as_structured_item, wrap_business
    from commerce.merchant import buyer_destination, profile as merchant_profile

    t_all0 = asyncio.get_event_loop().time()
    suppliers = [m for m in member_agent_ids if m.startswith("supplier")]
    rec = await open_group(
        leader_aic=leader_aic,
        leader_agent_id=leader_agent_id,
        member_agent_ids=member_agent_ids,
        invite=True,
    )
    leader = _LEADERS.get(rec.session_id)
    if not leader:
        raise RuntimeError("leader missing after open_group")

    invite_meta = next(
        (x for x in (rec.results or []) if isinstance(x, dict) and "invite_elapsed_ms" in x),
        {},
    )
    joined_suppliers = [
        m
        for m in rec.members
        if m.get("status") == "joined" and str(m.get("agent_id") or "").startswith("supplier")
    ]
    try:
        min_joined = int(os.getenv("ACPS_GROUP_MIN_SUPPLIERS") or "2")
    except ValueError:
        min_joined = 2
    min_joined = max(1, min_joined)

    # 入组供应不足 → 立刻空榜返回，由 step_auction 走并行 RPC，避免再空等 wait_sec
    if len(joined_suppliers) < min_joined:
        if dissolve:
            try:
                await dissolve_group(rec.session_id)
            except Exception:  # noqa: BLE001
                pass
        return {
            "session_id": rec.session_id,
            "group_id": rec.group_id,
            "task_id": None,
            "bids": [
                {
                    "supplier_agent_id": mid,
                    "aic": partner_aic(mid),
                    "error": "not_joined",
                    "transport": "group",
                }
                for mid in suppliers
            ],
            "schemes": [],
            "offers_got": 0,
            "early_abort": True,
            "abort_reason": "insufficient_joined_suppliers",
            "joined_suppliers": [m.get("agent_id") for m in joined_suppliers],
            "invite_elapsed_ms": invite_meta.get("invite_elapsed_ms"),
            "elapsed_ms": round((asyncio.get_event_loop().time() - t_all0) * 1000.0, 1),
            "members": rec.members,
        }

    offers: dict[str, dict[str, Any]] = {}
    ship_by_task: dict[str, dict[str, Any]] = {}

    async def _on_msg(msg: Any) -> None:
        if not isinstance(msg, TaskResult):
            return
        offer = _extract_offer_from_result(msg)
        if offer and msg.senderId and offer.get("schema_type") == "agentlink.blind_bid_offer":
            offers[str(msg.senderId)] = {
                "senderId": msg.senderId,
                "state": str(msg.status.state) if msg.status else None,
                "envelope": offer,
            }
        ship = _extract_structured_result(msg, schemas={"agentlink.shipping_quote"})
        if ship and msg.taskId:
            ship_by_task[str(msg.taskId)] = ship
        rec.results.append(
            {
                "senderId": msg.senderId,
                "taskId": msg.taskId,
                "state": str(msg.status.state) if msg.status else None,
            }
        )

    session = leader.group_sessions[rec.session_id]
    inner = session.leader_mq_client._message_handler

    async def _wrapped(msg: Any) -> None:
        await _on_msg(msg)
        if inner:
            await inner(msg)

    session.leader_mq_client.set_message_handler(_wrapped)

    mention_aics = [
        m["aic"]
        for m in rec.members
        if m.get("status") == "joined" and m.get("agent_id", "").startswith("supplier")
    ]
    logistics_aics = [
        m["aic"]
        for m in rec.members
        if m.get("status") == "joined" and m.get("agent_id") == "logistics"
    ]
    # 有人入组时缩短默认等待；可用环境变量覆盖
    try:
        eff_wait = float(os.getenv("ACPS_GROUP_BID_WAIT_SEC") or wait_sec)
    except ValueError:
        eff_wait = wait_sec
    # 默认入参 45s 过长；未显式配置时压到 12s
    if os.getenv("ACPS_GROUP_BID_WAIT_SEC") is None and wait_sec >= 45.0:
        eff_wait = 12.0
    eff_wait = max(2.0, min(eff_wait, 60.0))

    task_id = f"task-bid-{uuid4().hex[:10]}"
    await session.leader_mq_client.send_task_command(
        command=TaskCommandType.Start,
        task_id=task_id,
        session_id=rec.session_id,
        text_content="agentlink.group.blind_bid",
        data_items=[as_structured_item(bid_envelope)],
        mentions=mention_aics or None,
    )
    rec.task_id = task_id

    deadline = asyncio.get_event_loop().time() + eff_wait
    expected = set(mention_aics)
    while asyncio.get_event_loop().time() < deadline:
        if expected and expected.issubset(set(offers.keys())):
            break
        await asyncio.sleep(0.4)

    qty = int(
        quantity
        or (bid_envelope.get("payload") or {}).get("quantity")
        or 1
    )
    dest = dest_postal or buyer_destination().get("postal_code") or "071000"

    bids: list[dict[str, Any]] = []
    for mid in suppliers:
        aic = partner_aic(mid)
        row = offers.get(aic)
        if not row:
            bids.append({"supplier_agent_id": mid, "aic": aic, "error": "no_group_bid"})
            continue
        payload = (row["envelope"].get("payload") or {}) if isinstance(row["envelope"], dict) else {}
        bids.append(
            {
                "supplier_agent_id": mid,
                "aic": aic,
                "unit_price": payload.get("unit_price"),
                "lead_time_days": payload.get("lead_time_days"),
                "bid_id": payload.get("bid_id"),
                "transport": "group",
                "raw": row["envelope"],
            }
        )

    # —— P2：同组向物流询运，按供应商发货地合 TCO ——
    schemes: list[dict[str, Any]] = []
    if with_tco and logistics_aics:
        for bid in [b for b in bids if b.get("unit_price") is not None]:
            mid = bid["supplier_agent_id"]
            pol = _load_agent_policy(mid)
            origin_city = (
                pol.get("ship_from_city")
                or merchant_profile(mid).get("city")
                or "未知"
            )
            kg_unit = float(pol.get("kg_per_unit") or 2.0)
            weight = max(1.0, round(kg_unit * qty, 2))
            ship_tid = f"task-ship-{mid}-{uuid4().hex[:6]}"
            ship_env = wrap_business(
                "agentlink.shipping_request",
                str((bid_envelope.get("business_id") or "group-tco")),
                {
                    "supplier_agent_id": mid,
                    "weight_kg": weight,
                    "zone": "domestic",
                    "origin": {"city": origin_city},
                    "origin_hint": origin_city,
                    "destination": {"postal_code": str(dest)},
                },
            )
            await session.leader_mq_client.send_task_command(
                command=TaskCommandType.Start,
                task_id=ship_tid,
                session_id=rec.session_id,
                text_content="agentlink.group.shipping_request",
                data_items=[as_structured_item(ship_env)],
                mentions=logistics_aics,
            )
            ship_deadline = asyncio.get_event_loop().time() + min(20.0, wait_sec)
            while asyncio.get_event_loop().time() < ship_deadline:
                if ship_tid in ship_by_task:
                    break
                await asyncio.sleep(0.3)
            ship_env_out = ship_by_task.get(ship_tid) or {}
            ship_payload = ship_env_out.get("payload") or {}
            shipping_cost = ship_payload.get("shipping_cost")
            unit = float(bid["unit_price"])
            goods_total = round(unit * qty, 2)
            tco = round(goods_total + float(shipping_cost or 0), 2) if shipping_cost is not None else None
            bid["shipping_cost"] = shipping_cost
            bid["goods_total"] = goods_total
            bid["tco"] = tco
            bid["origin_city"] = origin_city
            bid["weight_kg"] = weight
            schemes.append(
                {
                    "scheme_id": f"sch-{mid}",
                    "supplier_agent_id": mid,
                    "aic": bid.get("aic"),
                    "unit_price": unit,
                    "quantity": qty,
                    "goods_total": goods_total,
                    "shipping_cost": shipping_cost,
                    "tco": tco,
                    "lead_time_days": bid.get("lead_time_days"),
                    "eta_days": ship_payload.get("eta_days"),
                    "origin_city": origin_city,
                    "dest_postal": dest,
                    "bid_id": bid.get("bid_id"),
                    "transport": "group",
                }
            )

    bids_sorted = sorted(
        [b for b in bids if b.get("unit_price") is not None],
        key=lambda b: (
            b.get("tco") is None,
            float(b["tco"]) if b.get("tco") is not None else float(b["unit_price"]),
        ),
    )
    schemes_sorted = sorted(
        [s for s in schemes if s.get("tco") is not None],
        key=lambda s: float(s["tco"]),
    ) or sorted(schemes, key=lambda s: float(s.get("unit_price") or 1e18))

    out = {
        "session_id": rec.session_id,
        "group_id": rec.group_id,
        "task_id": task_id,
        "members": rec.members,
        "bids": bids,
        "ranked": bids_sorted,
        "schemes": schemes_sorted,
        "offers_got": sorted(offers.keys()),
        "tco_enabled": with_tco,
        "early_abort": False,
        "invite_elapsed_ms": invite_meta.get("invite_elapsed_ms"),
        "bid_wait_sec": eff_wait,
        "elapsed_ms": round((asyncio.get_event_loop().time() - t_all0) * 1000.0, 1),
    }
    if dissolve:
        await dissolve_group(rec.session_id)
    return out
