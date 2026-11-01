"""Keep editable MA rows and their independent conditions synchronized."""
import re

from .models import RELATION_METHODS, Rule


def rename_references(rule, mapping):
    aliases = dict(mapping)
    aliases.update({"MA" + old[3:]: new for old, new in mapping.items() if old.startswith("SMA")})
    if aliases:
        pattern = r"(?<!\w)(?:" + "|".join(re.escape(k) for k in sorted(aliases, key=len, reverse=True)) + r")(?!\w)"
        rule.name = re.sub(pattern, lambda m: aliases[m.group()], rule.name)
    rule.ma = mapping.get(rule.ma, rule.ma)
    rule.other = mapping.get(rule.other, rule.other)


def sync_averages(config, averages, mapping=None, added=()):
    """Pause dependent rules without losing intentional manual disabling or settings."""
    keys = [ma.key for ma in averages]
    if len(keys) != len(set(keys)):
        raise ValueError("Each moving average needs a unique type and period")
    for ma in averages:
        ma.validate()
    before = {r.id: (r.ma, r.other, r.name, r.enabled) for r in config.rules}
    for rule in config.rules:
        rename_references(rule, mapping or {})
    config.moving_averages = averages
    for ma in averages:
        if ma.key in added and not any(r.ma == ma.key and r.method not in RELATION_METHODS for r in config.rules):
            config.rules.append(Rule(name=f"{ma.key} slope positive", ma=ma.key, enabled=ma.enabled,
                                     paused_by_ma=not ma.enabled))
    active = {ma.key for ma in averages if ma.enabled}
    for rule in config.rules:
        dependencies = {rule.ma} - {"PRICE"}
        if rule.method in RELATION_METHODS:
            dependencies.add(rule.other)
        if not dependencies <= active:
            if rule.enabled:
                rule.enabled, rule.paused_by_ma = False, True
        elif rule.paused_by_ma:
            rule.enabled, rule.paused_by_ma = True, False
    return {r.id: r for r in config.rules if before.get(r.id) != (r.ma, r.other, r.name, r.enabled)}
