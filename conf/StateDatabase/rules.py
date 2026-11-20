# /usr/bin/python
"""Initialize the 'rules' database from a YAML configuration file.

The rules themselves are not meant to be edited here: they are generated from a set of rule templates (one per
rule kind) and the parameters given in the configuration file. By default, the configuration file is 'rules.yml',
located in the same directory as this script, but another one can be passed as the first argument:

    python3 conf/StateDatabase/rules.py [path/to/rules.yml]

See 'rules.yml' for a description of the configuration format.
"""
import os
import sys

import yaml

import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils

DEFAULT_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.yml")


## Helpers to reference the variables available in the rule context
def _structure(resource, field):
    return {"var": "{0}.structure.{0}.{1}".format(resource, field)}


def _limit(resource, field):
    return {"var": "{0}.limits.{0}.{1}".format(resource, field)}


def _events(path):
    return {"var": "events.{0}".format(path)}


## Event rules (generate events used by request rules), named '<resource>_<kind>' (e.g., cpu_exceeded_upper)
def _exceeded_upper(r):
    # Usage is over the upper limit and the resource can still be scaled up
    return dict(
        rule={"and": [
            {">": [_structure(r, "usage"), _limit(r, "upper")]},
            {"<": [_limit(r, "upper"), _structure(r, "max")]},
            {"<": [_structure(r, "current"), _structure(r, "max")]}]},
        generates="events",
        action={"events": {"scale": {"up": 1}}})


def _dropped_lower(r, ignore_zero_usage):
    # Usage is under the lower limit and the resource can still be scaled down
    return dict(
        rule={"and": [
            {">" if ignore_zero_usage else ">=": [_structure(r, "usage"), 0]},
            {"<": [_structure(r, "usage"), _limit(r, "lower")]},
            {">": [_limit(r, "lower"), _structure(r, "min")]}]},
        generates="events",
        action={"events": {"scale": {"down": 1}}})


def _idle(r, usage_factor):
    # Usage is under a fraction of the minimum, the resource is already at its minimum and nothing is lent
    return dict(
        rule={"and": [
            {">=": [_structure(r, "usage"), 0]},
            {"<": [_structure(r, "usage"), {"*": [_structure(r, "min"), usage_factor]}]},
            {"<=": [_limit(r, "lower"), _structure(r, "min")]},
            {"!": [_structure(r, "lent")]}]},
        generates="events",
        action={"events": {"idle": 1}})


def _reclaim(r, usage_factor):
    # Some amount of the resource is lent and usage is over a fraction of the minimum
    return dict(
        rule={"and": [
            {"!!": [_structure(r, "lent")]},
            {">=": [_structure(r, "usage"), {"*": [_structure(r, "min"), usage_factor]}]}]},
        generates="events",
        action={"events": {"reclaim": 1}})


## Request rules (generate scaling requests from events), named '<Resource><Kind>' (e.g., CpuRescaleUp)
def _requests_rule(trigger_event, trigger_amount, rescale_type, rescale_policy, events_to_remove,
                   blocking_event=None, max_blocking_events=None, amount=None):
    conditions = [{">=": [_events(trigger_event), trigger_amount]}]
    if blocking_event:
        conditions.append({"<=": [_events(blocking_event), max_blocking_events]})
    doc = dict(
        rule={"and": conditions},
        generates="requests",
        events_to_remove=trigger_amount if events_to_remove is None else events_to_remove,
        rescale_policy=rescale_policy,
        rescale_type=rescale_type)
    if amount is not None:
        doc["amount"] = amount
    return doc


def _rescale_up(r, up_events, max_down_events, rescale_policy, amount=None, events_to_remove=None):
    return _requests_rule("scale.up", up_events, "up", rescale_policy, events_to_remove,
                          "scale.down", max_down_events, amount)


def _rescale_down(r, down_events, max_up_events, rescale_policy, amount=None, events_to_remove=None):
    return _requests_rule("scale.down", down_events, "down", rescale_policy, events_to_remove,
                          "scale.up", max_up_events, amount)


def _lend(r, idle_events, max_up_events, events_to_remove=None):
    return _requests_rule("idle", idle_events, "lend", "lend_current", events_to_remove,
                          "scale.up", max_up_events)


def _reclaim_lent(r, reclaim_events, events_to_remove=None):
    return _requests_rule("reclaim", reclaim_events, "reclaim", "reclaim_lent", events_to_remove)


## ReBalancer rules (evaluated by the ReBalancer, not the Guardian), named '<resource>_<kind>'
def _usage_high(r, min_margin, usage_ratio):
    # There is room to scale up (max - current) and usage is over a fraction of the current allocation
    return dict(
        rule={"and": [
            {">=": [{"-": [_structure(r, "max"), _structure(r, "current")]}, min_margin]},
            {">": [{"/": [_structure(r, "usage"), _structure(r, "current")]}, usage_ratio]}]},
        generates="")


def _usage_low(r, min_margin, usage_ratio):
    # There is room to scale down (current - min) and usage is under a fraction of the current allocation
    return dict(
        rule={"and": [
            {">=": [{"-": [_structure(r, "current"), _structure(r, "min")]}, min_margin]},
            {"<": [{"/": [_structure(r, "usage"), _structure(r, "current")]}, usage_ratio]}]},
        generates="")


def _event_name(resource, kind):
    return "{0}_{1}".format(resource, kind)


def _request_name(resource, kind):
    return "{0}{1}".format(resource.capitalize(), kind)


# Rule group -> (function to build the rule name, {kind: template})
RULE_TEMPLATES = {
    "events": (_event_name, {
        "exceeded_upper": _exceeded_upper,
        "dropped_lower": _dropped_lower,
        "idle": _idle,
        "reclaim": _reclaim,
    }),
    "requests": (_request_name, {
        "RescaleUp": _rescale_up,
        "RescaleDown": _rescale_down,
        "Lend": _lend,
        "Reclaim": _reclaim_lent,
    }),
    "rebalancer": (_event_name, {
        "usage_high": _usage_high,
        "usage_low": _usage_low,
    }),
}


def _new_rule(name, resource, active, fields):
    return dict(_id=name, type="rule", name=name, resource=resource, active=active, **fields)


def build_template_rule(resource, group, kind, params):
    if group not in RULE_TEMPLATES:
        raise ValueError("Unknown rule group '{0}' in resource '{1}', expected one of: {2}".format(
            group, resource, ", ".join(RULE_TEMPLATES)))
    get_name, templates = RULE_TEMPLATES[group]
    if kind not in templates:
        raise ValueError("Unknown rule '{0}' in '{1}.{2}', expected one of: {3}".format(
            kind, resource, group, ", ".join(templates)))

    params = dict(params or {})
    active = params.pop("active", True)
    name = get_name(resource, kind)
    try:
        fields = templates[kind](resource, **params)
    except TypeError as e:
        raise ValueError("Invalid parameters for rule '{0}': {1}".format(name, e))
    if fields["generates"] == "requests":
        fields["action"] = {"requests": [name]}
    return _new_rule(name, resource, active, fields)


def build_custom_rule(rule):
    rule = dict(rule)
    missing = [f for f in ("name", "resource", "rule", "generates") if f not in rule]
    if missing:
        raise ValueError("Custom rule {0} is missing required fields: {1}".format(rule, ", ".join(missing)))
    name, resource, active = rule.pop("name"), rule.pop("resource"), rule.pop("active", True)
    return _new_rule(name, resource, active, rule)


def build_rules(config):
    rules = []
    for resource, groups in (config.get("rules") or {}).items():
        for group, kinds in (groups or {}).items():
            for kind, params in (kinds or {}).items():
                rules.append(build_template_rule(resource, group, kind, params))
    rules.extend(build_custom_rule(rule) for rule in config.get("custom_rules") or [])

    # Rules are always built (and thus validated), but only those of the enabled resources are loaded
    enabled_resources = config.get("resources")
    if enabled_resources is not None:
        rules = [r for r in rules if r["resource"] in enabled_resources]

    names = [r["name"] for r in rules]
    duplicated = sorted({n for n in names if names.count(n) > 1})
    if duplicated:
        raise ValueError("Duplicated rule names: {0}".format(", ".join(duplicated)))
    return rules


def load_config(config_file):
    with open(config_file, "r") as f:
        return yaml.safe_load(f) or {}


if __name__ == "__main__":
    config_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG_FILE
    # Build the rules before touching the database, so an invalid configuration does not leave it empty
    rules = build_rules(load_config(config_file))

    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    database = "rules"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)
    if handler.database_exists(database):
        print("Adding 'rules' documents from {0}".format(config_file))
        for rule in rules:
            handler.add_rule(rule)
