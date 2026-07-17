"""SSL 证书解析，移植自原 app/utils/cert.py。

get_cert 改为同步函数（在 asyncio 线程池中调用），保持解析逻辑不变。
pyOpenSSL 的 crypto 模块在 23.x 之后已迁移到 cryptography，这里兼容两者。
"""
from __future__ import annotations

import socket
import ssl
from datetime import datetime

socket.setdefaulttimeout(6)


def _load_cert_x509(certs_pem: str):
    """从 PEM 文本加载 X509 对象，兼容新旧 pyOpenSSL。"""
    try:
        from OpenSSL import crypto
        return crypto.load_certificate(crypto.FILETYPE_PEM, certs_pem)
    except Exception:
        # 新版 pyOpenSSL 已移除 crypto.load_certificate，回退到 cryptography
        import cryptography.hazmat.backends
        import cryptography.x509
        return cryptography.x509.load_pem_x509_certificate(certs_pem.encode())


def parse_certs(certs_pem: str) -> dict:
    """解析证书 PEM 文本为结构化字典（字段与原实现一致）。"""
    result: dict = {}
    ospj = _load_cert_x509(certs_pem)

    def _attr(obj, name):
        # 兼容 pyOpenSSL X509Name（.CN 属性）与 cryptography（rfc4514_string）
        try:
            return getattr(obj, name, None)
        except Exception:
            return None

    # subject / issuer —— 优先 pyOpenSSL 风格
    subject = getattr(ospj, "get_subject", lambda: None)()
    issuer = getattr(ospj, "get_issuer", lambda: None)()

    def _g(o, key):
        if o is None:
            return None
        v = _attr(o, key)
        if v is None and hasattr(o, "country_name"):
            mapping = {
                "C": "country_name", "ST": "state_or_province_name", "L": "locality_name",
                "O": "organization_name", "OU": "organizational_unit_name",
                "CN": "common_name", "emailAddress": "email_address",
            }
            v = getattr(o, mapping.get(key, ""), None)
        return v

    subject_dn = f"C={_g(subject, 'C')}, CN={_g(subject, 'CN')}"
    if _g(subject, "O"):
        subject_dn += f" ,O={_g(subject, 'O')}"

    issuser_obj = {
        "country": _g(issuer, "C"),
        "province": _g(issuer, "ST"),
        "locality": _g(issuer, "L"),
        "organizational": _g(issuer, "O"),
        "organizational_unit": _g(issuer, "OU"),
        "common_name": _g(issuer, "CN"),
        "email": _g(issuer, "emailAddress"),
    }
    issuer_dn = f"C={_g(issuer, 'CN')}, O={_g(issuer, 'O')}, OU={_g(issuer, 'OU')}, CN={_g(issuer, 'CN')}"

    # 签名算法 / 序列号 / 有效期 / 版本
    try:
        signature_algorithm = ospj.get_signature_algorithm().decode()
    except Exception:
        signature_algorithm = ospj.signature_algorithm_oid._name

    serial_number = ospj.get_serial_number() if hasattr(ospj, "get_serial_number") else ospj.serial_number

    def _nb():
        v = ospj.get_notBefore() if hasattr(ospj, "get_notBefore") else ospj.not_valid_before_utc
        v = v.decode() if isinstance(v, bytes) else v.strftime('%Y%m%d%H%M%SZ')
        return str(datetime.strptime(v, '%Y%m%d%H%M%SZ'))

    def _na():
        v = ospj.get_notAfter() if hasattr(ospj, "get_notAfter") else ospj.not_valid_after_utc
        v = v.decode() if isinstance(v, bytes) else v.strftime('%Y%m%d%H%M%SZ')
        return str(datetime.strptime(v, '%Y%m%d%H%M%SZ'))

    def _expired():
        if hasattr(ospj, "has_expired"):
            return ospj.has_expired()
        return datetime.utcnow() > ospj.not_valid_after_utc

    validity_obj = {"start": _nb(), "end": _na(), "expired": _expired()}
    version = (ospj.get_version() + 1) if hasattr(ospj, "get_version") else ospj.version.value + 1

    fingerprint_obj = {}
    if hasattr(ospj, "digest"):
        fingerprint_obj['sha1'] = ospj.digest('sha1').decode().replace(":", "").lower()
        fingerprint_obj['sha256'] = ospj.digest('sha256').decode().replace(":", "").lower()
        fingerprint_obj['md5'] = ospj.digest('md5').decode().replace(":", "").lower()
    else:
        import hashlib
        der = ospj.public_bytes(encoding_pem_false()) if False else ospj.fingerprint.__self__.public_bytes.__self__.public_bytes(0)
        fingerprint_obj['sha1'] = ospj.fingerprint(hashlib.sha1).hex()
        fingerprint_obj['sha256'] = ospj.fingerprint(hashlib.sha256).hex()
        fingerprint_obj['md5'] = ospj.fingerprint(hashlib.md5).hex()

    extensions = {}
    if hasattr(ospj, "get_extension_count"):
        exn_num = 0
        while exn_num < ospj.get_extension_count():
            ext = ospj.get_extension(exn_num)
            ext_name = ext.get_short_name().decode() if isinstance(ext.get_short_name(), bytes) else str(ext.get_short_name())
            extensions[ext_name] = str(ext)
            exn_num += 1

    subject_obj = {
        "country": _g(subject, "C"),
        "province": _g(subject, "ST"),
        "locality": _g(subject, "L"),
        "organizational": _g(subject, "O"),
        "organizational_unit": _g(subject, "OU"),
        "common_name": _g(subject, "CN"),
        "email": _g(subject, "emailAddress"),
    }

    result['subject_dn'] = subject_dn
    result['issuer'] = issuser_obj
    result['signature_algorithm'] = signature_algorithm
    result['serial_number'] = str(serial_number)
    result['validity'] = validity_obj
    result['issuer_dn'] = issuer_dn
    result['version'] = version
    result['extensions'] = extensions
    result['subject'] = subject_obj
    result['fingerprint'] = fingerprint_obj
    return result


def get_cert(host: str, port: int) -> dict | None:
    """同步获取并解析 SSL 证书（在 asyncio 线程池中调用）。"""
    from ..logger import get_logger
    logger = get_logger()
    try:
        certs = ssl.get_server_certificate((host, port))
        return parse_certs(certs)
    except Exception as e:
        logger.debug(f"get cert error {host}:{port} {e}")
        return None
