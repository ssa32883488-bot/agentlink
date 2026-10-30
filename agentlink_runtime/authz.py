from __future__ import annotations

from enum import Enum


class AuthzLevel(str, Enum):
    SUGGEST = "suggest"
    NEGOTIATE = "negotiate"
    COMMIT = "commit"


_RANK = {
    AuthzLevel.SUGGEST: 1,
    AuthzLevel.NEGOTIATE: 2,
    AuthzLevel.COMMIT: 3,
}


def allows(current: AuthzLevel | str, required: AuthzLevel | str) -> bool:
    cur = AuthzLevel(current)
    req = AuthzLevel(required)
    return _RANK[cur] >= _RANK[req]
