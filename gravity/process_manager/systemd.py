"""
"""


from gravity.io import debug
from gravity.process_manager import BaseProcessManager
from gravity.settings import ProcessManager


class SystemdProcessManager(BaseProcessManager):

    name = ProcessManager.systemd

    def __init__(self, state_dir=None, start_daemon=True, foreground=False, **kwargs):
        super(SystemdProcessManager, self).__init__(state_dir=state_dir, **kwargs)

    def start(self, instance_names):
        """ """
        debug(f"START: {instance_names}")

    def _process_config(self, config_file, config, **kwargs):
        """ """
        raise NotImplementedError()

    def terminate(self):
        """ """
        debug("TERMINATE")

    def stop(self, instance_names=None):
        """ """
        debug(f"STOP: {instance_names}")

    def restart(self, instance_names=None):
        """ """
        debug(f"RESTART: {instance_names}")

    def reload(self, instance_names=None):
        """ """
        debug(f"RELOAD: {instance_names}")

    def graceful(self, instance_names=None):
        """ """
        debug(f"GRACEFUL: {instance_names}")

    def status(self):
        """ """
        debug(f"STATUS")

    def update(self, instance_names=None, force=False):
        """ """
        debug(f"UPDATE: {instance_names}")

    def shutdown(self):
        """ """
        debug(f"SHUTDOWN")
