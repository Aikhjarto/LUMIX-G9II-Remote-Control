import argparse

import LumixG9IIRemoteControl.configure_logging
import LumixG9IIRemoteControl.LumixG9IIWiFiControl
from LumixG9IIRemoteControl.parser import add_general_options_to_parser

from .configure_logging import logger


def setup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    add_general_options_to_parser(parser)
    parser.add_argument("--use-full-IPython", action="store_true", default=False)
    return parser


if __name__ == "__main__":
    try:
        args = setup_parser().parse_args()

        header = """LumixG9IIRemoteControl: use g9ii<tab> to see your options, e.g.
            g9ii.print_set_setting_commands()
            g9ii.print_current_settings()
            g9ii.set_setting('exposure', -3)
            g9ii.oneshot_af()
            g9ii.capture()
            use '?' instead of brackets to print the helpstring, e.g. g9ii.start_stream?
            """

        if args.use_full_IPython:
            import IPython
            from traitlets.config import Config

            c = Config()
            c.InteractiveShellApp.exec_lines = [
                "import LumixG9IIRemoteControl.LumixG9IIWiFiControl",
                "import LumixG9IIRemoteControl.LumixG9IIBluetoothControl"
                f"g9ii = LumixG9IIRemoteControl.LumixG9IIWiFiControl.LumixG9IIRemoteControl(auto_connect={args.auto_connect}, host={args.hostname})",
            ]
            c.InteractiveShellApp.hide_initial_ns = False

            c.InteractiveShell.banner2 = header
            IPython.start_ipython(argv=[], local_ns=locals(), config=c)

        else:
            import IPython

            g9ii = LumixG9IIRemoteControl.LumixG9IIWiFiControl.LumixG9IIWiFiControl(
                auto_connect=args.auto_connect, host=args.hostname
            )
            IPython.embed(header=header)
        # try:
        #     g9ii.connect(host=args.hostname)
        # except RuntimeError as e:
        #     traceback.print_exception(e)

        # g9ii.start_stream()
        # g9ii.set_playmode()
        # g9ii.set_recmode()

        # g9ii._state_thread.join()
        # g9ii = LumixG9IIRemoteControl()
        # g9ii._allmenu_tree = defusedxml.ElementTree.parse("../../Dumps/allmenu.xml")
        # g9ii.set_local_language()
    except Exception as e:
        logger.exception(e, exc_info=True)
