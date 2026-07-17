"""utils 包：工具函数集合（异步化）。

对外暴露与原 app/utils/__init__.py 等价的接口：
    conn_db, http_req, get_logger, is_valid_domain, check_domain_black,
    get_ip, get_cname, domain_parsed, get_fld, gen_md5, ...
"""
from __future__ import annotations

# 数据库（motor 异步）
from ..database import conn_db, get_client, get_db

# 日志
from ..logger import get_logger

# HTTP 客户端
from ..core.http_client import http_req, http_req_simple, HttpResponse

# DNS
from ..core.dns import get_ip, get_cname, domain_parsed, get_fld

# 时间
from .time_util import curr_date, curr_date_obj, time2date, date2time, parse_datetime

# 域名校验
from .domain_util import (
    check_domain_black,
    is_forbidden_domain,
    is_in_scope,
    is_in_scopes,
    is_valid_domain,
    is_valid_fuzz_domain,
    cut_first_name,
)

# IP
from .ip_util import (
    get_ip_asn,
    get_ip_city,
    get_ip_type,
    ip_in_scope,
    is_vaild_ip_target,
    not_in_black_ips,
    transfer_ip_scope,
)

# URL
from .url_util import (
    cut_filename,
    get_hostname,
    normal_url,
    rm_similar_url,
    same_netloc,
    url_ext,
    urlsimilar,
)

# HTTP 解析
from .http_util import get_headers_text, get_title

# CDN / 证书
from .cdn import get_cdn_name_by_cname, get_cdn_name_by_ip
from .cert import get_cert, parse_certs

# 系统/子进程
from .system_util import (
    build_port_custom,
    check_output,
    exec_system,
    gen_filename,
    gen_md5,
    is_valid_exclude_ports,
    random_choices,
    truncate_string,
)

# 资产聚合
from .arl import (
    arl_domain,
    gen_cip_map,
    gen_stat_finger_map,
    get_asset_domain_by_id,
    get_domain_by_id,
    get_monitor_domain_by_id,
    get_scope_ids,
    get_task_ids,
    scope_data_by_id,
    task_statistic,
)

# 认证
from .user import change_pass, init_admin_user, user_login, user_login_by_token, user_logout

# 推送
from .push import dict2dingding_mark, dict2table, message_push

# cron
from .cron_util import check_cron, check_cron_interval

# 指纹规则工具
from ..core.fingerprint.rules import parse_human_rule, transform_rule_map

# 查询插件加载
from .query_loader import load_query_plugins

# 文件读取辅助
def load_file(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        return f.readlines()


__all__ = [
    # db
    "conn_db", "get_client", "get_db",
    # logger
    "get_logger",
    # http
    "http_req", "http_req_simple", "HttpResponse",
    # dns
    "get_ip", "get_cname", "domain_parsed", "get_fld",
    # time
    "curr_date", "curr_date_obj", "time2date", "date2time", "parse_datetime",
    # domain
    "check_domain_black", "is_forbidden_domain", "is_in_scope", "is_in_scopes",
    "is_valid_domain", "is_valid_fuzz_domain", "cut_first_name",
    # ip
    "get_ip_asn", "get_ip_city", "get_ip_type", "ip_in_scope",
    "is_vaild_ip_target", "not_in_black_ips", "transfer_ip_scope",
    # url
    "cut_filename", "get_hostname", "normal_url", "rm_similar_url",
    "same_netloc", "url_ext", "urlsimilar",
    # http parse
    "get_headers_text", "get_title",
    # cdn / cert
    "get_cdn_name_by_cname", "get_cdn_name_by_ip", "get_cert", "parse_certs",
    # system
    "build_port_custom", "check_output", "exec_system", "gen_filename", "gen_md5",
    "is_valid_exclude_ports", "random_choices", "truncate_string",
    # arl
    "arl_domain", "gen_cip_map", "gen_stat_finger_map", "get_asset_domain_by_id",
    "get_domain_by_id", "get_monitor_domain_by_id", "get_scope_ids", "get_task_ids",
    "scope_data_by_id", "task_statistic",
    # user
    "change_pass", "init_admin_user", "user_login", "user_login_by_token", "user_logout",
    # push
    "dict2dingding_mark", "dict2table", "message_push",
    # cron
    "check_cron", "check_cron_interval",
    # fingerprint
    "parse_human_rule", "transform_rule_map",
    # plugins
    "load_query_plugins",
    # misc
    "load_file",
]
