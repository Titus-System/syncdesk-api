from enum import Enum

from pydantic import BaseModel


class DeviceType(Enum):
    MOBILE = "mobile"
    TABLET = "tablet"
    DESKTOP = "desktop"


class SessionDeviceInfo(BaseModel):
    user_agent: str | None = None
    ip_address: str | None = None
    device_type: DeviceType | None = None
    os: str | None = None
    browser: str | None = None
    app_version: str | None = None

    def fingerprint(self) -> str:
        f_values = [self.device_type.value if self.device_type else None, self.os, self.browser]
        return " | ".join([str(v) for v in f_values if v is not None])
