import argparse


def add_general_options_to_parser(parser: argparse.ArgumentParser):
    parser.add_argument("--hostname", type=str, help="Hostname or IP-Adress of camera")
    parser.add_argument("--auto-connect", action="store_true")
