"""站点自动打标签（入口/无效），移植自原 app/services/autoTag.py。"""
from __future__ import annotations

from ..modules import SiteAutoTag


class AutoTag:
    def __init__(self, site_info: dict):
        self.site_info = site_info
        self.status = self.site_info.get("status", 0)
        self.title = self.site_info.get("title", "")
        self.headers = self.site_info.get("headers", "")

    def run(self):
        body_length = self.site_info.get("body_length", 0)

        if self.is_invalid_title():
            return self._set_invalid_tag()

        if not self.title and "/html" in self.headers:
            if body_length >= 200 and self.status == 200:
                self._set_entry_tag()
                return

        if body_length <= 300:
            if not self.is_redirected() and not self.title:
                self._set_invalid_tag()
                return

        if body_length <= 1000:
            if self.is_40x() or self.is_50x():
                self._set_invalid_tag()
                return

        if self.is_redirected():
            if not self.is_out():
                self._set_invalid_tag()
                return
            if "Location: https://url.cn/sorry" in self.headers:
                self._set_invalid_tag()
                return
            for line in self.headers.split("\n"):
                if "Location:" in line:
                    hostname = self.site_info.get("hostname")
                    if hostname and hostname in line:
                        return self._set_invalid_tag()
                    return self._set_entry_tag()
            return self._set_invalid_tag()

        self._set_entry_tag()

    def is_redirected(self):
        return self.status in [301, 302, 303]

    def is_40x(self):
        return self.status in [401, 403, 404]

    def is_50x(self):
        return self.status in [500, 501, 502, 503, 504]

    def _set_entry_tag(self):
        self.site_info["tag"] = [SiteAutoTag.ENTRY]

    def _set_invalid_tag(self):
        self.site_info["tag"] = [SiteAutoTag.INVALID]

    def is_invalid_title(self):
        invalid_title = ["Welcome to nginx", "IIS7", "Apache Tomcat",
                         "Welcome to CentOS", "Apache HTTP Server Test Page",
                         "Test Page for the Nginx HTTP", "500 Internal Server Error",
                         "Error 404--Not Found", "Welcome to OpenResty",
                         "没有找到站点", "404 not found", "页面不存在", "访问拦截",
                         "403 Forbidden", "Page Not Found"]
        return any(t in self.title for t in invalid_title)

    def is_out(self):
        return any(o in self.headers for o in
                   ["Location: https://", "Location: http://", "Location: //"])


def auto_tag(site_info):
    if isinstance(site_info, list):
        for info in site_info:
            AutoTag(info).run()
        return site_info
    if isinstance(site_info, dict):
        AutoTag(site_info).run()
        return site_info
