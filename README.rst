========================================
 gravity - Galaxy Server Administration
========================================

A process manager (`supervisor`_) and management tools for `Galaxy`_ servers.

Installing this will give you an executables, ``galaxy`` which is used to
manage Galaxy.  A virtualenv will automatically be created for your Galaxy
server. It's a good thing.

Installation
============

Python 2.7 is required. Sadly, Python 3 won't work, because supervisor doesn't
support it, `although work is in progress <supervisor issue 491_>`_.

To install:

``pip install gravity``

To make your life easier, you are encourged to install into a `virtualenv`_,
and to make that trivial, you are encouraged to use `virtualenv-burrito`_.

Notes
=====

``[galaxy:server]``

Add this section to your ``galaxy.ini``, ``reports_wsgi.ini``,
``tool_shed_wsgi.ini`` to set:

::

    instance_name = string  # override the default auto-generated instance name
    galaxy_root = /path     # if galaxy is not at ../ or ./ from the config file
    virtualenv = /path      # override default auto-generated virtualenv path (it
                            #   will be created if it does not exist)
    log_dir = /path         # where to log galaxy server output. for uwsgi you
                            #   probably want to use uwsgi's logto option though
    uwsgi_path = /path      # explicit path to uwsgi, otherwise it will be found on
                            #   $PATH. Or, the special value `install`, which will
                            #   cause it to be installed into service's virtualenv

Potentially useful information, tricks, etc.:

-  Unless you set different state dirs with ``--state-dir`` or
   ``$GRAVITY_STATE_DIR``, there will only be one supervisord for all
   of your galaxy instances. But they will be separated out by a
   generated ``instance_name``. You can override this with
   ``instance_name`` in ``[galaxy:server]``.

-  To put configs (galaxy configs, galaxy + reports, whatever) into the
   same instance, set their ``instance_name`` to the same string in each
   config's ``[galaxy:server]``. This puts them into a single supervisor
   group, which may be what you want, although note that any
   start/stop/restart/etc. is performed on the entire group, which may
   not be what you want.

-  The config manager generally views things in terms of config files.
   If you change the virtualenv or ``galaxy_root`` in a config file, it
   will not change that value for all services in the instance
   (supervisor group), it will only change it for the services started
   from that config.

-  Anything you drop in to ``$GRAVITY_STATE_DIR/supervisor/supervisord.conf.d``
   will be picked up by supervisord on a ``galaxy supervisorctl update`` or just
   ``galaxy update``

-  The ``job_conf.xml`` parsed corresponds to the galaxy config, it'll
   check the path in ``job_config_file`` in ``[app:main]`` or default to
   ``galaxy_root/config/job_conf.xml`` if that file exists. If handlers
   in ``job_conf.xml`` have a corresponding ``[server:]`` in
   ``galaxy.ini``, they will be started using Paste. If there is not a
   corresponding ``[server:]`` they will be started as a "standalone"
   server with ``galaxy_root/lib/galaxy/main.py``

Subcommands
===========

Use ``galaxy -h`` for help. Subcommands also support ``-h``, e.g.  ``galaxy add
-h``.

``add``

Register a Galaxy, Reports, or Tool Shed server config with the process
manager, create a virtualenv, create supervisor configs, and update.
Does not start.

``list``

List config files registered with the process manager.

``instances``

List known instances and services.

``get /path/to/galaxy.ini``

Show stored configuration details for the named config file.

``rename /path/to/old.ini /path/to/new.ini``

Use this if you move your config.

``remove /path/to/galaxy.ini`` ``remove instance_name``

Deregister a Galaxy et. al. server config., or all configs referencing
the supplied ``instance_name``.

| ``start [instance_name]``
| ``stop [instance_name]``
| ``restart [instance_name]``

Roughly what you'd expect. If ``instance_name`` isn't provided, perform
the operation on all known instances.

If you call ``start`` from the root (or from 1 subdirectory deep) of a Galaxy
source tree, ``config/galaxy.ini`` if it exists, or else
``config/galaxy.ini.sample`` will automatically be registered with ``galaxy
add`` and then ``galaxy start`` will start the newly added server.

``reload [instance_name]``

The same as restart but uWSGI master processes will only receive a
``SIGHUP`` so the workers restart but the master stays up.

``graceful [instance_name]``

The same as reload but Paste servers will be restarted sequentially, and
the next one will not be restarted until the previous one is up and
accepting requests.

``update``

Figure out what has changed in configs, which could be:

-  changes to ``[galaxy:server]``
-  adding or removing ``[server:]`` sections
-  adding or removing a ``[uwsgi]`` section
-  adding or removing handlers in ``job_conf.xml``

This will perform the operation for all registered configs, which may
cause unintended service restarts.

Any needed changes to supervisor configs will be performed and then
``supervisorctl update`` will be called. You will need to do a
``galaxy start`` after this to start any newly added instances (or
possibly even old instances, since adding new programs to a group in
supervisor causes the entire group to be stopped).

Update is called automatically for the ``start``, ``stop``, ``restart``,
``reload``, and ``graceful`` subcommands.

``supervisorctl [subcommand]``

Pass through directly to supervisor

``shutdown``

Stop supervisord

.. _supervisor: http://supervisord.org/
.. _Galaxy: http://galaxyproject.org/
.. _supervisor issue 491: https://github.com/Supervisor/supervisor/issues/491
.. _virtualenv: https://virtualenv.pypa.io/
.. _virtualenv-burrito: https://github.com/brainsik/virtualenv-burrito
