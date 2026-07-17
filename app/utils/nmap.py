"""nmap 封装，使用 python-nmap 库（线程池中同步调用）。"""
from __future__ import annotations

import nmap as _nmap


class PortScanner(_nmap.PortScanner):
    """直接继承 python-nmap 的 PortScanner。"""
    pass
