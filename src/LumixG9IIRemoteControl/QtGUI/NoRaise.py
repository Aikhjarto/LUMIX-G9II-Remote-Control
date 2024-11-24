import traceback


class NoRaiseMixin:
    def _no_raise(func):
        def no_raise(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                traceback.print_exception(e)

        return no_raise
