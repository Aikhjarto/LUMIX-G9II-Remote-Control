from qtconsole.inprocess import QtInProcessKernelManager
from qtconsole.rich_jupyter_widget import RichJupyterWidget


class EmbedIPythonWidget(RichJupyterWidget):
    """
    Providing a IPython widget with a kernel.
    https://github.com/gpoulin/python-test/blob/master/embedded_qtconsole.py
    """

    def __init__(self, **kwarg):
        super(RichJupyterWidget, self).__init__()
        self.kernel_manager = QtInProcessKernelManager()
        self.kernel_manager.start_kernel()
        self.kernel = self.kernel_manager.kernel
        self.kernel.shell.push(kwarg)
        self.kernel_client = self.kernel_manager.client()
        self.kernel_client.start_channels()

    def update_console_namespace(self, module, cls, variable_name):
        """
        Walks through stack to find a variable with `variable_name` from type
        `cls` either from module `module` or module __main__.
        If a corresponding variable is found, it is added along with all other
        variables from the same local namespace to the namespace of the console.

        Parameters
        ----------
        module : str
        cls : str
        variable_name : str
        """

        # Note: isinstance makes a difference between __main__.MyClass and mymodule.MyClass
        # https://stackoverflow.com/questions/54018653/what-does-main-mean-in-the-output-of-type

        self.kernel.shell.run_cell(
            "from {0} import {1}; import inspect; locals().update(["
            "f.frame.f_locals for f in inspect.getouterframes(inspect.currentframe()) "
            "if '{2}' in f.frame.f_locals and (isinstance(f.frame.f_locals['{2}'], {1}) or str(type(f.frame.f_locals['{2}']))=='<class \\'__main__.'+'{1}'+'\\'>')][0])".format(
                module, cls, variable_name
            )
        )
