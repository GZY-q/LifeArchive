"""M0 worker entry point: visible, finite placeholder, with no scheduler."""

import logging

from life_archive.settings import get_settings


def main() -> None:
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger(__name__).info(
        "M0 worker placeholder: no jobs or scheduler configured; exiting."
    )


if __name__ == "__main__":
    main()
