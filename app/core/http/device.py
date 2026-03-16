import re

from fastapi import Request

from app.core.http.schemas import DeviceType, SessionDeviceInfo

_CH_UA_RE = re.compile(r'"(?P<brand>[^"]+)";v="(?P<version>\d+)"')


def parse_sec_ch_ua(value: str) -> tuple[str | None, str | None]:
    """
    Returns (browser, version)
    """
    matches = _CH_UA_RE.findall(value)
    if not matches:
        return None, None

    # Prefer real browsers over "Not A(Brand)"
    for brand, version in matches:
        if "Not A" not in brand:
            return brand, version

    # Fallback to first
    brand, version = matches[0]
    return brand, version


def get_device_info(
    request: Request,
) -> SessionDeviceInfo:
    headers = request.headers

    user_agent = headers.get("user-agent")

    ip_address = request.client.host if request.client else None
    if ip_address:
        ip_address = ip_address.split(",")[0].strip()

    browser = None
    app_version = None

    sec_ch_ua = headers.get("sec-ch-ua")
    if sec_ch_ua:
        browser, app_version = parse_sec_ch_ua(sec_ch_ua)

    os = headers.get("sec-ch-ua-platform")
    if os:
        os = os.strip('"')

    mobile = headers.get("sec-ch-ua-mobile")
    if mobile == "?1":
        device_type = DeviceType.MOBILE
    elif mobile == "?0":
        device_type = DeviceType.DESKTOP
    else:
        device_type = None

    session_device_info = SessionDeviceInfo(
        user_agent=user_agent,
        ip_address=ip_address,
        browser=browser,
        app_version=app_version,
        os=os,
        device_type=device_type,
    )

    return session_device_info
