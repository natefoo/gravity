"""
"""
import errno
import os
import shlex
import subprocess

from gravity.io import debug, info
from gravity.process_manager import BaseProcessManager
from gravity.settings import ProcessManager

SYSTEMD_SERVICE_TEMPLATES = {}
SYSTEMD_SERVICE_TEMPLATES["gunicorn"] = """;
; This file is maintained by Gravity - CHANGES WILL BE OVERWRITTEN
;

[Unit]
Description=Galaxy {program_name}
After=network.target
After=time-sync.target

[Service]
UMask={galaxy_umask}
Type=simple
{systemd_user_group}
WorkingDirectory={galaxy_root}
TimeoutStartSec=15
ExecStart={command}
#ExecReload=
#ExecStop=
{environment}
#MemoryLimit=
Restart=always

MemoryAccounting=yes
CPUAccounting=yes
BlockIOAccounting=yes

[Install]
WantedBy=multi-user.target
"""

SYSTEMD_SERVICE_TEMPLATES["celery"] = SYSTEMD_SERVICE_TEMPLATES["gunicorn"]
SYSTEMD_SERVICE_TEMPLATES["celery-beat"] = SYSTEMD_SERVICE_TEMPLATES["gunicorn"]


class SystemdProcessManager(BaseProcessManager):

    name = ProcessManager.systemd

    def __init__(self, state_dir=None, start_daemon=True, foreground=False, **kwargs):
        super(SystemdProcessManager, self).__init__(state_dir=state_dir, **kwargs)
        self.user_mode = os.geteuid() != 0

    @property
    def __systemd_unit_dir(self):
        unit_path = "/etc/systemd/system" if not self.user_mode else os.path.expanduser("~/.config/systemd/user")
        return unit_path

    @property
    def __use_instance(self):
        #return not self.config_manager.single_instance
        return False

    def __systemctl(self, *args, **kwargs):
        args = list(args)
        if self.user_mode:
            args = ["--user"] + args
        try:
            debug("Calling systemctl with args: %s", args)
            subprocess.check_call(["systemctl"] + args)
        except:
            raise

    def __unit_name(self, instance_name, service):
        unit_name = f"{service['config_type']}-"
        if self.__use_instance:
            unit_name += f"{instance_name}-"
        unit_name += f"{service['service_name']}.service"
        return unit_name

    def __update_service(self, config_file, config, attribs, service, instance_name):
        unit_name = self.__unit_name(instance_name, service)

        # FIXME: refactor
        # used by the "standalone" service type
        attach_to_pool_opt = ""
        server_pools = service.get("server_pools")
        if server_pools:
            _attach_to_pool_opt = " ".join(f"--attach-to-pool={server_pool}" for server_pool in server_pools)
            # Insert a single leading space
            attach_to_pool_opt = f" {_attach_to_pool_opt}"

        virtualenv_dir = attribs.get("virtualenv")
        virtualenv_bin = f'{os.path.join(virtualenv_dir, "bin")}{os.path.sep}' if virtualenv_dir else ""
        gunicorn_options = attribs["gunicorn"].copy()
        gunicorn_options["preload"] = "--preload" if gunicorn_options["preload"] else ""

        format_vars = {
            #"log_dir": attribs["log_dir"],
            #"log_file": self._service_log_file(attribs["log_dir"], program_name),
            "program_name": service["service_name"],
            "systemd_user_group": "",
            "config_type": service["config_type"],
            "server_name": service["service_name"],
            "attach_to_pool_opt": attach_to_pool_opt,
            "gunicorn": gunicorn_options,
            "celery": attribs["celery"],
            "galaxy_infrastructure_url": attribs["galaxy_infrastructure_url"],
            "tusd": attribs["tusd"],
            "gx_it_proxy": attribs["gx_it_proxy"],
            "galaxy_umask": service.get("umask", "022"),
            "galaxy_conf": config_file,
            "galaxy_root": config["galaxy_root"],
            "virtualenv_bin": virtualenv_bin,
            "state_dir": self.state_dir,
        }
        format_vars["command"] = service.command_template.format(**format_vars)
        if not format_vars["command"].startswith("/"):
            # FIXME: bit of a hack
            format_vars["command"] = f"{virtualenv_bin}/{format_vars['command']}"
        if not self.user_mode:
            format_vars["systemd_user_group"] = f"User={attribs['galaxy_user']}"
            if "galaxy_group" in attribs:
                format_vars["systemd_user_group"] += f"\nGroup={attribs['galaxy_group']}"
        conf = os.path.join(self.__systemd_unit_dir, unit_name)

        template = SYSTEMD_SERVICE_TEMPLATES.get(service["service_type"])
        if not template:
            raise Exception(f"Unknown service type: {service['service_type']}")

        environment = self._service_environment(service, attribs)
        format_vars["environment"] = "\n".join("Environment={}={}".format(k, shlex.quote(v.format(**format_vars))) for k, v in environment.items())

        contents = template.format(**format_vars)
        service_name = self._service_program_name(instance_name, service)
        self._update_file(conf, contents, service_name, "service")

        return conf

    def start(self, instance_names=None):
        """ """
        # FIXME: the service name shortcut is probably broken
        for config_file, config in self.config_manager.get_registered_configs(instances=instance_names).items():
            unit_names = [self.__unit_name(config.instance_name, s) for s in config["services"]]
            self.__systemctl("start", *unit_names)

    def _process_config(self, config_file, config, **kwargs):
        """ """
        instance_name = config["instance_name"]
        attribs = config["attribs"]
        intended_configs = set()
        present_configs = set()

        try:
            os.makedirs(self.__systemd_unit_dir)
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise

        # FIXME: none of this works for instances
        for service in config["services"]:
            intended_configs.add(self.__update_service(config_file, config, attribs, service, instance_name))

        # FIXME: should use config_type, but that's per-service
        _present_configs = filter(lambda f: f.startswith("galaxy-"), os.listdir(self.__systemd_unit_dir))
        present_configs.update([os.path.join(self.__systemd_unit_dir, f) for f in _present_configs])

        for file in (present_configs - intended_configs):
            service_name = os.path.basename(os.path.splitext(file)[0])
            info(f"Ensuring service is stopped: {service_name}")
            self.__systemctl("stop", service_name)
            info("Removing service config %s", file)
            os.unlink(file)

    def terminate(self):
        """ """
        debug("TERMINATE")

    def stop(self, instance_names=None):
        """ """
        for config_file, config in self.config_manager.get_registered_configs(instances=instance_names).items():
            unit_names = [self.__unit_name(config.instance_name, s) for s in config["services"]]
            self.__systemctl("stop", *unit_names)

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
        for config_file, config in self.config_manager.get_registered_configs().items():
            unit_names = [self.__unit_name(config.instance_name, s) for s in config["services"]]
            self.__systemctl("status", "--lines=0", *unit_names)

    def update(self, instance_names=None, force=False):
        """ """
        for config_file, config in self.config_manager.get_registered_configs(instances=instance_names).items():
            process_manager = config["process_manager"]
            if process_manager == self.name:
                self._process_config(config_file, config)
            else:
                pass
                """
                # FIXME: refactor
                instance_name = config["instance_name"]
                instance_conf_dir = join(self.supervisord_conf_dir, f"{instance_name}.d")
                group_file = join(self.supervisord_conf_dir, f"group_{instance_name}.conf")
                if os.path.exists(instance_conf_dir):
                    shutil.rmtree(instance_conf_dir)
                if os.path.exists(group_file):
                    os.unlink(group_file)
                """
        self.__systemctl("daemon-reload")


    def shutdown(self):
        """ """
        debug(f"SHUTDOWN")
