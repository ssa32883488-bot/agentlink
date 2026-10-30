"""AMP Access / Message / Heartbeat 过程日志。

比赛计分口径（梧桐指南）：
- Access：correlationId = AIP taskId；调用方/被调方各记一条，配对计 1 次
- Message：correlationId = taskId；双方相同 messageId；eventType=send|receive
- Heartbeat：周期上报存活，供平台发现/调用（topic 默认 amp.heartbeat）

落地：
1. 本地 NDJSON（logs/amp_access.jsonl / amp_message.jsonl / amp_heartbeat.jsonl）
2. 可选直连平台 Kafka PLAINTEXT（默认 wt.ioa.pub:19092）
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

_logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
_ACCESS_LOG = _ROOT / "logs" / "amp_access.jsonl"
_MESSAGE_LOG = _ROOT / "logs" / "amp_message.jsonl"
_HEARTBEAT_LOG = _ROOT / "logs" / "amp_heartbeat.jsonl"

_kafka_lock = threading.Lock()
_kafka_producer = None
_kafka_failed = False

_hb_lock = threading.Lock()
_hb_threads: dict[str, threading.Thread] = {}
_hb_stop: dict[str, threading.Event] = {}
_hb_started_at: dict[str, float] = {}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_log_id() -> str:
    try:
        return str(uuid4())  # uuid7 在部分环境不可用
    except Exception:  # noqa: BLE001
        return f"log-{uuid4().hex}"


def _message_id_for_task(task_id: str) -> str:
    """双侧必须相同：由 taskId 派生，无需额外协商。"""
    tid = (task_id or "").strip() or uuid4().hex
    return f"msg-{tid}"


def _kafka_enabled() -> bool:
    if os.getenv("AMP_KAFKA_ENABLED", "1").strip() in ("0", "false", "False", "no"):
        return False
    return bool((os.getenv("AMP_KAFKA_BOOTSTRAP") or "wt.ioa.pub:19092").strip())


def _get_kafka_producer():
    global _kafka_producer, _kafka_failed
    if _kafka_failed:
        return None
    if not _kafka_enabled():
        return None
    with _kafka_lock:
        if _kafka_producer is not None:
            return _kafka_producer
        if _kafka_failed:
            return None
        try:
            from kafka import KafkaProducer  # type: ignore

            bootstrap = (os.getenv("AMP_KAFKA_BOOTSTRAP") or "wt.ioa.pub:19092").strip()
            _kafka_producer = KafkaProducer(
                bootstrap_servers=[x.strip() for x in bootstrap.split(",") if x.strip()],
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
                key_serializer=lambda v: (v or "").encode("utf-8"),
                acks=1,
                retries=2,
                linger_ms=50,
                request_timeout_ms=15000,
                metadata_max_age_ms=30000,
            )
            _logger.info("AMP Kafka producer ready → %s", bootstrap)
            return _kafka_producer
        except Exception as exc:  # noqa: BLE001
            _kafka_failed = True
            _logger.warning("AMP Kafka 不可用，仅写本地日志: %s", exc)
            return None


def _publish(topic: str, record: dict[str, Any], *, key: str | None = None) -> None:
    producer = _get_kafka_producer()
    if producer is None:
        return
    try:
        producer.send(topic, key=key or record.get("aic") or "", value=record)
        # 不强制 flush 每条，周期/进程退出时由 linger 批量发出；关键路径额外 flush
        if os.getenv("AMP_KAFKA_FLUSH", "1").strip() not in ("0", "false"):
            producer.flush(timeout=3)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("AMP Kafka 发送失败 topic=%s: %s", topic, exc)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _http_ingest(record: dict[str, Any]) -> None:
    url = (os.getenv("AMP_HTTP_INGEST_URL") or "").strip()
    if not url:
        return
    try:
        import httpx

        httpx.post(url, json=record, timeout=2.0)
    except Exception:  # noqa: BLE001
        pass


def _build_access_record(
    *,
    task_id: str,
    local_aic: str,
    peer_aic: str,
    direction: Literal["send", "receive"],
    endpoint: str | None,
    status: str,
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    """规范 AccessLogRecord（correlationId=taskId）。"""
    caller_aic = local_aic if direction == "send" else peer_aic
    callee_aic = peer_aic if direction == "send" else local_aic
    status_code = 200
    st = (status or "").lower()
    if any(x in st for x in ("fail", "reject", "error", "timeout")):
        status_code = 500

    body = {
        "request": {
            "method": "POST",
            "route": "/rpc",
            "url": endpoint or "",
        },
        "response": {"statusCode": status_code},
        "caller": {
            "aic": caller_aic,
            "serviceName": "agentlink-leader" if direction == "send" else "agentlink-peer",
        },
        "callee": {
            "aic": callee_aic,
            "serviceName": "agentlink-partner" if direction == "send" else "agentlink-local",
        },
    }
    if extra:
        body["attributes"] = extra

    return {
        "schema_version": "1.0",
        "log_id": _new_log_id(),
        "log_type": "access",
        "timestamp": _iso_now(),
        "aic": local_aic,
        "correlation_id": task_id,
        "correlationId": task_id,  # 兼容平台 camelCase 消费
        "body": body,
        "resource": {
            "service.name": "agentlink",
            "agentlink.direction": direction,
            "agentlink.taskId": task_id,
        },
    }


def _build_message_record(
    *,
    task_id: str,
    local_aic: str,
    peer_aic: str,
    direction: Literal["send", "receive"],
    endpoint: str | None,
    status: str,
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    """规范 MessageLogRecord：双侧同 messageId，eventType=send|receive。"""
    event_type: Literal["send", "receive"] = "send" if direction == "send" else "receive"
    message_id = _message_id_for_task(task_id)
    dest_name = endpoint or f"aip-rpc/{peer_aic[-16:] if peer_aic else 'peer'}"
    # Partner 入站 Start 记 receive，语义仍是 TaskCommand；结果回传才是 TaskResult
    op = "aip.TaskCommand"
    if event_type == "receive" and str((extra or {}).get("phase") or "").lower() in (
        "result",
        "complete",
        "completion",
    ):
        op = "aip.TaskResult"
    body: dict[str, Any] = {
        "eventType": event_type,
        "operationName": op,
        "system": "aip-rpc",
        "destination": {"name": dest_name, "kind": "topic"},
        "messageId": message_id,
        "attributes": {
            "peerAic": peer_aic,
            "taskState": status,
            **(extra or {}),
        },
    }
    return {
        "schema_version": "1.0",
        "log_id": _new_log_id(),
        "log_type": "message",
        "timestamp": _iso_now(),
        "aic": local_aic,
        "correlation_id": task_id,
        "correlationId": task_id,
        "body": body,
        "resource": {
            "service.name": "agentlink",
            "agentlink.direction": direction,
            "agentlink.taskId": task_id,
            "agentlink.messageId": message_id,
        },
    }


def record_access(
    *,
    task_id: str,
    local_aic: str,
    peer_aic: str,
    direction: str,
    endpoint: str | None = None,
    status: str = "ok",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """写入 Access + 配对 Message，并尽力上报平台 Kafka。"""
    tid = (task_id or "").strip()
    if not tid:
        tid = f"task-{uuid4().hex[:12]}"
    direction_norm: Literal["send", "receive"] = (
        "receive" if str(direction).lower() in ("receive", "recv", "inbound", "callee") else "send"
    )

    access = _build_access_record(
        task_id=tid,
        local_aic=local_aic or "unknown-aic",
        peer_aic=peer_aic or "",
        direction=direction_norm,
        endpoint=endpoint,
        status=status,
        extra=extra,
    )
    message = _build_message_record(
        task_id=tid,
        local_aic=local_aic or "unknown-aic",
        peer_aic=peer_aic or "",
        direction=direction_norm,
        endpoint=endpoint,
        status=status,
        extra=extra,
    )

    try:
        _append_jsonl(_ACCESS_LOG, access)
    except Exception:  # noqa: BLE001
        _logger.warning("写 amp_access.jsonl 失败", exc_info=True)
    try:
        _append_jsonl(_MESSAGE_LOG, message)
    except Exception:  # noqa: BLE001
        _logger.warning("写 amp_message.jsonl 失败", exc_info=True)

    access_topic = (os.getenv("AMP_ACCESS_TOPIC") or "amp.access").strip()
    message_topic = (os.getenv("AMP_MESSAGE_TOPIC") or "amp.message").strip()
    _publish(access_topic, access, key=tid)
    _publish(message_topic, message, key=tid)
    _http_ingest(access)
    _http_ingest(message)

    return {"access": access, "message": message}


def record_message(
    *,
    task_id: str,
    local_aic: str,
    peer_aic: str,
    direction: str,
    endpoint: str | None = None,
    status: str = "ok",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """仅 Message（一般不必单独调；record_access 已联写）。"""
    tid = (task_id or "").strip() or f"task-{uuid4().hex[:12]}"
    direction_norm: Literal["send", "receive"] = (
        "receive" if str(direction).lower() in ("receive", "recv", "inbound", "callee") else "send"
    )
    message = _build_message_record(
        task_id=tid,
        local_aic=local_aic or "unknown-aic",
        peer_aic=peer_aic or "",
        direction=direction_norm,
        endpoint=endpoint,
        status=status,
        extra=extra,
    )
    try:
        _append_jsonl(_MESSAGE_LOG, message)
    except Exception:  # noqa: BLE001
        pass
    _publish((os.getenv("AMP_MESSAGE_TOPIC") or "amp.message").strip(), message, key=tid)
    return message


def _heartbeat_enabled() -> bool:
    if os.getenv("AMP_HEARTBEAT_ENABLED", "1").strip() in ("0", "false", "False", "no"):
        return False
    return _kafka_enabled() or True  # 即使 Kafka 关也写本地日志


def _heartbeat_interval_sec() -> float:
    try:
        return max(5.0, float(os.getenv("AMP_HEARTBEAT_INTERVAL_SEC") or "30"))
    except ValueError:
        return 30.0


def record_heartbeat(
    *,
    local_aic: str,
    agent_id: str | None = None,
    uptime_seconds: float | None = None,
) -> dict[str, Any]:
    """写一条 AMP Heartbeat（本地 NDJSON + Kafka amp.heartbeat）。"""
    aic = (local_aic or "").strip() or "unknown-aic"
    if uptime_seconds is None:
        started = _hb_started_at.get(aic) or time.monotonic()
        uptime_seconds = round(time.monotonic() - started, 3)
    record: dict[str, Any] = {
        "schema_version": "1.0",
        "log_id": _new_log_id(),
        "log_type": "heartbeat",
        "timestamp": _iso_now(),
        "aic": aic,
        "body": {"uptimeSeconds": float(uptime_seconds)},
        "resource": {
            "service.name": "agentlink",
            "agentlink.agent_id": agent_id or "",
        },
    }
    try:
        _append_jsonl(_HEARTBEAT_LOG, record)
    except Exception:  # noqa: BLE001
        _logger.warning("写 amp_heartbeat.jsonl 失败", exc_info=True)

    topic = (os.getenv("AMP_HEARTBEAT_TOPIC") or "amp.heartbeat").strip()
    # 心跳高频：默认不强制每条 flush，减轻 Kafka 压力
    producer = _get_kafka_producer()
    if producer is not None:
        try:
            producer.send(topic, key=aic, value=record)
            if os.getenv("AMP_HEARTBEAT_FLUSH", "0").strip() not in ("0", "false", "False"):
                producer.flush(timeout=2)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("AMP heartbeat Kafka 发送失败: %s", exc)
    _http_ingest(record)
    return record


def start_heartbeat(*, aic: str, agent_id: str | None = None, interval_sec: float | None = None) -> bool:
    """后台线程周期上报心跳；同 AIC 只启一次。返回是否新启动。"""
    if not _heartbeat_enabled():
        _logger.info("AMP heartbeat disabled")
        return False
    aic_key = (aic or "").strip() or "unknown-aic"
    with _hb_lock:
        th = _hb_threads.get(aic_key)
        if th and th.is_alive():
            return False
        stop = threading.Event()
        _hb_stop[aic_key] = stop
        _hb_started_at[aic_key] = time.monotonic()
        interval = float(interval_sec) if interval_sec is not None else _heartbeat_interval_sec()

        def _loop() -> None:
            _logger.info(
                "AMP heartbeat started aic=%s agent=%s interval=%ss",
                aic_key,
                agent_id or "",
                interval,
            )
            # 立即首拍，便于验收
            try:
                record_heartbeat(local_aic=aic_key, agent_id=agent_id)
            except Exception:  # noqa: BLE001
                _logger.warning("AMP heartbeat 首拍失败", exc_info=True)
            while not stop.wait(interval):
                try:
                    record_heartbeat(local_aic=aic_key, agent_id=agent_id)
                except Exception:  # noqa: BLE001
                    _logger.warning("AMP heartbeat 周期失败", exc_info=True)

        t = threading.Thread(target=_loop, name=f"amp-hb-{agent_id or aic_key[-8:]}", daemon=True)
        _hb_threads[aic_key] = t
        t.start()
        return True


def stop_heartbeat(*, aic: str | None = None) -> None:
    """停止指定 AIC 或全部心跳线程。"""
    with _hb_lock:
        keys = [aic.strip()] if aic and aic.strip() else list(_hb_stop.keys())
        for k in keys:
            ev = _hb_stop.pop(k, None)
            if ev:
                ev.set()
            _hb_threads.pop(k, None)
