""" Galaxy Process Management superclass and utilities
"""

import contextlib
import importlib
import inspect
import os
import subprocess
from abc import ABCMeta, abstractmethod

from gravity.config_manager import ConfigManager
from gravity.io import exception, debug, error, info
from gravity.util import which


@contextlib.contextmanager
def process_manager(*args, **kwargs):
    pm = ProcessManagerRouter(*args, **kwargs)
    try:
        yield pm
    finally:
        pm.terminate()


# If at some point we have additional process managers we can make a factory,
# but for the moment there's only supervisor.
@contextlib.contextmanager
def _process_manager(*args, **kwargs):
    state_dir = kwargs.get('state_dir')
    config_manager = ConfigManager(state_dir=state_dir)
    kwargs["config_manager"] = config_manager
    process_manager_names = config_manager.get_process_manager_names(instances=kwargs.get("instances"))
    for name in process_manager_names:
        debug(f"Trying process manager {name}")
        mod_name = "gravity.process_manager." + name
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            error(f"Unknown process manager module: {mod_name}")
            continue
        for name in dir(mod):
            obj = getattr(mod, name)
            if not name.startswith("_") and inspect.isclass(obj) and issubclass(obj, BaseProcessManager) and obj != BaseProcessManager:
                pm = obj(*args, **kwargs)
                try:
                    yield pm
                finally:
                    pm.terminate()
    return


class BaseProcessManager(object, metaclass=ABCMeta):

    def __init__(self, state_dir=None, start_daemon=True, foreground=False, **kwargs):
        self.config_manager = kwargs.get('config_manager')
        if not self.config_manager:
            self.config_manager = ConfigManager(state_dir=state_dir)
        self.state_dir = self.config_manager.state_dir
        self.tail = which("tail")

    def _service_log_file(self, log_dir, program_name):
        return os.path.join(log_dir, program_name + ".log")

    def _service_program_name(self, instance_name, service):
        return f"{instance_name}_{service['config_type']}_{service['service_type']}_{service['service_name']}"

    def _service_environment(self, service, attribs):
        environment = service.get_environment()
        environment_from = service.environment_from
        if not environment_from:
            environment_from = service.service_type
        environment.update(attribs.get(environment_from, {}).get("environment", {}))
        return environment

    def _file_needs_update(self, path, contents):
        """Update if contents differ"""
        if os.path.exists(path):
            # check first whether there are changes
            with open(path) as fh:
                existing_contents = fh.read()
            if existing_contents == contents:
                return False
        return True

    def _update_file(self, path, contents, name, file_type):
        exists = os.path.exists(path)
        if (exists and self._file_needs_update(path, contents)) or not exists:
            verb = "Updating" if exists else "Adding"
            info("%s %s %s", verb, file_type, name)
            with open(path, "w") as out:
                out.write(contents)
        else:
            debug("No changes to existing config for %s %s at %s", file_type, name, path)

    @abstractmethod
    def _process_config(self, config_file, config, **kwargs):
        """ """

    @abstractmethod
    def start(self, instance_names=None):
        """ """

    @abstractmethod
    def stop(self, instance_names=None):
        """ """

    @abstractmethod
    def restart(self, instance_names=None):
        """ """

    @abstractmethod
    def reload(self, instance_names=None):
        """ """

    @abstractmethod
    def terminate(self):
        """ """

    @abstractmethod
    def graceful(self, instance_names=None):
        """ """

    @abstractmethod
    def status(self):
        """ """

    @abstractmethod
    def update(self, instance_names=None, force=False):
        """ """

    @abstractmethod
    def shutdown(self):
        """ """

    def follow(self, instance_names, quiet=False):
        # supervisor has a built-in tail command but it only works on a single log file. `galaxyctl supervisorctl tail
        # ...` can be used if desired, though
        if not self.tail:
            exception("`tail` not found on $PATH, please install it")
        instance_names, service_names, registered_instance_names = self.get_instance_names(instance_names)
        log_files = []
        if quiet:
            cmd = [self.tail, "-f", self.log_file]
            tail_popen = subprocess.Popen(cmd)
            tail_popen.wait()
        else:
            if not instance_names:
                instance_names = registered_instance_names
            for instance_name in instance_names:
                config = self.config_manager.get_instance_config(instance_name)
                log_dir = config["attribs"]["log_dir"]
                if not service_names:
                    services = self.config_manager.get_instance_services(instance_name)
                    for service in services:
                        program_name = self._service_program_name(instance_name, service)
                        log_files.append(self._service_log_file(log_dir, program_name))
                else:
                    log_files.extend([self._service_log_file(log_dir, s) for s in service_names])
                cmd = [self.tail, "-f"] + log_files
                tail_popen = subprocess.Popen(cmd)
                tail_popen.wait()

    def get_instance_names(self, instance_names):
        registered_instance_names = self.config_manager.get_registered_instance_names()
        unknown_instance_names = []
        if instance_names:
            _instance_names = []
            for n in instance_names:
                if n in registered_instance_names:
                    _instance_names.append(n)
                else:
                    unknown_instance_names.append(n)
            instance_names = _instance_names
        elif registered_instance_names:
            instance_names = registered_instance_names
        else:
            exception("No instances registered (hint: `galaxyctl register /path/to/galaxy.yml`)")
        return instance_names, unknown_instance_names, registered_instance_names


class ProcessManagerRouter(BaseProcessManager):
    def __init__(self, state_dir=None, start_daemon=True, foreground=False, **kwargs):
        super(ProcessManagerRouter, self).__init__(state_dir=state_dir, **kwargs)
        self._load_pm_modules(state_dir=state_dir, **kwargs)

    def _load_pm_modules(self, *args, **kwargs):
        self.process_managers = {}
        for filename in os.listdir(os.path.dirname(__file__)):
            if filename.endswith(".py") and not filename.startswith("_"):
                mod = importlib.import_module("gravity.process_manager." + filename[: -len(".py")])
                for name in dir(mod):
                    obj = getattr(mod, name)
                    if not name.startswith("_") and inspect.isclass(obj) and issubclass(obj, BaseProcessManager) and obj != BaseProcessManager:
                        pm = obj(*args, **kwargs)
                        self.process_managers[pm.name] = pm

    def __group_instance_names_by_pm(self, instance_names):
        instance_names_by_pm = {}
        instance_names = self.get_instance_names(instance_names)[0]
        for instance_name in instance_names:
            config = self.config_manager.get_instance_config(instance_name)
            try:
                instance_names_by_pm[config.process_manager].append(instance_name)
            except KeyError:
                instance_names_by_pm[config.process_manager] = [instance_name]
        return instance_names_by_pm

    def __route_method(self, method, *args, **kwargs):
        instance_names = kwargs.get("instance_names")
        instance_names_by_pm = self.__group_instance_names_by_pm(instance_names)
        for pm_name, instance_names in instance_names_by_pm.items():
            pm = self.process_managers[pm_name]
            debug(f"Calling '{method}()' in process manager {pm_name} for instance(s): {instance_names}")
            # the kwargs are just whatever the user provided, we swap these out for validated instance names for the
            # given process manager
            if "instance_names" in kwargs:
                kwargs["instance_names"] = instance_names
            getattr(pm, method)(*args, **kwargs)

    def _process_config(self, config_file, config, **kwargs):
        """ """
        raise NotImplementedError()

    def start(self, instance_names=None):
        """ """
        self.__route_method('start', instance_names=instance_names)

    def terminate(self):
        """ """
        self.__route_method('terminate')

    def stop(self, instance_names):
        """ """
        self.__route_method('stop', instance_names=instance_names)

    def restart(self, instance_names):
        """ """
        self.__route_method('restart', instance_names=instance_names)

    def reload(self, instance_names):
        """ """
        self.__route_method('reload', instance_names=instance_names)

    def graceful(self, instance_names):
        """ """
        self.__route_method('graceful', instance_names=instance_names)

    def status(self):
        """ """
        self.__route_method('status')

    def update(self, instance_names=None, force=False):
        """ """
        for config_file, config in self.config_manager.get_registered_configs().items():
            debug(f"#### CHANGES: {config_file}: {config.get('changed')}")
        #return
        # FIXME: update is special because it has to run on all PMs if the instance's PM changed
        #instance_names_by_pm = self._group_instance_names_by_pm(instance_names)
        #for pm_name, instance_names in instance_names_by_pm.items():
        #    pm = self.process_managers[pm_name]
        #    pm.update(instance_names, force=force)
        for pm in self.process_managers.values():
            pm.update(instance_names, force=force)

    def shutdown(self):
        """ """
        self.__route_method('shutdown')



def for_instances(func):
    def decorator(self, instance_names, **kwargs):
        instance_names = self.get_instance_names(instance_names)[0]
        valid_instance_names = []
        for instance in instance_names:
            config = self.config_manager.get_instance_config(instance)
            if config.process_manager == self.name:
                valid_instance_names.append(instance)
            else:
                debug(f"Skipped: process manager '{self.name}' is not the process manager for instance '{instance}': {config.process_manager}")
        debug(f"#### Calling {func} with instance_names {valid_instance_names}")
        return func(self, valid_instance_names, **kwargs)
    return decorator
