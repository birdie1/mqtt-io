"""
Main entrypoint when MQTT IO is invoked as `python -m mqtt_io`.
"""
import argparse
import logging.config
import sys
from copy import deepcopy
from hashlib import sha256
from typing import Any, Optional

from mqtt_io.types import ConfigType

from . import VERSION
from .config import load_main_config
from .exceptions import ConfigValidationFailed
from .modules import install_missing_requirements
from .server import MqttIo

_LOG = logging.getLogger('mqtt_io.__main__')


def hashed(value: Any) -> str:
    """
    Return the string representation of the value, hashed.
    """
    return sha256(str(value).encode("utf8")).hexdigest()


def redact_config(config: ConfigType) -> ConfigType:
    """
    Remove secret information from the config file.
    """
    ret = deepcopy(config)
    mqtt_config = config["mqtt"]
    ret["mqtt"]["host"] = hashed(mqtt_config["host"])
    if "password" in mqtt_config:
        ret["mqtt"]["password"] = "<provided but redacted>"
    for mqtt_section in ("host", "port", "user"):
        if mqtt_config[mqtt_section]:
            ret["mqtt"][mqtt_section] = hashed(mqtt_config[mqtt_section])
    return ret


def main() -> None:
    """
    Main entrypoint function.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    # Load, validate and normalise config, or quit.
    try:
        config = load_main_config(args.config)
    except ConfigValidationFailed as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    if config["logging"]:
        logging.config.dictConfig(config["logging"])

    if config.get("reporting", {}).get("enabled"):
        # pylint: disable=import-outside-toplevel
        try:
            import sentry_sdk  # type: ignore
        except ImportError:
            install_missing_requirements(["sentry-sdk"])
            import sentry_sdk  # type: ignore

        issue_id: Optional[int] = config["reporting"].get("issue_id")

        sentry_sdk.init(
            "https://e3db7fd828ff468fb6caebd3953a69a2@o549418.ingest.sentry.io/5672194",
            traces_sample_rate=1.0,
            release=VERSION,
        )
        sentry_sdk.set_context("config", redact_config(config))
        if issue_id is not None:
            sentry_sdk.set_tag("issue_id", issue_id)
    try:
        mqtt_gpio = MqttIo(config)
        mqtt_gpio.run()
    except Exception:
        _LOG.exception('MqttIo crashed!')
        raise


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("")
